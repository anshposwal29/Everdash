import requests
from datetime import datetime, timedelta
from config import Config

# The address of your Mock Server (must be running on port 5001)
MOCK_API_URL = "http://127.0.0.1:5001/api/v1/all_users"
API_KEY = "sk_everdash_test_123"

def fetch_sensor_data_external(user_identifier, metric_type, start_date, end_date, api_key):
    """
    Fetches mock data. Now UPDATED to find users by either user_id OR redcap_id.
    """
    try:
        # 1. Fetch Master Data
        headers = {"X-API-KEY": api_key}
        response = requests.get(MOCK_API_URL, headers=headers, timeout=5)
        
        if response.status_code != 200:
            print(f"Error fetching from Mock API: {response.status_code}")
            return []

        data = response.json()
        participants = data.get('participants', [])
        
        # --- CRITICAL FIX ---
        # Look for a match in 'user_id' OR 'redcap_id'
        user = next((p for p in participants if p['user_id'] == user_identifier or p.get('redcap_id') == user_identifier), None)
        
        if not user:
            print(f"User {user_identifier} not found in Mock Data (checked ID and REDCap)")
            return []

        # 2. Extract Data (Same as before)
        history = user.get('passive_data_history', {})
        values = []
        
        current = start_date
        while current <= end_date:
            d_str = current.strftime('%Y-%m-%d')
            day_data = history.get(d_str)
            val = 0 
            
            if day_data:
                q = day_data.get('quantitative', {})
                if metric_type == 'steps':
                    val = q.get('watch_activity', {}).get('steps', 0)
                elif metric_type == 'heart_rate_avg':
                    val = q.get('watch_heart_rate', {}).get('avg_bpm', 0)
                elif metric_type == 'sleep_minutes':
                    val = q.get('watch_sleep', {}).get('minutes_total', 0)
                elif metric_type == 'screen_time_minutes':
                    val = q.get('phone_screen_time', {}).get('minutes', 0)
                elif metric_type == 'battery_drain':
                    levels = q.get('phone_battery', [])
                    val = (100 - min(levels)) if levels else 0
                
            values.append(val)
            current += timedelta(days=1)
            
        return values

    except Exception as e:
        print(f"Sensor Service Error: {e}")
        return []
    

