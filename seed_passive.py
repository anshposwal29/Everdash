import random
from datetime import datetime, timedelta
from database import get_db
from schema import User, PassiveData

def seed_passive_data():
    print("--- Seeding Mock Passive Data ---")
    db = next(get_db())
    
    # CORRECTED: Use 'identifier' instead of 'email'
    users = db.query(User).filter(User.identifier.in_(['alice@example.com', 'bob@example.com'])).all()
    
    if not users:
        print("❌ No demo users found (Alice/Bob).")
        print("   -> Tip: If you haven't run 'add_demo_users.py' yet, do that first!")
        return

    # Generate data for the last 14 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=14)
    
    count = 0
    for user in users:
        print(f"Generating data for {user.identifier}...")
        
        current = start_date
        while current <= end_date:
            # 1. Daily Steps (Random walk with trend)
            # Alice is active (8k steps), Bob is sedentary (3k steps)
            base_steps = 8000 if 'alice' in user.identifier else 3000
            daily_steps = max(0, int(random.gauss(base_steps, 1000)))
            
            # Check if data already exists to avoid duplicates
            existing = db.query(PassiveData).filter_by(
                user_id=user.id, 
                timestamp=current, 
                metric_type='steps'
            ).first()

            if not existing:
                db.add(PassiveData(
                    user_id=user.id,
                    timestamp=current,
                    metric_type='steps',
                    value=daily_steps,
                    source='mock_generator'
                ))
                count += 1
            
            # 2. Sleep (in minutes)
            base_sleep = 480 # 8 hours
            daily_sleep = max(0, int(random.gauss(base_sleep, 60)))
            
            existing_sleep = db.query(PassiveData).filter_by(
                user_id=user.id, 
                timestamp=current, 
                metric_type='sleep_minutes'
            ).first()

            if not existing_sleep:
                db.add(PassiveData(
                    user_id=user.id,
                    timestamp=current,
                    metric_type='sleep_minutes',
                    value=daily_sleep,
                    source='mock_generator'
                ))
                count += 1
            
            current += timedelta(days=1) # Move to next day

    db.commit()
    print(f"✓ Successfully added {count} data points.")
    db.close()

if __name__ == "__main__":
    seed_passive_data()

    