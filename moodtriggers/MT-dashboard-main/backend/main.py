# main.py
import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from sqlalchemy import create_engine, text, exc
import logging
from dotenv import load_dotenv
import json
import credentials
from fastapi import BackgroundTasks

from fastapi.responses import FileResponse
import subprocess

import overall_backend 
import tempfile


from Weekly_Email import prepare_email, send_email, get_email, load_participant_data 

import config

# setup/config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

load_dotenv()
app = FastAPI()

##############################
# local = "no"
local = credentials.local
##############################

if local == True:
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3007",
        "http://localhost:8000",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"])
else:
    origins = [
        "http://localhost",
        config.Internal_IP,
        config.Public_IP, 
    ]


# database conn
DB_USER = config.DB_USER
DB_PASSWORD = config.DB_PASSWORD
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
DB_NAME = config.DB_NAME

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# helperfunc
def to_date(d: str) -> datetime:
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

TABLE_MAP = {
    'Location': 'location_final3', 
    'Accelerometer': 'acceleration_final3', 
    'Gyroscope': 'angv_final3', 
    'Battery': 'battery_level_final3',
    'User Survey Responses': 'ema_responses_final3', 
    'Screen Events': 'screen_events_final3',
    'Phone': 'phone_record_final3', 
    'SMS': 'sms_record_final3',
    'App Usage': 'app_usage_final3', 
    'Light': 'illuminance_final3',
}

TYPE_ALIASES = {
    "Location": {"Location"}, 
    "Accelerometer": {"Accelerometer", "Acceleration"},
    "Gyroscope": {"Gyroscope", "AngV"}, 
    "Battery": {"Battery", "Battery Level"},
    "User Survey Responses": {"EMA"}, 
    "Screen Events": {"Screen"},
    "Phone": {"Calls"}, 
    "SMS": {"Texts"}, 
    "App Usage": {"AppUsage"}, 
    "Light": {"Illuminance"},
}
ALIAS_TO_CANON = {alias: canon for canon, aliases in TYPE_ALIASES.items() for alias in aliases}
for canon in TABLE_MAP.keys(): ALIAS_TO_CANON[canon] = canon

def canonicalize_types(requested: str) -> list[str]:
    raw = [t.strip() for t in requested.split(",") if t.strip()]
    return list(dict.fromkeys([ALIAS_TO_CANON.get(t, t) for t in raw]))
    
# api
@app.get("/participants")
def get_participants():
    query = text("SELECT DISTINCT participant_id FROM ema_responses_final3 WHERE participant_id IS NOT NULL ORDER BY participant_id ASC")
    try:
        with engine.connect() as conn:
            res = conn.execute(query).fetchall()
            return [str(row[0]).zfill(5) for row in res]
    except Exception as e:
        logger.error(f"Failed to get participants: {e}")
        raise HTTPException(status_code=500, detail="Could not retrieve participant list.")
 
@app.get("/overall_status")
def get_overall_status(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD")
):
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT participant_id AS id, daily_status_list AS "dailyStatus", 
                       weekly_compliance AS "weeklyCompliance",
                       overall_compliance AS "overallCompliance",
                       avg_overall_passive_pct AS "overallPassive",
                       study_start_date AS study_start_date,
                       start_date, end_date, excluded
                FROM overall_status_cache
                WHERE start_date <= :end AND end_date >= :start
                ORDER BY participant_id
            """), {"start": start_date, "end": end_date}).mappings().all()

        if not result:
            raise HTTPException(status_code=404, detail="No cached data found. Run the backend job first.")

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        full_dates = [(start_dt + timedelta(days=i)).isoformat() for i in range((end_dt - start_dt).days)]
        
        
        # This step might not be needed (but maybe for participants who already finished)
        output = []
        for r in result:
            existing = {d["date"]: d for d in r["dailyStatus"]}
            # fill missing dates
            complete = [
                existing.get(d, {"date": d, "ema_done": False, "passive_data_missing": True})
                for d in full_dates
            ]

            output.append({
                **dict(r),
                "dailyStatus": complete
            })

        return output

    except Exception as e:
        logger.error(f"Error reading from overall_status_cache: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")

@app.get("/sensing_data")
def sensing_data(
    participant_id: str = Query(..., description="Participant ID"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    sensing_types: str = Query(..., description="Comma-separated list")
):
    types_list = canonicalize_types(sensing_types)
    start_dt = to_date(start_date)
    end_dt_excl = to_date(end_date) + timedelta(days=1)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt_excl.timestamp() * 1000)

    days = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_dt_excl - start_dt).days)]
    per_day_data = {day: {"name": day, **{t: None for t in types_list}} for day in days}
    
    pid_filter = "(participant_id::text = :pid OR participant_id::text = ltrim(:pid,'0'))"
    date_filter = "timestamp >= :start_ms AND timestamp < :end_ms"
    
    query_map = { # To do: try test to remove group by d to show all EMA responses
        "Location": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp / 1000.0), 'YYYY-MM-DD') AS d, COUNT(*) as val FROM location_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "User Survey Responses": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, AVG(response) AS val FROM ema_responses_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "Battery": f'SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),\'YYYY-MM-DD\') AS d, AVG("batteryPercent") AS val FROM battery_level_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d',
        "Accelerometer": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, AVG(SQRT(POWER(x,2)+POWER(y,2)+POWER(z,2))) AS val FROM acceleration_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "Gyroscope": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, AVG(SQRT(POWER(x,2)+POWER(y,2)+POWER(z,2))) AS val FROM angv_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "Screen Events": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, COUNT(*) AS val FROM screen_events_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "Phone": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, COUNT(*) AS val FROM phone_record_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "SMS": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, COUNT(*) AS val FROM sms_record_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
        "App Usage": f'SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),\'YYYY-MM-DD\') AS d, SUM("usageDuration") AS val FROM app_usage_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d',
        "Light": f"SELECT TO_CHAR(TO_TIMESTAMP(timestamp/1000.0),'YYYY-MM-DD') AS d, AVG(illuminance) AS val FROM illuminance_final3 WHERE {pid_filter} AND {date_filter} GROUP BY d",
    }
    
    try:
        with engine.connect() as conn:
            for sens_type in types_list:
                if sens_type in query_map:
                    res = conn.execute(text(query_map[sens_type]), {"pid": participant_id, "start_ms": start_ms, "end_ms": end_ms}).mappings().all()
                    for row in res:
                        if row['d'] in per_day_data and row['val'] is not None:
                            per_day_data[row['d']][sens_type] = round(float(row['val']), 2)
        return list(per_day_data.values())
    except Exception as e:
        logger.error(f"/sensing_data failed for {participant_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve sensing data.")


#####################################################################################################################################
# for day level detail per participant
@app.get("/sensing_data_dayDetail")
def sensing_data_dayDetail(
    participant_id: str = Query(..., description="Participant ID"),
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    sensing_types: str = Query(..., description="Comma‑separated list of sensor types"),
):
    """
    Return per‑day, per‑sensor aggregates for the requested participant
    and date range.
    """
    types_list = canonicalize_types(sensing_types)
    start_dt = to_date(start_date)
    end_dt_excl = to_date(end_date) + timedelta(days=1)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms   = int(end_dt_excl.timestamp() * 1000)

    days = [(start_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range((end_dt_excl - start_dt).days)]
    per_day_data = {day: {"name": day, **{t: [] for t in types_list}} for day in days}

    pid_filter = "(participant_id::text = :pid OR participant_id::text = ltrim(:pid,'0'))"
    date_filter = "timestamp >= :start_ms AND timestamp < :end_ms"
    ts_filter = ("date_trunc('hour', to_timestamp(timestamp/1000)) + ( (extract(minute FROM to_timestamp(timestamp/1000))::int / 15) * interval '15 minute') AS ts")

    query_map = {
        "Location": f"SELECT {ts_filter}, AVG(altitude) AS val FROM location_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "User Survey Responses": f"SELECT {ts_filter}, AVG(response) AS val FROM ema_responses_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "Battery": f'SELECT {ts_filter}, AVG("batteryPercent") AS val FROM battery_level_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1',
        "Accelerometer": f'''WITH numbered AS (SELECT timestamp, x, y, z, ROW_NUMBER() OVER (ORDER BY timestamp) AS rn FROM acceleration_final3 WHERE {pid_filter} AND {date_filter})
            SELECT {ts_filter},AVG(SQRT(POWER(x,2) + POWER(y,2) + POWER(z,2))) AS val FROM numbered WHERE rn % 10 = 0 GROUP BY 1''',
        "Gyroscope": f'''WITH numbered AS (SELECT timestamp, x, y, z, ROW_NUMBER() OVER (ORDER BY timestamp) AS rn FROM angv_final3 WHERE {pid_filter} AND {date_filter})
            SELECT {ts_filter},AVG(SQRT(POWER(x,2) + POWER(y,2) + POWER(z,2))) AS val FROM numbered WHERE rn % 10 = 0 GROUP BY 1''',
        "Screen Events": f"SELECT {ts_filter}, COUNT(*) AS val FROM screen_events_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "Phone": f"SELECT {ts_filter}, COUNT(*) AS val FROM phone_record_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "SMS": f"SELECT {ts_filter}, COUNT(*) AS val FROM sms_record_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "App Usage": f'SELECT {ts_filter}, COUNT(*) AS val FROM app_usage_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1',
        "Light": f"SELECT {ts_filter}, AVG(illuminance) AS val FROM illuminance_final3 WHERE {pid_filter} AND {date_filter} GROUP BY 1",
        "All EMA Responses": f'''SELECT TO_TIMESTAMP(timestamp/1000.0) AS ts, 
                "surveyId" AS "surveyId", 
                "questionnaireType" AS "questionnaireType", 
                "questionNumber" AS "questionNumber", 
                "questionText" AS "questionText", 
                response AS "resp"
            FROM ema_responses_final3 WHERE {pid_filter} AND {date_filter} ORDER BY ts''',
    }

    try:
        with engine.connect() as conn:
            for sens_type in types_list:
                sql = query_map.get(sens_type)
                if not sql:
                    continue
                rows = conn.execute(text(sql), {"pid": participant_id, "start_ms": start_ms, "end_ms": end_ms}).mappings().all()
                for row in rows:
                    ts = row.get("ts")
                    if ts is None:
                        continue
                    day = ts.strftime("%Y-%m-%d")
                    # Numeric sensors
                    if "val" in row and sens_type != "All EMA Responses":
                        val = row["val"]
                        if val is not None and isinstance(val, (int, float)):
                            val = round(float(val), 2)
                        per_day_data[day][sens_type].append({"ts": ts.isoformat(), "val": val})
                    # Full EMA response rows
                    elif sens_type == "All EMA Responses":
                        per_day_data[day][sens_type].append({
                            "Timestamp": ts.isoformat(),
                            "SurveyID": row.get("surveyId"),
                            "QuestionnaireType": row.get("questionnaireType"),
                            "QuestionNumber": row.get("questionNumber"),
                            "QuestionText": row.get("questionText"),
                            "Response": row.get("resp"),
                        })
        return list(per_day_data.values())
    except Exception as e:
        logger.error(f"/sensing_data_dayDetail failed for {participant_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve sensing data.")
    
#####################################################################################################################################

@app.get("/export_data")
def export_data(
    participant_id: str = Query(...),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    sensing_types: str = Query(..., description="Comma-separated list of sensor types")
):
    types_to_export = canonicalize_types(sensing_types)
    apply_date_filter = bool(start_date and end_date)
    if apply_date_filter:
        start_dt = to_date(start_date)
        end_dt_exclusive = to_date(end_date) + timedelta(days=1)
        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt_exclusive.timestamp() * 1000)
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        with engine.connect() as conn:
            for data_type in types_to_export:
                table_name = TABLE_MAP.get(data_type)
                if not table_name: continue

                # Base query always filters on participant_id
                base_query = f"""
                    SELECT * FROM {table_name}
                    WHERE (participant_id::text = :pid OR participant_id::text = ltrim(:pid, '0'))
                """
                # Append timestamp filters only if provided
                if apply_date_filter:
                    base_query += " AND timestamp >= :start_ms AND timestamp < :end_ms"
                base_query += " ORDER BY timestamp ASC"
                params = {"pid": participant_id}
                if apply_date_filter:
                    params.update({"start_ms": start_ms, "end_ms": end_ms})
                query = text(base_query)

                try:
                    df = pd.read_sql(query, conn, params=params)
                    if not df.empty:
                        zf.writestr(
                            f"{data_type.lower().replace(' ', '_')}.csv",
                            df.to_csv(index=False),
                        )
                except Exception as e:
                    logger.warning(f"Could not export {data_type}: {e}")

    zip_buffer.seek(0)
    # Filename changes depending on whether timestamps were used
    if apply_date_filter:
        filename = f"export_{participant_id}_{start_date}_to_{end_date}.zip"
    else:
        filename = f"export_{participant_id}_all.zip"
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(zip_buffer, media_type="application/zip", headers=headers)

class ParticipantUpdate(BaseModel):
    old_id: str
    new_id: str

@app.post("/update-participant-id")
def update_participant_id(update: ParticipantUpdate):
    try:
        with engine.begin() as conn:  # automatically commits
            conn.execute(
                text("SELECT update_participant_id_optimized(:old_value, :new_value)"),
                {"old_value": update.old_id, "new_value": update.new_id}
            )
      
        # Run immediately 
        overall_backend.get_overall_status(
            start_date="2020-01-01",
            end_date=datetime.now().strftime("%Y-%m-%d"),
            participant_filter = [update.new_id]
        )
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
      
      
class ParticipantExcludeUpdate(BaseModel):
    participant_id: str
    excluded: bool


@app.post("/update-participant-exclude")
def update_participant_exclude(update: ParticipantExcludeUpdate):
    try:
        with engine.begin() as conn:
        
            # Now update the participant's flag
            res = conn.execute(
                text("""
                    UPDATE overall_status_cache
                    SET excluded = :excluded,
                        updated_at = now()
                    WHERE participant_id = :pid
                """),
                {"excluded": update.excluded, "pid": update.participant_id}
            )

            # Check if any row was updated
            if res.rowcount == 0:
                raise HTTPException(status_code=404, detail="Participant not found")

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# participant summary screen
@app.get("/participant_summary")
def participant_summary(
    participant_id: str = Query(...),
):

    pid_filter = "(participant_id::text = :pid OR participant_id::text = ltrim(:pid,'0'))"

    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(f"""
                    SELECT
                        participant_id,
                        study_start_date,
                        daily_status_list
                    FROM overall_status_cache
                    WHERE {pid_filter}
                """),
                {"pid": participant_id},
            ).mappings().first()
         
        if not row:
            raise HTTPException(
                status_code=404,
                detail="No cached participant summary found."
            )
        
        daily_status = row["daily_status_list"]
        study_start_date = row["study_start_date"]
        if isinstance(study_start_date, datetime):
            study_start_date = study_start_date.date()

        summary = [
            {
                "pid": participant_id,
                "study_start_date": study_start_date.isoformat(),
                **d,   # include ALL components without knowing them
            }
            for d in daily_status
            if (
                isinstance(d, dict)
                and "date" in d
                and datetime.strptime(d["date"], "%Y-%m-%d").date() >= study_start_date
            )
        ]

        return summary 

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"participant_summary failed: {e}", exc_info=True)
        raise HTTPException(500, "Failed to retrieve participant summary.")
      



#### Email add ons (Anna)

@app.get("/unique_participants_email")
async def get_unique_participants():
    df = load_participant_data()  # This should return your fully expanded participant dataframe
    return df['participant_id'].unique().tolist()

class EmailPreview(BaseModel):
    html: str

@app.get("/preview_email", response_model=EmailPreview)
async def preview_email(participant_id: str):
    df = load_participant_data()
    
    # Fetch first name and email from RedCap
    first_name, _ = get_email(participant_id, credentials.RedCap_token)
    
    html = prepare_email(participant_id, first_name, df)
    return {"html": html}
  
  
class SendEmailRequest(BaseModel):
    participant_id: str

@app.post("/send_email")
async def send_email_endpoint(request: SendEmailRequest):
    participant_id = request.participant_id

    df = load_participant_data()
    first_name, emailadr = get_email(participant_id, credentials.RedCap_token)

    html = prepare_email(participant_id, first_name, df)
    
    email_sender = config.email_sender
    email_cc = config.email_cc
    email_password = credentials.email_password
    email_receiver = emailadr
    #email_receiver = 'langener95@gmail.com' # I PUT MY OWN EMAIL FOR TESTING, THIS WILL BE REPLACED 
    subject = config.subject

    send_email(
        email_sender,
        email_receiver,
        email_cc,
        subject,
        html,
        email_password,
        is_html=True
    )

    return {"status": "success", "participant_id": participant_id}
  
  
  
#### Report Builder



def render_rmd_to_stream(rmd_file: str, output_filename: str, env_vars: dict = None):
    """
    Renders an R Markdown file to a temporary .docx file and returns a StreamingResponse.
    """
    env = os.environ.copy()
    if env_vars:
        env.update(env_vars)

    tmp_file = tempfile.NamedTemporaryFile(suffix=".docx")
    try:
        subprocess.run(
            [
                "Rscript",
                "-e",
                f"rmarkdown::render('{rmd_file}', output_file='{tmp_file.name}')"
            ],
            check=True,
            env=env
        )
    except subprocess.CalledProcessError as e:
        tmp_file.close()
        raise HTTPException(status_code=500, detail=f"R Markdown failed: {e.stderr}")

    tmp_file.seek(0)
    return StreamingResponse(
        tmp_file,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={output_filename}"}
    )


@app.get("/compensation-report/{participant_number}")
def compensation_report(participant_number: str, google_takeout: bool = Query(False)):
    RMD_FILE = "/var/www/MoodTriggersDashboardv2/Reports/Compensation_Report.Rmd"
    output_filename = f"Compensation_Report_{participant_number}.docx"
    env_vars = {
        "PARTICIPANT_NUMBER": participant_number,
        "GOOGLE_TAKEOUT": "TRUE" if google_takeout else "FALSE"
    }
    return render_rmd_to_stream(RMD_FILE, output_filename, env_vars)


@app.get("/feedback-report/{participant_number}")
def feedback_report(participant_number: str):
    RMD_FILE = "/var/www/MoodTriggersDashboardv2/Reports/Feedback_Report.Rmd"
    output_filename = f"Feedback_Report_{participant_number}.docx"
    env_vars = {"PARTICIPANT_NUMBER": participant_number}
    return render_rmd_to_stream(RMD_FILE, output_filename, env_vars)
  
  
