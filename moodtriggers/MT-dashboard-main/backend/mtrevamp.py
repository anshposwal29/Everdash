
import io
import os
import requests
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
import credentials

# --- Database Connection Details (EASY TO CHANGE) ---
DB_USER = credentials.DB_USER
print(DB_USER)
DB_PASSWORD = credentials.DB_PASSWORD
print(DB_PASSWORD)
DB_HOST = credentials.DB_HOST
DB_PORT = credentials.DB_PORT
DB_NAME = credentials.DB_NAME

STORAGE = credentials.firebase_config()


import pandas as pd
from pandas import Int64Dtype
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine



engine: Engine = create_engine(
    "postgresql://hannah:moodtriggers2025@localhost:5432/moodtriggers",
    pool_pre_ping=True,
)


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
    return pd.Series([x] * length)

def _to_py_int_series(num_like) -> pd.Series:
    s = pd.to_numeric(num_like, errors="coerce")
    return s.map(lambda v: None if pd.isna(v) else int(v)).astype("object")

def to_int_ms(series_like) -> pd.Series:
    s = series_like if isinstance(series_like, pd.Series) else _as_series(series_like, 1)
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().any(): return _to_py_int_series(num)
    dt = pd.to_datetime(s.str[:23], errors="coerce", utc=True)
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

# JSON nest
def expand_data_column(df: pd.DataFrame) -> pd.DataFrame:
    if "data" not in df.columns:
        return df
    
    all_readings = []
    for json_string in df["data"]:
        try:
            readings = json.loads(json_string)
            if isinstance(readings, list):
                all_readings.extend(r for r in readings if isinstance(r, dict))
        except (json.JSONDecodeError, TypeError):
            continue
            
    return pd.DataFrame(all_readings) if all_readings else df

# parse it
def parse_battery(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    work_df = expand_data_column(df)
    out = pd.DataFrame()
    vals = pd.to_numeric(work_df.get("batteryPercent"), errors="coerce")
    out["batteryPercent"] = _to_py_int_series(vals.round())
    out["timestamp"] = to_int_ms(work_df.get("timestamp"))
    out["date"] = pd.to_datetime(work_df.get("date").str[:23], errors="coerce", utc=True)
    out.dropna(subset=['timestamp'], inplace=True)
    return force_pid(out, pid)

def parse_angv(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    work_df = expand_data_column(df)
    out = pd.DataFrame()
    out["x"] = to_float(work_df.get("x"))
    out["y"] = to_float(work_df.get("y"))
    out["z"] = to_float(work_df.get("z"))
    out["timestamp"] = to_int_ms(work_df.get("timestamp"))
    out["date"] = pd.to_datetime(work_df.get("date").str[:23], errors="coerce", utc=True)
    out.dropna(subset=['timestamp'], inplace=True)
    return force_pid(out, pid)

def parse_accel(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    work_df = expand_data_column(df)
    out = pd.DataFrame()
    out["x"] = to_float(work_df.get("x"))
    out["y"] = to_float(work_df.get("y"))
    out["z"] = to_float(work_df.get("z"))
    out["timestamp"] = to_int_ms(work_df.get("timestamp"))
    out["date"] = pd.to_datetime(work_df.get("date").str[:23], errors="coerce", utc=True)
    out.dropna(subset=['timestamp'], inplace=True)
    return force_pid(out, pid)
    
def parse_location(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    work_df = expand_data_column(df)
    out = pd.DataFrame()
    out["latitude"] = to_float(work_df.get("latitude"))
    out["longitude"] = to_float(work_df.get("longitude"))
    out["timestamp"] = to_int_ms(work_df.get("timestamp"))
    for col in ["accuracy", "altitude", "altitudeAccuracy", "speed", "speedAccuracy", "heading"]:
        if col in work_df.columns: out[col] = to_float(work_df[col])
    out["date"] = pd.to_datetime(work_df.get("date").str[:23], errors="coerce", utc=True)
    out.dropna(subset=['timestamp', 'latitude', 'longitude'], inplace=True)
    return force_pid(out, pid)

def parse_ema(pid: str, df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["response"] = to_float(df.get("response"))
    out["timestamp"] = to_int_ms(df.get("timestamp"))
    out["surveyId"] = _to_py_int_series(df.get("surveyId"))
    out["questionNumber"] = _to_py_int_series(df.get("questionNumber"))
    out["questionnaireType"] = df.get("questionnaireType")
    out["questionText"] = df.get("questionText")
    out["date"] = pd.to_datetime(df.get("date").str[:23], errors="coerce", utc=True)
    out.dropna(subset=['timestamp'], inplace=True)
    return force_pid(out, pid)

# helper func
TABLES: Dict[str, str] = {
    "zip_log_final": "combined_id TEXT PRIMARY KEY, folder_name TEXT, zip_name TEXT",
    "battery_level_final": 'participant_id TEXT, "batteryPercent" INTEGER, timestamp BIGINT, date TIMESTAMPTZ NULL',
    "location_final": 'participant_id TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION, accuracy DOUBLE PRECISION NULL, altitude DOUBLE PRECISION NULL, "altitudeAccuracy" DOUBLE PRECISION NULL, speed DOUBLE PRECISION NULL, "speedAccuracy" DOUBLE PRECISION NULL, heading DOUBLE PRECISION NULL, timestamp BIGINT, date TIMESTAMPTZ NULL',
    "angv_final": "participant_id TEXT, x DOUBLE PRECISION, y DOUBLE PRECISION, z DOUBLE PRECISION, timestamp BIGINT, date TIMESTAMPTZ NULL",
    "acceleration_final": "participant_id TEXT, x DOUBLE PRECISION, y DOUBLE PRECISION, z DOUBLE PRECISION, timestamp BIGINT, date TIMESTAMPTZ NULL",
    "ema_responses_final": 'participant_id TEXT, "surveyId" INTEGER, "questionnaireType" TEXT, "questionNumber" INTEGER, "questionText" TEXT, response DOUBLE PRECISION NULL, date TIMESTAMPTZ NULL, timestamp BIGINT',
}

def create_tables_if_needed():
    with engine.begin() as conn:
        for tname, cols in TABLES.items():
            conn.execute(text(f'CREATE TABLE IF NOT EXISTS public."{tname}" ({cols});'))

def zip_already_done(full_path: str) -> bool:
    with engine.begin() as conn:
        return conn.execute(text('SELECT 1 FROM "zip_log_final" WHERE combined_id=:cid'), {"cid": full_path}).first() is not None

def log_zip(full_path: str):
    with engine.begin() as conn:
        conn.execute(
            text('INSERT INTO "zip_log_final" (combined_id, folder_name, zip_name) VALUES (:cid, :folder, :zip) ON CONFLICT (combined_id) DO NOTHING'),
            {"cid": full_path, "folder": os.path.dirname(full_path), "zip": os.path.basename(full_path)}
        )

#routing

HANDLERS = {"parse_ema": parse_ema, "parse_battery": parse_battery, "parse_location": parse_location, "parse_angv": parse_angv, "parse_accel": parse_accel}
USR = r"(?:user_sensor_datas_)?"
ROUTES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(rf"{USR}(ema_responses|user_survey_responses)\.json$", re.I), "ema_responses_final", "parse_ema"),
    (re.compile(rf"{USR}battery_level(_sample)?\.json$", re.I), "battery_level_final", "parse_battery"),
    (re.compile(rf"{USR}location(_sample)?\.json$", re.I), "location_final", "parse_location"),
    (re.compile(rf"{USR}(angular_velocity|angv)(_sample)?\.json$", re.I), "angv_final", "parse_angv"),
    (re.compile(rf"{USR}acceleration(_sample)?\.json$", re.I), "acceleration_final", "parse_accel"),
]

def route_for(name: str) -> Optional[Tuple[str, str]]:
    base = os.path.basename(name)
    for rx, table, handler in ROUTES:
        if rx.search(base): return (table, handler)
    return None

def list_all_zip_paths(base_prefix: str) -> List[str]:
    names: List[str] = []
    try:
        print(f"Listing zips under prefix: {base_prefix} (streaming)")
        for obj in STORAGE.list_files():
            n = getattr(obj, "name", "")
            if n.startswith(base_prefix) and n.endswith(".zip") and "/logs/" not in n:
                names.append(n)
        print(f"Discovered {len(names)} candidate zip(s) containing sensor data.")
    except Exception as e:
        print(f"Error listing files (stream): {e}")
    return names

def extract_pid_from_path(path: str) -> Optional[str]:
    m = re.search(r"studyIDs/([^/]+)/", path)
    return m.group(1) if m else None

def read_json_from_zip(zf: zipfile.ZipFile, inner_path: str) -> Optional[pd.DataFrame]:
    try:
        with zf.open(inner_path) as fp:
            raw = fp.read()
            print(f"    ↳ reading {inner_path} ({len(raw)} bytes)")
            arr = json.loads(raw.decode("utf-8"))
            return pd.DataFrame(arr)
    except Exception as e:
        print(f"  ! Could not read {inner_path}: {e}")
        return None

        
def read_json_from_zip_streaming(zf: zipfile.ZipFile, inner_path: str, chunk_size: int = 5000) -> Generator[pd.DataFrame, None, None]:
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

    print(f"\n--- Processing {storage_path} (PID {pid}) ---")
    tmpfile = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmpfile = tmp.name
        print(f"Downloading to temp: {tmpfile}")
        STORAGE.download(path=storage_path, filename=tmpfile)
        print(f"Download complete: {os.path.getsize(tmpfile)} bytes")

        with zipfile.ZipFile(tmpfile, "r") as zf:
            all_names = zf.namelist()
            inner_jsons = [n for n in all_names if n.lower().endswith(".json")]
            print(f"  🗂  Zip contains {len(all_names)} entries; JSON files: {len(inner_jsons)}")
            if not inner_jsons:
                log_zip(storage_path)
                return
              
            ema_present = any("ema_responses" in n.lower() for n in inner_jsons)
            if ema_present:
                inner_jsons = [n for n in inner_jsons if "user_survey_responses" not in n.lower()]
                print("  ⚙️  ema_responses.json present — skipping user_survey_responses.json")


            for inner in inner_jsons:
                routed = route_for(inner)
                if not routed:
                    print(f"    · skipping (no route): {inner}")
                    continue
                table, handler_name = routed
                parser = HANDLERS[handler_name]
                print(f"    → route: {inner} -> {table} via {handler_name}")
                
                # Changed this because of memory issues
                for chunk_df in read_json_from_zip_streaming(zf, inner, chunk_size=100000):
                    if chunk_df.empty:
                        continue
                    parsed = parser(pid, chunk_df)
                    if parsed.empty:
                        continue
                    parsed.to_sql(table, engine, if_exists="append", index=False)
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
                os.remove(tmpfile)
                print("  🧹 temp file removed")
            except Exception:
                print("  ⚠️ temp file cleanup failed")


if __name__ == "__main__":
    print("Starting ingestion script...")
    if not ensure_connection():
        raise SystemExit(1)

    print("Ensuring tables exist...")
    create_tables_if_needed()


    if 'STORAGE' not in locals():
        print("STORAGE object not configured.")
        raise SystemExit(1)

    base_prefix = os.environ.get("MT_BASE_PREFIX", "studyIDs/")
    zips = list_all_zip_paths(base_prefix)
    print(f"Found {len(zips)} total zip(s) under '{base_prefix}' to process.")
    
    # --- LIMIT TO FIRST 50 UNIQUE PARTICIPANTS ---
    seen_pids = set()
    filtered_zips = []
    
    for zp in sorted(zips):
        pid = extract_pid_from_path(zp)
        if not pid:
            continue
    
        # if we already have 50 unique PIDs, stop entirely
        if len(seen_pids) >= 50 and pid not in seen_pids:
            break
    
        # track unique PIDs and include their zips
        seen_pids.add(pid)
        filtered_zips.append(zp)
    
    zips = filtered_zips
    print(f"Processing only the first {len(seen_pids)} participants "
          f"({len(zips)} zip files).")
          
    # --- END LIMIT ---
    

    for i, zp in enumerate(sorted(zips), 1):
        print(f"▶️  [{i}/{len(zips)}] {zp}")
        process_zip(zp)

    print("\n--- 50 Participants finished ---")
