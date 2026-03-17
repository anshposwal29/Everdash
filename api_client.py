import json
import os

CACHE_FILE_PATH = os.path.join("instance", "cache.json")


def fetch_all_participants():
    if not os.path.exists(CACHE_FILE_PATH):
        print("[api_client] Cache file not found. Run 'python cache_updater.py' first.")
        return []

    try:
        with open(CACHE_FILE_PATH, "r") as f:
            cache_data = json.load(f)

        participants = cache_data.get("participants", [])
        cached_at = cache_data.get("cached_at", "unknown")
        print(f"[api_client] Loaded {len(participants)} participants from cache (cached at {cached_at})")
        return participants

    except json.JSONDecodeError as e:
        print(f"[api_client] Cache file corrupted: {e}")
        return []

    except Exception as e:
        print(f"[api_client] Unexpected error: {e}")
        return []
