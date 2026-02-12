import datetime
import pytz
import pandas as pd
from typing import Optional, Union
from config import Config

# 1. Get the centralized Timezone from your Config
TZ_NAME = Config.TIMEZONE
TZ = pytz.timezone(TZ_NAME)

def to_tz_aware_datetime(val: Union[str, int, float, pd.Timestamp]) -> Optional[datetime.datetime]:
    """
    Convert various inputs (string, int timestamp, pandas timestamp) 
    to a timezone-aware datetime object (Standardized to Config.TIMEZONE).
    """
    if pd.isna(val) or val == "" or val is None:
        return None
    
    dt = None
    
    try:
        # Handle pandas Timestamp
        if isinstance(val, pd.Timestamp):
            dt = val.to_pydatetime()
            
        # Handle numeric timestamps (assume seconds if small, ms if large)
        elif isinstance(val, (int, float)):
            # Heuristic: if > 3e11, it's likely milliseconds (e.g., 1600000000000)
            if val > 300_000_000_000: 
                val = val / 1000.0
            dt = datetime.datetime.fromtimestamp(val)
            
        # Handle strings (ISO format, etc.)
        elif isinstance(val, str):
            dt = pd.to_datetime(val).to_pydatetime()

        if dt is None:
            return None

        # Ensure timezone awareness
        if dt.tzinfo is None:
            # If naive, assume it belongs to the configured timezone
            dt = TZ.localize(dt)
        else:
            # If already aware, convert to the configured timezone
            dt = dt.astimezone(TZ)
            
        return dt
        
    except Exception:
        return None

def to_int_ms(dt_val: Union[datetime.datetime, pd.Timestamp, str]) -> Optional[int]:
    """
    Convert a datetime-like object (or string) to integer milliseconds.
    """
    dt = to_tz_aware_datetime(dt_val)
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)

def force_pid(pid_val: Union[str, int, float]) -> Optional[str]:
    """
    Standardize Participant ID format.
    - Handles floats: 1001.0 -> "1001"
    - Handles ints: 1001 -> "1001"
    - Handles whitespace: " 1001 " -> "1001"
    """
    if pd.isna(pid_val) or pid_val == "":
        return None
    
    try:
        # If it looks like a float (e.g. from pandas read_csv), convert to int first
        if isinstance(pid_val, float):
             return str(int(pid_val))
        return str(pid_val).strip()
    except Exception:
        return None