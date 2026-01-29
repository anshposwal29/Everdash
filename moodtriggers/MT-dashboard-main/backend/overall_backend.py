#%%
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text, exc
import logging
import io
import os
import zipfile
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, text, exc
import logging
from dotenv import load_dotenv
import json
import sys

import config


# database conn
DB_USER = config.DB_USER
DB_PASSWORD = config.DB_PASSWORD
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
DB_NAME = config.DB_NAME


DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")


def to_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()
  
def slice_into_weeks(date_range):
    weeks = []
    n = len(date_range)

    # Work from the end in chunks of 7 days
    for i in range(n, 0, -7):
        start = max(0, i - 7)
        week_dates = date_range[start:i]
        weeks.append((week_dates[0], week_dates[-1]))
        
    # The list is already ordered with the most recent week first
    return weeks
  
def count_ema_days(pid, s_ms, e_ms_excl):
    try:
        with engine.connect() as conn2:
            qq = text("""
                        SELECT *
                        FROM ema_responses_final3
                        WHERE (participant_id::text = :pid OR participant_id::text = ltrim(:pid,'0'))
                          AND date >= :start
                          AND date <= :end
                        ORDER BY date
                                """)
            
            result = conn2.execute(qq, {"pid": pid, "start": s_ms, "end": e_ms_excl})
            result = pd.DataFrame(result.fetchall(), columns=result.keys())

            result['date'] = pd.to_datetime(result['date'], errors='coerce').dt.date

            try:

                # Pivot the existing data
                result = result.groupby('date')['surveyId'].nunique().reset_index(name='Total')
                study_start_date = result['date'].iloc[0]

                range_start = max(pd.to_datetime(s_ms), pd.to_datetime(study_start_date))  # start stays as is unless study started later
                range_end = min(pd.to_datetime(e_ms_excl), pd.to_datetime(study_start_date)+ timedelta(config.Study_length))  # end stays as is unless study ended

                # Create full date range
                full_dates = pd.DataFrame({
                    'date': pd.date_range(start=pd.to_datetime(range_start), end=pd.to_datetime(range_end), freq='D')
                })
                
                full_dates['date'] = pd.to_datetime(full_dates['date']).dt.date
                
                result = full_dates.merge(result, how='outer', on='date')
                
                result = result.fillna(0).reset_index()
                
                result["n"] = result['Total'].clip(upper=config.EMA_promts)
  
                n = result['Total'].clip(upper=config.EMA_promts).sum() 
                

            except Exception as e:
                result = {"n": 0} 
                n = 0
                study_start_date = 0


            return int(n or 0), result, study_start_date
    except Exception as e:
        return 0

def get_overall_status(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    participant_filter: list[str] | None = None
):
  
  
    start_dt = to_date(start_date) - timedelta(days=1)
    end_dt = to_date(end_date) 

    today_date = datetime.now().date()  - timedelta(days=1)

  
    def query_presence_set_for_day(table_name, conn, pid, day_dt, ts_col="timestamp"):
        """
        Fetch hours per day for a single participant and a single day.
        Only fetches timestamps for that day.
        """
        day_start_ms = int(datetime.combine(day_dt, datetime.min.time()).timestamp() * 1000)
        day_end_ms = int((datetime.combine(day_dt, datetime.min.time()) + timedelta(days=1)).timestamp() * 1000)
    
        sql = f"""
            SELECT {ts_col} AS ts
            FROM {table_name}
            WHERE participant_id::text = :pid
              AND {ts_col} >= :start_ms
              AND {ts_col} < :end_ms
        """
    
        rows = conn.execute(text(sql), {"pid": pid, "start_ms": day_start_ms, "end_ms": day_end_ms}).mappings().all()
    
        # Count distinct hours seen
        hours_seen = set()
        for r in rows:
            dt = datetime.utcfromtimestamp(r["ts"] / 1000)
            hours_seen.add(dt.hour)
    
        return len(hours_seen)

    
    def query_ema_response(conn, ts_col="timestamp"):
        ema_sql = f"""
                SELECT 
                    participant_id,
                    DATE_TRUNC('day', TO_TIMESTAMP({ts_col} / 1000)) AS day,
                    ROUND(AVG(response)::numeric, 2) AS resp
                FROM ema_responses_final3
                WHERE participant_id IS NOT NULL
                GROUP BY participant_id, day
        """

        ema_rows = conn.execute(text(ema_sql)).mappings().all()

        # Structure: {participant_id: {day: hours}}
        out = {}
        for r in ema_rows:
            pid = str(r["participant_id"])
            day = r["day"].date().strftime("%Y-%m-%d")
            ema_resp = float(r["resp"])
            out.setdefault(pid, {})[day] = ema_resp
        return out

    try:
        with engine.connect() as conn:
            # participants in ema
            all_pids_res = conn.execute(text("""
                SELECT DISTINCT participant_id
                FROM ema_responses_final3
                WHERE participant_id IS NOT NULL
            """)).mappings().all()
            
            all_pids = [str(r["participant_id"]) for r in all_pids_res]
            
            # Apply filter if provided
            if participant_filter != None: # '0':
                all_pids = [pid for pid in all_pids if pid in participant_filter]
                
            logger.info(f"Found {len(all_pids)} participants in EMA table")

            ema_resp_presence = query_ema_response(conn)

            # first EMA timestamp per participant (ms)
            first_ts_rows = conn.execute(text("""
                SELECT participant_id, MIN(date) AS first_ts
                FROM ema_responses_final3
                WHERE participant_id IS NOT NULL
                GROUP BY participant_id
            """)).mappings().all()
            first_ts_map = {str(r["participant_id"]): r["first_ts"] for r in first_ts_rows}

        # response
        date_range = [(start_dt + timedelta(days=i)) for i in range((today_date - start_dt).days + 1)]
        final_response = []
  
        logger.info(f"Starting computation for {len(all_pids)} participants")
        
        cached_daily_status = {}
        
        if participant_filter is None:
            try:
                with engine.connect() as conn:
                    existing_cache_rows = conn.execute(text("""
                        SELECT participant_id, daily_status_list
                        FROM overall_status_cache
                    """)).mappings().all()
        
                if not existing_cache_rows:
                    print("⚠️ overall_status_cache is empty. Nothing to preload.")
                    cached_daily_status = {}
                else:
                    for row in existing_cache_rows:
                        pid = str(row["participant_id"])
                        raw = row["daily_status_list"]
        
                        if raw is None:
                            continue
        
                        # Ensure JSON is converted to Python list
                        if isinstance(raw, str):
                            try:
                                raw = json.loads(raw)
                            except Exception:
                                continue
        
                        if not isinstance(raw, list):
                            continue
        
                        cached_daily_status[pid] = raw
        
                    print("✅ Successfully cached daily_status_list")
        
            except Exception as e:
                print("⚠️ overall_status_cache table does not exist. Skipping caching step.", e)

        

        with engine.connect() as conn: 
          for pid_str in all_pids:
              print(pid_str)
  
              _, ema_presence, study_start_date = count_ema_days(pid_str, start_dt - timedelta(1), end_dt + timedelta(1))
  
              # Normalize cached values to pure YYYY-MM-DD strings
              existing_days_str = set()
              for row in cached_daily_status.get(pid_str, []):
                  d = row.get("date")
                  if hasattr(d, "strftime"):
                      existing_days_str.add(d.strftime("%Y-%m-%d"))
                  else:
                      existing_days_str.add(str(d).strip())
              
                          
  
              daily_status_list = []
              daily_passive_rows = []
  
              
              for day_dt in date_range:
                
                  day_str = day_dt.strftime("%Y-%m-%d").strip()
                  
                  if day_str in existing_days_str:
                    
                      logger.info(f"Skipping already processed day: {day_str} for PID {pid_str}")
                      continue
                    
                  # Query passive data per table for this participant and day
                  loc_missing = query_presence_set_for_day('location_final3', conn, pid_str, day_dt)
                  bat_missing = query_presence_set_for_day('battery_level_final3', conn, pid_str, day_dt)
                  acc_missing = query_presence_set_for_day('acceleration_final3', conn, pid_str, day_dt)
                  angv_missing = query_presence_set_for_day('angv_final3', conn, pid_str, day_dt)
                  light_missing = query_presence_set_for_day('illuminance_final3', conn, pid_str, day_dt)
                  screen_missing = query_presence_set_for_day('screen_events_final3', conn, pid_str, day_dt)
                  phone_missing = query_presence_set_for_day('phone_record_final3', conn, pid_str, day_dt)
                  sms_missing = query_presence_set_for_day('sms_record_final3', conn, pid_str, day_dt)
                  app_missing = query_presence_set_for_day('app_usage_final3', conn, pid_str, day_dt)
                  
                  # EMA response for today
                  ema_resp_today = ema_resp_presence.get(pid_str, {}).get(day_str, 0)
                  
                  # Determine if any passive data exists for today
                  passive_present = any([
                    loc_missing,
                    bat_missing,
                    acc_missing,
                    angv_missing,
                    light_missing,
                    screen_missing,
                    phone_missing,
                    sms_missing,
                    app_missing
                  ])
                  

                  ema_resp_missing = ema_resp_presence.get(pid_str, {}).get(day_str, 0) 
  
                  HOURS_PER_DAY = 24
  
                  loc_available_pct = max(0, (loc_missing) / HOURS_PER_DAY * 100)
                  bat_available_pct = max(0, (bat_missing) / HOURS_PER_DAY * 100)
                  acc_available_pct = max(0, (acc_missing) / HOURS_PER_DAY * 100)
                  gyro_available_pct = max(0, (angv_missing) / HOURS_PER_DAY * 100)
                  
                  daily_passive_rows.append({
                      "date": pd.to_datetime(day_str),
                      "loc_available_pct": loc_available_pct,
                      "bat_available_pct": bat_available_pct,
                      "acc_available_pct": acc_available_pct,
                      "gyro_available_pct": gyro_available_pct,
                      "passive_available_pct": (loc_available_pct + bat_available_pct + acc_available_pct + gyro_available_pct) / 4
                  })
  
    
                  if day_str in ema_presence["date"].astype(str).values:
                      day_counts = ema_presence.loc[ema_presence["date"].astype(str) == day_str]
                      total_ema_done = int(day_counts['n'].iloc[0])  
                  else:
                      total_ema_done = 0
           
                  
                  daily_status_list.append({
                    "date": day_str,
                    "ema_done": total_ema_done,
                    "ema_avg_response_time": ema_resp_today,
                    "passive_available_pct": (loc_available_pct + bat_available_pct + acc_available_pct + gyro_available_pct) / 4,
                    "location": loc_missing,
                    "battery": bat_missing,
                    "accelerometer": acc_missing,
                    "angular_velocity": angv_missing,
                    "light": light_missing,
                    "screen_events": screen_missing,
                    "phone": phone_missing,
                    "sms": sms_missing,
                    "app_usage": app_missing,
                  })
                    
              


              cached_status_rows = cached_daily_status.get(pid_str, [])
              full_daily_status_dates = cached_status_rows + daily_status_list
                          
              cached_rows = cached_daily_status.get(pid_str, [])
              
              # Only keep cached rows that actually contain passive metrics
              cached_passive_rows = [
                  r for r in cached_rows
                  if "passive_available_pct" in r
              ]
              
              daily_passive_df = pd.concat(
                  [pd.DataFrame(cached_passive_rows), pd.DataFrame(daily_passive_rows)],
                  ignore_index=True
              )
              
              if not daily_passive_df.empty:
                  daily_passive_df["date"] = pd.to_datetime(daily_passive_df["date"])
            
              ##### Try out weekly compliance:
              # Ensure datetime
              ema_presence = ema_presence.copy()
              ema_presence['date'] = pd.to_datetime(ema_presence['date'])
              
              weekly_results = []
              weeks = slice_into_weeks(date_range)
              
              for start, end in weeks:
                  start = pd.to_datetime(start)
                  end = pd.to_datetime(end)
                  
                  # EMA data
              
                  # Filter EMA data to this week
                  week_data = ema_presence[
                      (ema_presence['date'] >= start) &
                      (ema_presence['date'] <= end)
                  ]
              
                  # Total EMAs completed in this week
                  total_emas_done = int(week_data['n'].sum())
        
                  
                  # Number of days in the week window
                  num_days = week_data.shape[0] 
              
                  # Expected EMAs
                  denom_days = num_days * config.EMA_promts
              
                  weekly_compliance = (
                      round((total_emas_done / denom_days) * 100)
                      if denom_days > 0 else 0
                  )
                  
                  
                  
                  study_start_date = pd.to_datetime(study_start_date)
                  week_start = max(pd.to_datetime(start), study_start_date)    # cannot be before study start
                  week_end = min(pd.to_datetime(end), study_start_date + timedelta(days=config.Study_length))  # cap at study end
                  
                  # Filter daily passive to this clipped week
                  week_passive = daily_passive_df[
                      (daily_passive_df["date"] >= week_start) &
                      (daily_passive_df["date"] <= week_end)
                  ]
                                  
                  avg_passive_pct = (
                      round(week_passive["passive_available_pct"].mean())
                      if not week_passive.empty else 0
                  )
                  
      
              
                  weekly_results.append({
                      "start_date": start.date().isoformat(),
                      "end_date": end.date().isoformat(),
                      "weekly_compliance": weekly_compliance,
                      "avg_passive_pct": avg_passive_pct,
                  })
  
              overall_compliance = 0
              avg_overall_passive_pct = 0
              first_ts = first_ts_map.get(pid_str)
  
              if first_ts:
                  first_date = first_ts.date() if isinstance(first_ts, datetime) else first_ts
  
                  window_end_date = min(first_date + timedelta(days=config.Study_length-1), today_date)
                
                  if window_end_date >= first_date:
                      denom_days = ((window_end_date - first_date).days + 1)*config.EMA_promts  # eligible days so far (<= 90)
      
  
                      num_days_with_ema, _, _  = count_ema_days(pid_str, first_date - timedelta(1), window_end_date + timedelta(1))
                      overall_compliance = round((num_days_with_ema / denom_days) * 100) if denom_days > 0 else 0
                      
                      if not daily_passive_df.empty:
                        daily_passive_df["date"] = pd.to_datetime(daily_passive_df["date"])
                      
                        study_start_dt = pd.to_datetime(study_start_date).normalize()
                        window_end_dt = pd.to_datetime(window_end_date).normalize()
                          
                        study_days_df = daily_passive_df[
                            (daily_passive_df["date"] >= study_start_dt) &
                            (daily_passive_df["date"] <= window_end_dt)
                        ]
                      
                        avg_overall_passive_pct = (
                            round(study_days_df["passive_available_pct"].mean())
                            if not study_days_df.empty else 0
                        )
 

                  else:
                      overall_compliance = 0
  
                  final_response.append({
                      "id": pid_str.zfill(5),
                      "daily_status_list": json.dumps(full_daily_status_dates),
                      "weekly_compliance": json.dumps(weekly_results),
                      "overall_compliance": overall_compliance,
                      "avg_overall_passive_pct": avg_overall_passive_pct,
                      "study_start_date": study_start_date,
                      "total_EMA": num_days_with_ema
                  })
  
              final_response = sorted(final_response, key=lambda x: x["id"])

    except Exception as e:
        logger.error(f"/overall_status endpoint failed: {e}", exc_info=True)
        raise 

            
    # Store in a cache table
    with engine.begin() as conn:
        # Create table if it does not exist, including the 'excluded' column
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS overall_status_cache (
                participant_id TEXT,
                study_start_date DATE,
                start_date DATE,
                end_date DATE,
                daily_status_list JSONB,
                weekly_compliance JSONB,
                overall_compliance INT,
                avg_overall_passive_pct INT,
                total_EMA INT,
                excluded BOOLEAN DEFAULT FALSE,
                updated_at TIMESTAMP DEFAULT now(),
                PRIMARY KEY (participant_id)
            )
        """))
        

        if len(all_pids) != 1:
            for rec in final_response:
                conn.execute(text("""
                    INSERT INTO overall_status_cache 
                    (participant_id, start_date, end_date, study_start_date, daily_status_list, weekly_compliance, overall_compliance,avg_overall_passive_pct,total_EMA, excluded)
                    VALUES 
                    (:pid, :start, :end, :study_start_date, :daily_status_list, :weekly, :overall, :overall_passive, :total_EMA, FALSE)
                    ON CONFLICT (participant_id)
                    DO UPDATE SET 
                        daily_status_list = overall_status_cache.daily_status_list || EXCLUDED.daily_status_list,
                        weekly_compliance = EXCLUDED.weekly_compliance,
                        overall_compliance = EXCLUDED.overall_compliance,
                        avg_overall_passive_pct = EXCLUDED.avg_overall_passive_pct,
                        total_EMA = EXCLUDED.total_EMA,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        study_start_date = EXCLUDED.study_start_date,
                        updated_at = now()
                """), {
                    "pid": rec["id"],
                    "start": start_dt,
                    "end": end_dt,
                    "study_start_date": rec["study_start_date"],
                    "daily_status_list": rec["daily_status_list"],
                    "weekly": rec["weekly_compliance"],
                    "overall": rec["overall_compliance"],
                    "overall_passive": rec["avg_overall_passive_pct"],
                    "total_EMA": rec["total_EMA"]
                })
                
                          
        else:
              for rec in final_response:
                conn.execute(text("""
                    INSERT INTO overall_status_cache 
                    (participant_id, start_date, end_date, study_start_date, daily_status_list, weekly_compliance, overall_compliance,avg_overall_passive_pct, total_EMA, excluded)
                    VALUES 
                    (:pid, :start, :end, :study_start_date, :daily_status_list, :weekly, :overall,:overall_passive, :total_EMA, FALSE)
                    ON CONFLICT (participant_id)
                    DO UPDATE SET 
                        daily_status_list = EXCLUDED.daily_status_list,
                        weekly_compliance = EXCLUDED.weekly_compliance,
                        overall_compliance = EXCLUDED.overall_compliance,
                        avg_overall_passive_pct = EXCLUDED.avg_overall_passive_pct,
                        total_EMA = EXCLUDED.total_EMA,
                        start_date = EXCLUDED.start_date,
                        end_date = EXCLUDED.end_date,
                        study_start_date = EXCLUDED.study_start_date,
                        updated_at = now()
                """), {
                    "pid": rec["id"],
                    "start": start_dt,
                    "end": end_dt,
                    "study_start_date": rec["study_start_date"],
                    "daily_status_list": rec["daily_status_list"],
                    "weekly": rec["weekly_compliance"],
                    "overall": rec["overall_compliance"],
                    "overall_passive": rec["avg_overall_passive_pct"],
                    "total_EMA": rec["total_EMA"]
                })
              
  
    logger.info(f"✅ Cached overall_status for {start_date} → {end_date}")
  




if __name__ == "__main__":

    
    with engine.connect() as conn:
        # Find full range of dates in EMA data
        result = conn.execute(text("""
                  SELECT 
                      MIN(TO_CHAR(date, 'YYYY-MM-DD')) AS start_date,
                      MAX(TO_CHAR(date, 'YYYY-MM-DD')) AS end_date
                  FROM ema_responses_final3
                  WHERE participant_id IS NOT NULL
              """)).mappings().first()

        if not result or not result["start_date"] or not result["end_date"]:
            logger.error("No EMA data found; cannot determine date range.")
            exit(1)

        #start_date = result["start_date"]
        start_date = result["start_date"]
        end_date = result["end_date"]
        
        # The next  lines are just for testing

        participant_filter = sys.argv[1] if len(sys.argv) > 1 else None
        
        
        logger.info(f"📅 Running overall_status for full EMA range: {start_date} → {end_date}")

    # Run the main computation
    get_overall_status(start_date, end_date, participant_filter = participant_filter)

print('finished')
# %%


