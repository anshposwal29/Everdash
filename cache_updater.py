"""
cache_updater.py
----------------
This script runs independently in its own terminal window.
It wakes up on a schedule, calls the Evergreen API for all users,
and writes the results to instance/cache.json.

Your Flask dashboard then reads from that file instead of
calling the API on every page load.

To run:
    python cache_updater.py

To change how often it refreshes, update CACHE_REFRESH_HOURS below.
"""

import requests
import json
import os
import time
from datetime import datetime, timedelta

# ---------------------------------------------------------------
# Configuration — change these as needed
# ---------------------------------------------------------------

# How many hours between cache refreshes
# Currently set to 24 hours (once per day)
CACHE_REFRESH_HOURS = 24

# Where to save the cache file
CACHE_FILE_PATH = os.path.join("instance", "cache.json")

# Evergreen API
EVERGREEN_BASE_URL = "https://evergreen-data-service.dali.dartmouth.edu"
API_KEY = "DdXis0P9ceZI6gnMoUH2h7S9lZf23hcEvGxQMXeg9GKVLdd6HkEwo4xZmDh9J2IX"
HEADERS = {"X-API-KEY": API_KEY}

# How many days of sensor data to fetch per user
SENSOR_WINDOW_DAYS = 30


# ---------------------------------------------------------------
# Low-level API helper
# ---------------------------------------------------------------

def _get(path, params=None):
    """
    Makes a GET request to the Evergreen API.
    Returns the parsed JSON response, or None if something went wrong.
    """
    url = f"{EVERGREEN_BASE_URL}{path}"
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"  [WARNING] {path} returned {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  [ERROR] Request failed for {path}: {e}")
        return None


def _unix(dt):
    """Converts a Python datetime object to a Unix timestamp integer."""
    return int(dt.timestamp())


# ---------------------------------------------------------------
# Per-user data fetchers
# ---------------------------------------------------------------

def _fetch_raw_sensor(user_id, sensor, start_ts, end_ts):
    """
    Fetches raw sensor readings for one user and one sensor type.
    Returns the list of data points, or an empty list if unavailable.

    Sensor options: gps, battery, accelerometer, gyroscope,
                    light_sensor, screen_time, sms, calls, healthkit
    """
    result = _get(f"/api/v1/internal/users/{user_id}/raw-data", params={
        "sensor": sensor,
        "start_time": start_ts,
        "end_time": end_ts
    })
    if result:
        return result.get("data", [])
    return []


def _fetch_features(user_id, start_ts, end_ts):
    """
    Fetches anomaly detection results for one user.
    Returns the raw response dict, or None if unavailable.
    """
    return _get(f"/api/v1/internal/users/{user_id}/features", params={
        "start_time": start_ts,
        "end_time": end_ts,
        "granularity": "daily"
    })


# ---------------------------------------------------------------
# Metric calculators (only use real data, never fabricate)
# ---------------------------------------------------------------

def _calculate_silence_days(raw_gps, raw_battery):
    """
    Calculates how many days since the user last had any sensor activity.
    Uses GPS and battery timestamps — whichever is most recent.
    Returns an integer number of days, or None if no data is available.
    """
    all_timestamps = []

    for point in raw_gps:
        ts = point.get("timestamp")
        if ts:
            all_timestamps.append(ts)

    for point in raw_battery:
        ts = point.get("timestamp")
        if ts:
            all_timestamps.append(ts)

    if not all_timestamps:
        # No data at all — we genuinely don't know, return None
        return None

    all_timestamps.sort(reverse=True)
    latest_str = all_timestamps[0]

    try:
        latest_str = latest_str.replace("Z", "+00:00")
        latest_dt = datetime.fromisoformat(latest_str)
        latest_naive = latest_dt.replace(tzinfo=None)
        delta = datetime.utcnow() - latest_naive
        return max(0, delta.days)
    except Exception as e:
        print(f"  [WARNING] Could not parse timestamp '{latest_str}': {e}")
        return None


def _calculate_passive_compliance(raw_gps, raw_battery, raw_accel, raw_gyro, window_days):
    """
    Calculates passive sensing compliance for each sensor as a percentage.

    Logic: Count how many unique days in the window had at least one
    data point. Divide by total days in window to get a percentage.

    Returns None for a sensor if it had zero data points — meaning
    we display 'N/A' in the UI rather than showing 0%.
    """
    def good_day_pct(data_points):
        if not data_points:
            # Genuinely no data — return None, not 0
            return None
        unique_days = set()
        for point in data_points:
            ts = point.get("timestamp", "")
            if ts:
                day = ts[:10]  # extract "2026-02-13" from full timestamp
                unique_days.add(day)
        if not unique_days:
            return None
        return min(100, int((len(unique_days) / window_days) * 100))

    return {
        "loc": good_day_pct(raw_gps),
        "bat": good_day_pct(raw_battery),
        "acc": good_day_pct(raw_accel),
        "gyr": good_day_pct(raw_gyro),
    }


def _calculate_days_in_study(created_at_str):
    """
    Calculates how many days the user has been in the study,
    based on their account creation date from the API.
    Returns an integer, or None if the date is unavailable.
    """
    if not created_at_str:
        return None
    try:
        created_dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        created_naive = created_dt.replace(tzinfo=None)
        return max(0, (datetime.utcnow() - created_naive).days)
    except Exception as e:
        print(f"  [WARNING] Could not parse created_at '{created_at_str}': {e}")
        return None


# ---------------------------------------------------------------
# Main cache builder
# ---------------------------------------------------------------

def build_cache():
    """
    Fetches all data from the Evergreen API and writes it to cache.json.
    This is the main function that runs on the schedule.
    """
    print(f"\n{'='*50}")
    print(f"Cache refresh started at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*50}")

    # Step 1: Get all users
    print("\n[1/2] Fetching user list...")
    users_data = _get("/api/v1/internal/users")

    if not users_data:
        print("[ERROR] Could not fetch users. Aborting cache refresh.")
        return False

    if isinstance(users_data, list):
        users = users_data
    else:
        users = users_data.get("users", users_data.get("data", []))

    print(f"  Found {len(users)} users.")

    # Step 2: Set up time window for sensor queries
    now = datetime.utcnow()
    window_start = now - timedelta(days=SENSOR_WINDOW_DAYS)
    start_ts = _unix(window_start)
    end_ts = _unix(now)

    # Step 3: Fetch data for each user
    print(f"\n[2/2] Fetching sensor data for each user (last {SENSOR_WINDOW_DAYS} days)...")
    participants = []

    for i, user in enumerate(users):
        user_id = user.get("firebase_uid")
        name = user.get("name", user.get("email", user_id))

        if not user_id:
            print(f"  [{i+1}/{len(users)}] Skipping user with no firebase_uid")
            continue

        print(f"  [{i+1}/{len(users)}] {name} ({user_id[:12]}...)")

        # Fetch all four sensors
        raw_gps   = _fetch_raw_sensor(user_id, "gps", start_ts, end_ts)
        raw_bat   = _fetch_raw_sensor(user_id, "battery", start_ts, end_ts)
        raw_accel = _fetch_raw_sensor(user_id, "accelerometer", start_ts, end_ts)
        raw_gyro  = _fetch_raw_sensor(user_id, "gyroscope", start_ts, end_ts)

        print(f"    GPS: {len(raw_gps)} pts | Battery: {len(raw_bat)} pts | "
              f"Accel: {len(raw_accel)} pts | Gyro: {len(raw_gyro)} pts")

        # Fetch features/anomalies
        features = _fetch_features(user_id, start_ts, end_ts)

        # Calculate metrics from real data only
        compliance    = _calculate_passive_compliance(raw_gps, raw_bat, raw_accel, raw_gyro, SENSOR_WINDOW_DAYS)
        silence_days  = _calculate_silence_days(raw_gps, raw_bat)
        days_in_study = _calculate_days_in_study(user.get("created_at"))

        # Build anomaly info — only from what the API actually returned
        anomaly_count = None
        if features and isinstance(features, dict):
            anomaly_count = features.get("anomaly_count")

        # Build the participant dict
        # Fields not available from the API are explicitly set to None
        # The dashboard will display "N/A" for None values
        participant = {
            # --- Identity (from /internal/users) ---
            "user_id":             user_id,
            "name":                user.get("name"),       # may be None
            "email":               user.get("email"),      # may be None
            "picture":             user.get("picture"),    # may be None
            "role":                user.get("role"),       # may be None

            # --- Fields NOT available from this API ---
            # These are set to None so the UI shows "N/A"
            "redcap_id":           None,
            "identifier":          user.get("name") or user.get("email"),  # best we can do
            "research_assistant":  None,
            "dropped":             None,

            # --- Study timing ---
            "days_in_study":       days_in_study,   # calculated from created_at, may be None

            # --- Sensor compliance (each value is % or None if no data) ---
            "passive_sensing_compliance": compliance,

            # --- Decision engine results ---
            # Only anomaly_count is real; everything else is None
            "decision_engine_results": {
                "silence_days":    silence_days,    # calculated from sensor timestamps, may be None
                "risky_count":     None,            # not available from this API
                "symptom_radar":   None,            # not available from this API
                "needs_attention": None,            # not available from this API
                "anomaly_count":   anomaly_count,   # from features endpoint, may be None
            },

            # --- Conversations ---
            # Messages API is not ready yet
            "conversations":       None,

            # --- Cache metadata ---
            "cached_at": now.isoformat()
        }

        participants.append(participant)

    # Step 4: Write to cache file
    cache_data = {
        "participants":  participants,
        "cached_at":     now.isoformat(),
        "window_days":   SENSOR_WINDOW_DAYS,
        "user_count":    len(participants)
    }

    os.makedirs("instance", exist_ok=True)

    with open(CACHE_FILE_PATH, "w") as f:
        json.dump(cache_data, f, indent=2)

    print(f"\n✅ Cache written to {CACHE_FILE_PATH}")
    print(f"   {len(participants)} participants saved.")
    print(f"   Next refresh in {CACHE_REFRESH_HOURS} hours.")
    return True


# ---------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------

if __name__ == "__main__":
    print("Cache updater started.")
    print(f"Will refresh every {CACHE_REFRESH_HOURS} hour(s).")
    print("Press Ctrl+C to stop.\n")

    while True:
        success = build_cache()

        if not success:
            print("[WARNING] Cache refresh failed. Will retry in 1 hour.")
            sleep_seconds = 3600
        else:
            sleep_seconds = CACHE_REFRESH_HOURS * 3600

        next_run = datetime.utcnow() + timedelta(seconds=sleep_seconds)
        print(f"\nSleeping until {next_run.strftime('%Y-%m-%d %H:%M:%S')} UTC...")
        time.sleep(sleep_seconds)


        