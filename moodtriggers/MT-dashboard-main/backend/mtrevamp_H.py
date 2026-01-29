
import io
import os
# import requests
import tempfile
import pyrebase
import zipfile
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime
import re
from sqlalchemy import text
import json
from sqlalchemy.engine import Engine

from typing import Optional, Dict, List, Tuple
from sqlalchemy import create_engine, text
from sqlalchemy import types as satypes

import ijson
from typing import Generator

import gc

from credentials import firebase_config
import config

import os, re, json, zipfile, tempfile, time
from typing import Optional, List, Tuple, Dict

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# config
STORAGE = firebase_config()
BUCKET = getattr(STORAGE, "bucket_name", None)
if BUCKET:
    print(f"Using bucket name: {BUCKET}")


DB_USER = config.DB_USER
DB_PASSWORD = config.DB_PASSWORD
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
DB_NAME = config.DB_NAME


PG_DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine: Engine = create_engine(PG_DSN, pool_pre_ping=True)

MT_CHUNKSIZE = int(os.environ.get("MT_CHUNKSIZE", "5000"))
MT_BASE_PREFIX = config.MT_BASE_PREFIX

# helper
def ensure_connection() -> bool:
    try:
        with engine.connect() as conn:
            dbname = conn.execute(text("SELECT current_database();")).scalar()
            user = conn.execute(text("SELECT current_user;")).scalar()
            print(f"Connected to DB: {dbname} as user: {user}")
        return True
    except Exception as e:
        print(f"DB connection failed: {e}")
        return False

def _as_series(x, length: int) -> pd.Series:
    if isinstance(x, pd.Series): return x
    return pd.Series([x] * max(1, length))

def _to_py_int_series(num_like) -> pd.Series:
    # coerce
    s = num_like if isinstance(num_like, pd.Series) else pd.Series(num_like)
    s = pd.to_numeric(s, errors="coerce")
    return s.map(lambda v: None if pd.isna(v) else int(v)).astype("object")

def to_int_ms(series_like) -> pd.Series:
    s = series_like if isinstance(series_like, pd.Series) else _as_series(series_like, 1)
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        return _to_py_int_series(num)
    dt = pd.to_datetime(s, errors="coerce")
    if dt.notna().any():
        if len(dt) == 0: return pd.Series([], dtype="object")
        ms = (dt.view("int64") // 10**6)
        return _to_py_int_series(ms)
    return pd.Series([None] * len(s), dtype="object")

def to_float(series_like) -> pd.Series:
    s = series_like if isinstance(series_like, pd.Series) else _as_series(series_like, 1)
    return pd.to_numeric(s, errors="coerce")

def force_pid(df: pd.DataFrame, pid: Optional[str]) -> pd.DataFrame:
    df["participant_id"] = str(pid) if pid is not None else None
    return df

def to_tz_aware_datetime(series_like, utc) -> pd.Series:
    """
    Parse a Series/array-like of date strings into pandas datetimes.

    Parameters
    - series_like: pd.Series or array-like of date strings
    - utc: bool, required. If True, results are converted to UTC (tz-aware, dtype datetime64[ns, UTC]).
           If False, offsets in the input are preserved (tz-aware) and strings without offsets produce naive datetimes.

    Returns
    - pd.Series of Timestamps (or NaT for parse failures)
    """
    if not isinstance(utc, bool):
        raise TypeError("utc must be a bool (True or False)")
    
    dates = series_like if isinstance(series_like, pd.Series) else _as_series(series_like, 1)

    # normalize strings:
    clean = (
        dates
        .astype(str)
        .str.replace(r'\s*\([A-Za-z]{2,}\)\s*$', '', regex=True)            # drop "(PDT)" etc.
        .str.replace(r'(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})', r'\1T\2', regex=True)  # make " " -> "T" between date/time
        .str.replace(r'\s+([+-])', r'\1', regex=True)                        # remove space before +/-
        .str.replace(r'([+-])(\d):', r'\g<1>0\2:', regex=True)               # pad single-digit hour -> "-07:"
        .str.replace(r'([+-]\d{2}:\d{2}):\d{2}(?:\.\d+)?$', r'\1', regex=True)  # drop seconds/microsecs in offset -> keep ±HH:MM
        .str.strip()
    )

    # Try different timestamp formats
    fmt_with_us = "%Y-%m-%dT%H:%M:%S.%f%z"
    fmt_no_us = "%Y-%m-%dT%H:%M:%S%z"
    fmt_no_tz = "%Y-%m-%dT%H:%M:%S.%f"
    fmt_noUs_no_tz = "%Y-%m-%dT%H:%M:%S"

    # microseconds + timezone
    ts = pd.to_datetime(clean, format=fmt_with_us, errors="coerce", utc=utc)
    # seconds + timezone
    mask = ts.isna()
    if mask.any():
        ts_s = pd.to_datetime(clean[mask], format=fmt_no_us, errors="coerce", utc=utc)
        ts.loc[mask] = ts_s
    
    # do not return utc date with timestamp value if there is no timezone
    if utc:
        return ts
    
    # microseconds only
    mask = ts.isna()
    if mask.any():
        ts_ms_noTz = pd.to_datetime(clean[mask], format=fmt_no_tz, errors="coerce")
        ts.loc[mask] = ts_ms_noTz
    # seconds only
    mask = ts.isna()
    if mask.any():
        ts_s_noTz = pd.to_datetime(clean[mask], format=fmt_noUs_no_tz, errors="coerce")
        ts.loc[mask] = ts_s_noTz
    
    ts_naive = ts.apply(lambda t: t.tz_localize(None) if hasattr(t, 'tz_localize') and t.tzinfo else t)
    return ts_naive

def to_timezone(series_like) -> pd.Series:
    s = series_like if isinstance(series_like, pd.Series) else _as_series(series_like, 1)
    return s.str.extract(r'\s([+-]?\d{1,2}):')[0].astype(float) # get hour of timezone as int

def expand_data_column(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    w = df.copy()
    if "data" in w.columns and w["data"].astype(str).str.startswith("[").any():
        # explode stringified array
        rows = []
        for _, r in w.iterrows():
            try:
                arr = json.loads(r["data"]) if pd.notna(r["data"]) else []
            except Exception:
                arr = []
            for pt in arr:
                rows.append({
                    **pt,
                })   
        w = pd.DataFrame(rows)
    return w

def extract_pid_from_path(path: str) -> Optional[str]:
    m = re.search(rf"{re.escape(config.MT_BASE_PREFIX)}([^/]+)/", path)
    return m.group(1) if m else None

# parsers
def parse_battery(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame()
    vals = pd.to_numeric(w.get("batteryPercent"), errors="coerce")
    out["batteryPercent"] = _to_py_int_series(vals.round())
    out["timestamp"] = to_int_ms(w.get("timestamp"))
    out["raw_date"] = w.get("date").astype(str)
    out["date"] = to_tz_aware_datetime(w.get("date"), utc=False)
    out["date_utc"] = to_tz_aware_datetime(w.get("date"), utc=True)
    out['timezone'] = to_timezone(w.get("date"))
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_angv(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "x": to_float(w.get("x")), "y": to_float(w.get("y")), "z": to_float(w.get("z")),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_accel(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "x": to_float(w.get("x")), "y": to_float(w.get("y")), "z": to_float(w.get("z")),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

import json
import pandas as pd
import numpy as np

def _to_ms(ts_series: pd.Series) -> pd.Series:
    """ mixed timestamps (ISO strings / seconds / ms) → int ms."""
    if ts_series is None:
        return pd.Series(dtype="Int64")
    s = ts_series.copy()

    #  detect sec vs ms
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any():
        ms = num.copy()
        # treat < 1e12 as seconds
        ms = np.where(ms < 1_000_000_000_000, ms * 1000, ms)
        return pd.Series(ms).astype("Int64")

    #  parse as datetimes
    dt = pd.to_datetime(s, errors="coerce")
    return (dt.astype("int64") // 1_000_000).astype("Int64")  # ns→ms

def parse_location(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = df.copy()
    w = expand_data_column(df)

    # coerce columns to numeric or float(NaN)
    for col in ["latitude","longitude","accuracy","altitude",
                "altitudeAccuracy","speed","speedAccuracy","heading"]:
        if col in w.columns:
            w[col] = pd.to_numeric(w[col], errors="coerce")
    # clean
    w.dropna(subset=["timestamp","latitude","longitude"], inplace=True)
    w.drop_duplicates(subset=["timestamp","latitude","longitude"],inplace=True)
    # return w

    # -flat shape (pick first value from cols of similar names)
    cand_lat = [c for c in w.columns if c.lower() in {"latitude","lat"}]
    cand_lon = [c for c in w.columns if c.lower() in {"longitude","lon","lng"}]
    cand_ts  = [c for c in w.columns if c.lower() in {"timestamp","time","created_at","recorded_at","date"}]

    lat = w[cand_lat[0]] if cand_lat else pd.Series(dtype=float)
    lon = w[cand_lon[0]] if cand_lon else pd.Series(dtype=float)
    ts  = w[cand_ts[0]]  if cand_ts  else pd.Series(dtype=object)

    out = pd.DataFrame({
        # "participant_id": pid,
        "timestamp": to_int_ms(w.get("timestamp")),
        "latitude": pd.to_numeric(lat, errors="coerce"),
        "longitude": pd.to_numeric(lon, errors="coerce"),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })

    # extras if there
    for src, dst in [
        ("accuracy","accuracy"), ("altitude","altitude"),
        ("altitudeAccuracy","altitudeAccuracy"),
        ("speed","speed"), ("speedAccuracy","speedAccuracy"),
        ("heading","heading")
    ]:
        if src in w.columns:
            out[dst] = pd.to_numeric(w[src], errors="coerce")

    out.dropna(subset=["timestamp","latitude","longitude"], inplace=True)
 
    return force_pid(out, pid)
                     
def parse_ema(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({"response": to_float(w.get("response")),
                        "timestamp": to_int_ms(w.get("timestamp")),
                        "surveyId": _to_py_int_series(w.get("surveyId")),
                        "questionNumber":  _to_py_int_series(w.get("questionNumber")),
                        "questionnaireType": w.get("questionnaireType") if "questionnaireType" in w.columns else _as_series(None, len(w)),
                        "questionText": w.get("questionText"),
                        "raw_date": w.get("date").astype(str),
                        "date": to_tz_aware_datetime(w.get("date"), utc=False),
                        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
                        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)


def parse_screen_event(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "screenState": w.get("screenState") if "screenState" in w.columns else _as_series(None, len(w)),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_phone_record(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "hashedPhoneNumber": w.get("hashedPhoneNumber") if "hashedPhoneNumber" in w.columns else _as_series(None, len(w)),
        "callType": w.get("callType") if "callType" in w.columns else _as_series(None, len(w)),
        "duration": _to_py_int_series(w.get("duration")) if "duration" in w.columns else _to_py_int_series(pd.Series([None]*len(w))),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_sms_record(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "messageId": _to_py_int_series(w.get("messageId")) if "messageId" in w.columns else _to_py_int_series(pd.Series([None]*len(w))),
        "hashedPhoneNumber": w.get("hashedPhoneNumber") if "hashedPhoneNumber" in w.columns else _as_series(None, len(w)),
        "type": w.get("type") if "type" in w.columns else _as_series(None, len(w)),
        "length": _to_py_int_series(w.get("length")) if "length" in w.columns else _to_py_int_series(pd.Series([None]*len(w))),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_light_sensor(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    illum_key = None
    for cand in ["illuminance","lux","light","value"]:
        if cand in w.columns:
            illum_key = cand; break
    out = pd.DataFrame({
        "illuminance": to_float(w.get(illum_key)) if illum_key else _as_series(None, len(w)),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)

def parse_app_usage(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    w = expand_data_column(df)
    out = pd.DataFrame({
        "packageName": w.get("packageName") if "packageName" in w.columns else _as_series(None, len(w)),
        "usageDuration": to_float(w.get("usageDuration")),
        "timestamp": to_int_ms(w.get("timestamp")),
        "raw_date": w.get("date").astype(str),
        "date": to_tz_aware_datetime(w.get("date"), utc=False),
        "date_utc": to_tz_aware_datetime(w.get("date"), utc=True),
        "timezone": to_timezone(w.get("date"))
    })
    out.dropna(subset=["timestamp"], inplace=True)
    return force_pid(out, pid)


TABLES: Dict[str, str] = {
    "zip_log_final3": "combined_id TEXT PRIMARY KEY, folder_name TEXT, zip_name TEXT",
    "battery_level_final3": 'participant_id TEXT, "batteryPercent" INTEGER, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "location_final3": 'participant_id TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, accuracy DOUBLE PRECISION NULL, altitude DOUBLE PRECISION NULL, "altitudeAccuracy" DOUBLE PRECISION NULL, speed DOUBLE PRECISION NULL, "speedAccuracy" DOUBLE PRECISION NULL, heading DOUBLE PRECISION NULL, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "angv_final3": "participant_id TEXT, x DOUBLE PRECISION, y DOUBLE PRECISION, z DOUBLE PRECISION, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER",
    "acceleration_final3": "participant_id TEXT, x DOUBLE PRECISION, y DOUBLE PRECISION, z DOUBLE PRECISION, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER",
    "ema_responses_final3": 'participant_id TEXT, "surveyId" INTEGER, "questionnaireType" TEXT, "questionNumber" INTEGER, "questionText" TEXT, response DOUBLE PRECISION NULL, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER, timestamp BIGINT',
    "screen_events_final3": 'participant_id TEXT, "screenState" TEXT, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "phone_record_final3": 'participant_id TEXT, "hashedPhoneNumber" TEXT, "callType" TEXT, duration INTEGER, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "sms_record_final3": 'participant_id TEXT, "messageId" BIGINT, "hashedPhoneNumber" TEXT, "type" TEXT, length INTEGER, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "illuminance_final3": 'participant_id TEXT, illuminance DOUBLE PRECISION, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
    "app_usage_final3": 'participant_id TEXT, "packageName" TEXT, "usageDuration" DOUBLE PRECISION, timestamp BIGINT, raw_date TEXT NULL, date TIMESTAMP NULL, date_utc TIMESTAMP NULL, timezone INTEGER',
}

#  Index definitions – one (or two) per table
# -----------------------------------------------------------------
#   * pid_ts_idx   – composite (participant_id, timestamp)
#   * bucket_idx   – expression index on the 15‑minute bucket
# -----------------------------------------------------------------
INDEX_DEFS: Dict[str, list[str]] = {
    "battery_level_final3": ["CREATE INDEX IF NOT EXISTS ix_battery_level_final3_pid_ts ON battery_level_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_battery_level_final3_bucket " "ON battery_level_final3 ((timestamp/1000/900));",],
    "location_final3": ["CREATE INDEX IF NOT EXISTS ix_location_final3_pid_ts ON location_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_location_final3_bucket ON location_final3 ((timestamp/1000/900));",],
    "angv_final3": ["CREATE INDEX IF NOT EXISTS ix_angv_final3_pid_ts ON angv_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_angv_final3_bucket ON angv_final3 ((timestamp/1000/900));",],
    "acceleration_final3": ["CREATE INDEX IF NOT EXISTS ix_acceleration_final3_pid_ts ON acceleration_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_acceleration_final3_bucket ON acceleration_final3 ((timestamp/1000/900));",],
    "screen_events_final3": ["CREATE INDEX IF NOT EXISTS ix_screen_events_final3_pid_ts ON screen_events_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_screen_events_final3_bucket ON screen_events_final3 ((timestamp/1000/900));",],
    "phone_record_final3": ["CREATE INDEX IF NOT EXISTS ix_phone_record_final3_pid_ts ON phone_record_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_phone_record_final3_bucket ON phone_record_final3 ((timestamp/1000/900));",],
    "sms_record_final3": ["CREATE INDEX IF NOT EXISTS ix_sms_record_final3_pid_ts ON sms_record_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_sms_record_final3_bucket ON sms_record_final3 ((timestamp/1000/900));",],
    "illuminance_final3": ["CREATE INDEX IF NOT EXISTS ix_illuminance_final3_pid_ts ON illuminance_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_illuminance_final3_bucket ON illuminance_final3 ((timestamp/1000/900));",],
    "app_usage_final3": ["CREATE INDEX IF NOT EXISTS ix_app_usage_final3_pid_ts ON app_usage_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_app_usage_final3_bucket ON app_usage_final3 ((timestamp/1000/900));",],
    "ema_responses_final3": ["CREATE INDEX IF NOT EXISTS ix_ema_responses_final3_pid_ts ON ema_responses_final3 (participant_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS ix_ema_responses_final3_bucket ON ema_responses_final3 ((timestamp/1000/900));",],
    "zip_log_final3": [],   
}

def create_tables_if_needed():
    with engine.begin() as conn:
        for tname, cols in TABLES.items():
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS public."{tname}" ({cols});'))
        for tname, statements in INDEX_DEFS.items():
            for stmt in statements:
                conn.execute(text(stmt))


### The next code is only for replacing IDs/ Updating old IDs
with engine.begin() as conn:
    conn.execute(text("""
    DO $block$
    DECLARE
        r RECORD;
    BEGIN
        FOR r IN
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name = 'participant_id'
              AND table_schema = 'public'
        LOOP
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = r.table_schema
                  AND table_name = r.table_name
                  AND column_name = 'old_id'
            ) THEN
                EXECUTE format(
                    'ALTER TABLE %I.%I ADD COLUMN old_id TEXT;',
                    r.table_schema, r.table_name
                );
            END IF;
        END LOOP;
    END;
    $block$;
    """))


    # 2. Add participant_id indexes only if at least one is missing
    conn.execute(text("""
    DO $$
    DECLARE
        r RECORD;
        missing_count INT;
    BEGIN
        -- Check how many tables lack the participant_id index
        SELECT COUNT(*) INTO missing_count
        FROM information_schema.columns c
        WHERE c.column_name = 'participant_id'
          AND c.table_schema = 'public'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_indexes pi
              WHERE pi.schemaname = c.table_schema
                AND pi.tablename = c.table_name
                AND pi.indexname = 'idx_' || c.table_name || '_participant_id'
          );

        IF missing_count = 0 THEN
            RAISE NOTICE 'All participant_id indexes already exist. Skipping index creation.';
            RETURN;
        END IF;

        -- Add missing indexes
        FOR r IN
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name = 'participant_id'
              AND table_schema = 'public'
        LOOP
            BEGIN
                EXECUTE format(
                    'CREATE INDEX IF NOT EXISTS idx_%I_participant_id ON %I.%I(participant_id);',
                    r.table_name, r.table_schema, r.table_name
                );
                RAISE NOTICE 'Index created or exists on table: %.%', r.table_schema, r.table_name;
            EXCEPTION WHEN OTHERS THEN
                RAISE NOTICE 'Could not create index on %.%', r.table_schema, r.table_name;
            END;
        END LOOP;
    
      END $$;
      """))

    # Create update_participant_id_optimized function
    conn.execute(text("""
    CREATE OR REPLACE FUNCTION update_participant_id_optimized(
        old_value TEXT,
        new_value TEXT
    )
    RETURNS VOID AS $$
    DECLARE
        r RECORD;
        sql TEXT;
        count_matches INT;
    BEGIN
        -- 1) Update participant_id in all relevant tables
        FOR r IN
            SELECT table_schema, table_name
            FROM information_schema.columns
            WHERE column_name = 'participant_id'
              AND table_schema = 'public'
              AND table_name NOT IN ('zip_log_final3', 'overall_status_cache')  
        LOOP
            -- Check for matches before updating
            sql := format('SELECT COUNT(*) FROM %I.%I WHERE participant_id = $1;', 
                          r.table_schema, r.table_name);
    
            EXECUTE sql INTO count_matches USING old_value;
    
            IF count_matches > 0 THEN
                sql := format(
                    'UPDATE %I.%I
                     SET old_id = COALESCE(old_id, participant_id),
                         participant_id = $1
                     WHERE participant_id = $2;',
                    r.table_schema, r.table_name
                );
                EXECUTE sql USING new_value, old_value;
    
                RAISE NOTICE 'Updated table %.% (% rows affected)', 
                             r.table_schema, r.table_name, count_matches;
            END IF;
        END LOOP;
    
        -- 2) Remove old cached status entries
        DELETE FROM overall_status_cache
        WHERE participant_id IN (old_value, new_value);
    
        RAISE NOTICE 'Removed old overall_status_cache rows for %', old_value;
    
    END;
    $$ LANGUAGE plpgsql;
            """))

    # Create trigger function to update all new data that comes in
    conn.execute(text("""
        CREATE OR REPLACE FUNCTION apply_participant_id_mapping_trigger()
        RETURNS TRIGGER AS $$
        DECLARE
            mapped_id TEXT;
        BEGIN
            IF NEW.participant_id IS NOT NULL THEN
                SELECT new_id INTO mapped_id
                FROM participant_id_mapping
                WHERE old_id = NEW.participant_id
                LIMIT 1;  -- ensure only one row
               
                -- Only update if mapping exists
                IF mapped_id IS NOT NULL THEN
                    NEW.participant_id := mapped_id;
                END IF;
            END IF;
        
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

    """))
    
    SKIP_TRIGGER_TABLES = {
        "zip_log_final3",
        "participant_id_mapping",
        'overall_status_cache'
    }

    # Create triggers for all tables
    for tname in TABLES.keys():

      if tname in SKIP_TRIGGER_TABLES:
          continue  # skip
      
          conn.execute(text(f"""
              DO $$
              BEGIN
                  IF NOT EXISTS (
                      SELECT 1 FROM pg_trigger
                      WHERE tgname = 'trigger_{tname}_before_insert'
                  ) THEN
                      CREATE TRIGGER trigger_{tname}_before_insert
                      BEFORE INSERT ON "{tname}"
                      FOR EACH ROW
                      EXECUTE FUNCTION apply_participant_id_mapping_trigger();
                  END IF;
              END;
              $$;
          """))

def zip_already_done(full_path: str) -> bool:
    with engine.begin() as conn:
        return conn.execute(text('SELECT 1 FROM "zip_log_final3" WHERE combined_id=:cid'),
                            {"cid": full_path}).first() is not None

def log_zip(full_path: str):
    with engine.begin() as conn:
        conn.execute(
            text('INSERT INTO "zip_log_final3" (combined_id, folder_name, zip_name) VALUES (:cid, :folder, :zip) ON CONFLICT (combined_id) DO NOTHING'),
            {"cid": full_path, "folder": os.path.dirname(full_path), "zip": os.path.basename(full_path)}
        )

# routers
HANDLERS = {
    "parse_ema": parse_ema,
    "parse_battery": parse_battery,
    "parse_location": parse_location,
    "parse_angv": parse_angv,
    "parse_accel": parse_accel,
    "parse_screen_event": parse_screen_event,
    "parse_phone_record": parse_phone_record,
    "parse_sms_record": parse_sms_record,
    "parse_light_sensor": parse_light_sensor,
    "parse_app_usage": parse_app_usage,
}
USR = r"(?:user_sensor_datas_)?"
ROUTES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(rf"{USR}(ema_responses|user_survey_responses)\.json$", re.I), "ema_responses_final3", "parse_ema"),
    (re.compile(rf"{USR}battery_level(_sample)?\.json$", re.I), "battery_level_final3", "parse_battery"),
    (re.compile(rf"{USR}location(_sample)?\.json$", re.I), "location_final3", "parse_location"),
    (re.compile(rf"{USR}(angular_velocity|angv)(_sample)?\.json$", re.I), "angv_final3", "parse_angv"),
    (re.compile(rf"{USR}acceleration(_sample)?\.json$", re.I), "acceleration_final3", "parse_accel"),
    (re.compile(rf"{USR}screen_event\.json$", re.I), "screen_events_final3", "parse_screen_event"),
    (re.compile(rf"{USR}phone_record\.json$", re.I), "phone_record_final3", "parse_phone_record"),
    (re.compile(rf"{USR}sms_record\.json$", re.I), "sms_record_final3", "parse_sms_record"),
    (re.compile(rf"{USR}(illuminance|light|light_sensor)(_sample)?\.json$", re.I), "illuminance_final3", "parse_light_sensor"),
    (re.compile(rf"{USR}app_usage_record\.json$", re.I), "app_usage_final3", "parse_app_usage"),
]

def route_for(name: str) -> Optional[Tuple[str, str]]:
    base = os.path.basename(name)
    for rx, table, handler in ROUTES:
        if rx.search(base): return (table, handler)
    return None

def _select_single_ema(inner_jsons: List[str]) -> Optional[str]:
    """
    Return exactly one EMA file path from inner_jsons, preferring user_survey_responses.json.#AL: I changed the order, if both are present ema_response needs to be preferred
    """
    usr = None
    ema = None
    for p in inner_jsons:
        lp = p.lower()
        if lp.endswith("ema_responses.json"):
            usr = p
            break
        if lp.endswith("user_survey_responses.json"):
            ema = p
    return usr or ema

      
def read_json_from_zip(zf: zipfile.ZipFile, inner_path: str, chunk_size: int = 100000) -> Generator[pd.DataFrame, None, None]:
    """
    Stream a JSON array from a zip file, yielding DataFrames in chunks.
    """
    try:
        rows = []
        with zf.open(inner_path) as fp:
            for item in ijson.items(fp, "item"):
                rows.append(item)
                if len(rows) >= chunk_size:
                    yield pd.DataFrame(rows)
                    rows = []
            if rows:
                yield pd.DataFrame(rows)
    except Exception as e:
        print(f"  ! Could not read {inner_path}: {e}")
        

def process_zip(storage_path: str):
    pid = extract_pid_from_path(storage_path)
    if not pid:
        print(f"Skipping {storage_path}: cannot determine participant id")
        return
    if zip_already_done(storage_path):
        print(f"Already processed: {storage_path}")
        return

    print(f"\n- Processing {storage_path} (PID {pid}) -")
    tmpfile = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmpfile = tmp.name
        print(f"Downloading to temp: {tmpfile}")
       
        try:
            STORAGE.download(path=storage_path, filename=tmpfile)
        except TypeError:
            try:
                STORAGE.download(storage_path, tmpfile)
            except:
                STORAGE.child(storage_path).download(tmpfile)

        print(f"Download complete: {os.path.getsize(tmpfile)} bytes")

        with zipfile.ZipFile(tmpfile, "r") as zf:
            all_names = zf.namelist()
            inner_jsons = [n for n in all_names if n.lower().endswith(".json")]
            print(f"Zip contains {len(all_names)} entries; JSON files: {len(inner_jsons)}")
            if not inner_jsons:
                log_zip(storage_path); return

            selected_ema = _select_single_ema(inner_jsons)

            for inner in inner_jsons:
                lower_inner = inner.lower()
                # enforce single EMA per zip
                if (lower_inner.endswith("user_survey_responses.json") or lower_inner.endswith("ema_responses.json")) and inner != selected_ema:
                    print(f"skipping (EMA not selected this zip): {inner}")
                    continue

                routed = route_for(inner)
                if not routed:
                    print(f"skipping (no route): {inner}")
                    continue

                table, handler_name = routed
                parser = HANDLERS[handler_name]
                print(f"route: {inner} -> {table} via {handler_name}")
                
                
                # Changed this because of memory issues
                for chunk_df in read_json_from_zip(zf, inner, chunk_size=100000):
                    if chunk_df.empty:
                        continue
                    parsed = parser(pid, chunk_df)
                    if parsed.empty:
                        continue
                    parsed.to_sql(table, engine, if_exists="append", index=False, method="multi", chunksize=MT_CHUNKSIZE)
                    print(f"INSERTED {len(parsed)} rows into {table}")
                    
                    del chunk_df, parsed
                    gc.collect()

        log_zip(storage_path)
        print("logged zip as processed")

    except Exception as e:
        print(f"Failed processing {storage_path}: {e}")
    finally:
        if tmpfile and os.path.exists(tmpfile):
            try:
                os.remove(tmpfile); print("temp file removed")
            except Exception:
                print("temp file cleanup failed")

# main
if __name__ == "__main__":
    print("Starting ingestion script...")
    if not ensure_connection(): raise SystemExit(1)
    print("Ensuring tables exist...")
    create_tables_if_needed()

    if not STORAGE or not hasattr(STORAGE, "list_files"):
        print("STORAGE object not configured.")
        raise SystemExit(1)

    print(f"Streaming zips under prefix: {MT_BASE_PREFIX} (processing)")
    seen = 0
    heartbeat_at = time.time() + 10  # heartbeat in 10s if nothing arrives
    
    try:
        # Prefer server-side prefix filtering if supported
        try:
            iterator = STORAGE.list_files(prefix=MT_BASE_PREFIX)
        except TypeError:
            iterator = STORAGE.list_files()
        
        blobs = list(iterator)
    
        for obj in reversed(blobs):
            name = getattr(obj, "name", "")
            if not (name.startswith(MT_BASE_PREFIX) and name.endswith(".zip") and "/logs/" not in name):
                if time.time() >= heartbeat_at:
                    print("  …still listing, no zips yielded yet")
                    heartbeat_at = time.time() + 10
                continue

            seen += 1
            print(f"▶️  [{seen}] {name}")
            process_zip(name)
            
    except Exception as e:
        print(f"Error during streaming processing: {e}")

    print("\n- Ingestion finished -")
    
