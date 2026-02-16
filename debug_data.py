import requests
import json

# 1. Ask the Mock Server for User_001 (Casey)
url = "http://127.0.0.1:5001/api/v1/all_users"
headers = {"X-API-KEY": "sk_everdash_test_123"}

print("Attempting to fetch data from Mock Server...")
try:
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        print(f"❌ Error: Server returned status {r.status_code}")
        exit()
        
    data = r.json()
    participants = data.get('participants', [])
    casey = next((p for p in participants if p['user_id'] == 'user_001'), None)
    
    if not casey:
        print("❌ Error: Casey (user_001) not found in the data.")
    else:
        history = casey.get('passive_data_history', {})
        print(f"✅ Success! Found Casey.")
        print(f"   Data Points (Days): {len(history)}")
        if history:
            first_day = list(history.keys())[0]
            print(f"   Sample Data ({first_day}): {history[first_day]['quantitative']['watch_activity']}")
        else:
            print("❌ Error: Casey exists, but 'passive_data_history' is empty.")

except Exception as e:
    print(f"❌ Connection Failed: {e}")
    print("Make sure mock_server.py is running on port 5001!")

    