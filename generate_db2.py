import json
import random
from datetime import datetime, timedelta

# --- CONFIGURATION ---
FILENAME = "mock_database2.json"
NUM_DAYS = 30
END_DATE = datetime.now()

# --- PERSONAS ---
# These profiles ensure the data looks real and tells a story
PERSONAS = [
    {
        "id": "user_001", "name": "Active Alex", "type": "healthy",
        "base_steps": 10000, "base_sleep": 480, "compliance": "high"
    },
    {
        "id": "user_002", "name": "Burnout Bob", "type": "risky",
        "base_steps": 2000, "base_sleep": 300, "compliance": "medium"
    },
    {
        "id": "user_003", "name": "Social Sarah", "type": "healthy",
        "base_steps": 7000, "base_sleep": 420, "compliance": "high"
    },
    {
        "id": "user_004", "name": "Ghosting Greg", "type": "dropped",
        "base_steps": 4000, "base_sleep": 360, "compliance": "low"
    },
    {
        "id": "user_005", "name": "Erratic Eve", "type": "variable",
        "base_steps": 5000, "base_sleep": 400, "compliance": "medium"
    }
]

def get_date_str(days_ago):
    return (END_DATE - timedelta(days=days_ago)).strftime('%Y-%m-%d')

def generate_user_data(persona):
    history = {}
    events = []
    conversations = []

    # Generate 30 days of history
    for i in range(NUM_DAYS):
        date_str = get_date_str(NUM_DAYS - 1 - i) # Chronological order
        
        # 1. Modify stats based on Persona + Random Noise
        steps = int(random.gauss(persona['base_steps'], 1000))
        sleep = int(random.gauss(persona['base_sleep'], 60))
        if steps < 0: steps = 0
        if sleep < 0: sleep = 0
        
        # If user is "Dropped", stop data after 15 days
        if persona['type'] == 'dropped' and i > 15:
            break

        # 2. Build the Passive Data Entry
        history[date_str] = {
            "quantitative": {
                "watch_activity": { "steps": steps },
                "watch_heart_rate": { "avg_bpm": random.randint(60, 90) },
                "watch_sleep": { "minutes_total": sleep },
                "phone_screen_time": { "minutes": random.randint(100, 400) },
                "phone_battery": [random.randint(5, 100) for _ in range(4)]
            },
            "campus": {
                "canvas_logs": { "files_viewed": random.randint(0, 10) },
                "wireless_locations": [
                    { "building": "Baker-Berry", "duration_mins": random.randint(0, 180) }
                ]
            }
        }

        # 3. GENERATE LOGIC-BASED EVENTS (The "Smart" Part)
        # Rule A: Low Activity Nudge
        if steps < 3000:
            events.append({
                "date": date_str,
                "type": "automated_nudge",
                "details": f"System detected low activity ({steps} steps). Sent generic prompt."
            })
        
        # Rule B: Critical Risk Intervention (Low Sleep + Low Steps)
        if sleep < 300 and steps < 3000:
            events.append({
                "date": date_str,
                "type": "staff_intervention",
                "details": "RISK ALERT: Combo of low sleep/activity. Staff emailed participant."
            })
            # Add a conversation to match!
            conversations.append({
                "prompt": "Risk Intervention",
                "messages": [
                    {"speaker": "Evie", "text": "I noticed you haven't been sleeping well.", "timestamp": date_str + "T10:00:00"},
                    {"speaker": "Participant", "text": "Yeah, exams are killing me.", "timestamp": date_str + "T10:05:00", "risky": True}
                ]
            })

    # Assemble the User Object
    return {
        "user_id": persona['id'],
        "redcap_id": f"REDCAP-{100 + int(persona['id'].split('_')[1])}",
        "identifier": persona['name'],
        "is_active": persona['type'] != 'dropped',
        "research_assistant": "Dr. Smith",
        "days_in_study": len(history),
        "decision_engine_results": {
            "symptom_radar": 2 if persona['type'] == 'risky' else 0,
            "risky_count": len([e for e in events if e['type'] == 'staff_intervention']),
            "needs_attention": persona['type'] == 'risky'
        },
        "passive_sensing_compliance": {"bat": 95 if persona['compliance'] == 'high' else 60},
        "conversations": conversations,
        "passive_data_history": history,
        "events": events
    }

# --- MAIN EXECUTION ---
full_db = {"participants": [generate_user_data(p) for p in PERSONAS]}

with open(FILENAME, 'w') as f:
    json.dump(full_db, f, indent=2)

print(f"✅ Created {FILENAME} with {len(PERSONAS)} smart users.")
print(f"👉 Go to mock_server.py and change DB_FILE = '{FILENAME}'")

