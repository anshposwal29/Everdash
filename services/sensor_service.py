import random
from datetime import datetime, timedelta

# ==========================================
# FUNCTION 1: FETCH SENSOR DATA (Line Graph)
# ==========================================
def fetch_sensor_data_external(user_identifier, metric_type, start_date, end_date, api_key):
    """
    Simulates a secure request to the External Sensor API.
    Returns a list of values for the graph.
    """
    
    # 1. SECURITY CHECK (Simulated)
    if not api_key or api_key != "sk_sensor_test_key_v1":
        print(f"Warning: Invalid API Key used for {metric_type}")
    
    # 2. CONFIGURATION: Statistical profiles
    SENSOR_PROFILES = {
        # Physiological
        'heart_rate_avg':      {'mu': 72, 'sigma': 8,  'min': 45, 'max': 130, 'decimals': 0},
        'steps':               {'mu': 6000, 'sigma': 2500, 'min': 100, 'max': 20000, 'decimals': 0},
        'sleep_minutes':       {'mu': 400, 'sigma': 60, 'min': 120, 'max': 720, 'decimals': 0},
        
        # Digital Phenotyping (Phone)
        'screen_time_minutes': {'mu': 300, 'sigma': 90, 'min': 30, 'max': 700, 'decimals': 0},
        'battery_drain':       {'mu': 85, 'sigma': 10, 'min': 10, 'max': 100, 'decimals': 0},
        'ambient_light_lux':   {'mu': 600, 'sigma': 200, 'min': 50, 'max': 5000, 'decimals': 0},
        
        # Mobility & Connectivity
        'travel_radius':       {'mu': 5.0, 'sigma': 3.5, 'min': 0.1, 'max': 25.0, 'decimals': 2}, # km
        'wifi_interactions':   {'mu': 6,   'sigma': 2,   'min': 1,   'max': 15,   'decimals': 0},
        'bluetooth_devices':   {'mu': 15,  'sigma': 8,   'min': 0,   'max': 60,   'decimals': 0},
        
        # Campus Data
        'dining_expense':      {'mu': 22.50, 'sigma': 8.50, 'min': 0, 'max': 60.00, 'decimals': 2},
        'canvas_activity':     {'mu': 8,     'sigma': 5,    'min': 0, 'max': 30,    'decimals': 0},
    }

    # Default profile
    profile = SENSOR_PROFILES.get(metric_type, {'mu': 50, 'sigma': 20, 'min': 0, 'max': 100, 'decimals': 0})

    data_points = []
    current = start_date
    
    # 3. GENERATE DATA
    while current <= end_date:
        val = random.gauss(profile['mu'], profile['sigma'])
        val = max(profile['min'], min(profile['max'], val))
        
        if profile['decimals'] == 0:
            val = int(val)
        else:
            val = round(val, profile['decimals'])
            
        data_points.append(val)
        current += timedelta(days=1)
        
    return data_points


# ==========================================
# FUNCTION 2: FETCH INTERVENTIONS (Dots)
# ==========================================
def fetch_intervention_history_external(user_identifier, start_date, end_date, api_key):
    """
    Simulates fetching clinical/staff interventions from the external API.
    Returns a list of dicts: [{'date': 'YYYY-MM-DD', 'type': 'staff', 'details': '...'}]
    """
    # 1. SECURITY CHECK
    if not api_key:
        return []

    interventions = []
    
    current = start_date
    while current <= end_date:
        # Mock Logic: 10% chance of a Staff Note on any given day
        if random.random() < 0.10:
            date_str = current.strftime('%Y-%m-%d')
            note_type = random.choice(['Risk Assessment', 'Phone Call', 'Check-in', 'Medication Adjust'])
            
            interventions.append({
                'date': date_str,
                'type': 'staff', # Red Dot
                'details': f"{note_type} - Logged via External API"
            })
            
        # Mock Logic: 5% chance of a User Report
        elif random.random() < 0.05:
            date_str = current.strftime('%Y-%m-%d')
            
            interventions.append({
                'date': date_str,
                'type': 'user', # Orange Dot
                'details': "User submitted symptom report"
            })
            
        current += timedelta(days=1)
        
    return interventions

