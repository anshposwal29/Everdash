import json
import random
from datetime import datetime, timedelta

# FILE CONFIGURATION
INPUT_FILE = 'mock_database.json'
OUTPUT_FILE = 'mock_database.json' # Overwrites the file with new data

def generate_time_series(start_date, days=30):
    """Generates daily data for the last 30 days for all requested sensors."""
    dates = [start_date + timedelta(days=i) for i in range(days)]
    history = {}
    
    for d in dates:
        d_str = d.strftime("%Y-%m-%d")
        
        # --- 1. QUANTITATIVE (Watch & Phone) ---
        daily_steps = int(random.gauss(6000, 2000))
        daily_steps = max(0, min(20000, daily_steps))
        sleep_min = int(random.gauss(420, 60))
        
        # Hourly battery simulation (drain and charge cycles)
        battery = []
        level = random.randint(80, 100)
        for h in range(24):
            drain = random.randint(1, 5)
            level -= drain
            if level < 20: level = 100 # Simulated recharge
            battery.append(level)
            
        history[d_str] = {
            "quantitative": {
                "watch_sleep": {
                    "minutes_total": sleep_min,
                    "efficiency": random.randint(70, 98),
                    "classifier_output": "normal"
                },
                "watch_activity": {
                    "steps": daily_steps,
                    "calories": int(daily_steps * 0.04),
                    "classifier_output": random.choice(["sedentary", "lightly_active", "active"])
                },
                "watch_heart_rate": {
                    "resting_bpm": random.randint(55, 75),
                    "avg_bpm": random.randint(70, 90),
                    "max_bpm": random.randint(110, 160)
                },
                "phone_screen_time": {
                    "minutes": random.randint(60, 400),
                    "unlocks": random.randint(20, 100)
                },
                "phone_battery": battery, # List of 24 hourly values
                "phone_ambient_light": { "avg_lux": random.randint(50, 500) },
                "phone_accelerometer": { 
                    "hours_collected": round(random.uniform(10, 24), 1), 
                    "magnitude_avg": round(random.uniform(9.0, 10.5), 2) 
                },
                "phone_gyroscope": { 
                    "hours_collected": round(random.uniform(10, 24), 1) 
                },
                "timestamps": {
                    "calls_count": random.randint(0, 5),
                    "texts_count": random.randint(0, 20)
                }
            },
            
            # --- 2. QUALITATIVE (Connectivity & Location) ---
            "qualitative": {
                "wifi": {
                    "connected_ssid": "Dartmouth-Secure",
                    "signal_strength_dbm": random.randint(-80, -40)
                },
                "bluetooth": {
                    "paired_devices_count": random.randint(1, 5),
                    "scanned_devices_count": random.randint(10, 50)
                },
                "hashed_contacts": {
                    "distinct_contacts_seen": random.randint(2, 10)
                },
                "gps": {
                    "location_samples": random.randint(12, 24), # Hourly samples
                    "significant_places_visited": random.randint(1, 4)
                }
            },
            
            # --- 3. CAMPUS DATA (Services) ---
            "campus": {
                "dining_purchases": [
                    {"item": random.choice(["Coffee", "Sandwich", "Salad", "Pizza", "Bagel"]), 
                     "cost": round(random.uniform(3, 12), 2),
                     "location": random.choice(["Collis", "Foco", "Novack"])}
                    for _ in range(random.randint(0, 3))
                ],
                "canvas_logs": {
                    "assignments_submitted": random.randint(0, 1),
                    "files_viewed": random.randint(0, 5)
                },
                "darthub": {
                    "term_status": "Enrolled",
                    "holds": False
                },
                "wireless_locations": [
                    {"building": random.choice(["Berry Library", "Kemeny Hall", "Sudikoff"]), "duration_mins": random.randint(30, 120)}
                    for _ in range(random.randint(1, 3))
                ]
            }
        }
    return history

def update_database():
    try:
        with open(INPUT_FILE, 'r') as f:
            data = json.load(f)
            print(f"Loaded {len(data['participants'])} participants.")
    except FileNotFoundError:
        print(f"Error: {INPUT_FILE} not found. Please ensure it is in the same folder.")
        return

    # Generate data starting from 30 days ago
    start_date = datetime.now() - timedelta(days=30)
    
    for p in data['participants']:
        print(f"Generating rich history for {p['identifier']}...")
        
        # 1. Generate the 30-day history
        p['passive_data_history'] = generate_time_series(start_date)
        
        # 2. Update the 'passive_sensing_compliance' summary to match the most recent day
        # This ensures the dashboard dots (Red/Green) match the detailed data
        last_day_key = list(p['passive_data_history'].keys())[-1]
        last_day_data = p['passive_data_history'][last_day_key]
        
        # Calculate % compliance based on 24 hours
        acc_compliance = int((last_day_data['quantitative']['phone_accelerometer']['hours_collected'] / 24) * 100)
        gyr_compliance = int((last_day_data['quantitative']['phone_gyroscope']['hours_collected'] / 24) * 100)
        # Randomize loc/bat for variety if not explicitly tracked by hours
        loc_compliance = random.randint(80, 100) if not p.get('dropped') else 0
        bat_compliance = 100 if not p.get('dropped') else 0

        p['passive_sensing_compliance'] = {
            "loc": loc_compliance,
            "bat": bat_compliance,
            "acc": acc_compliance,
            "gyr": gyr_compliance
        }

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Success! {OUTPUT_FILE} has been updated with 30 days of data.")

if __name__ == "__main__":
    update_database()

    