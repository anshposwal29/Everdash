import json
from app import app, db
from models import User

def seed_participants():
    """
    Reads users from mock_database.json and adds them to the local SQLite database
    so that the 'User Detail' page doesn't 404.
    """
    print("--- Seeding Participants ---")
    
    # 1. Load the Mock Data (The Source of Truth)
    try:
        with open('mock_database.json', 'r') as f:
            data = json.load(f)
            participants = data.get('participants', [])
            print(f"Found {len(participants)} participants in Mock Data.")
    except FileNotFoundError:
        print("Error: mock_database.json not found!")
        return

    # 2. Add to SQL Database
    with app.app_context():
        added_count = 0
        
        for p in participants:
            user_id = p['user_id']          # e.g., "user_001"
            redcap = p.get('redcap_id', '') # e.g., "REDCap-101"
            
            # Check if this user already exists in SQL
            # We assume your User model uses 'firebase_id' or 'participant_id'
            # Adjust the filter below if your model uses a different field name!
            existing_user = User.query.filter_by(firebase_id=user_id).first()
            
            if not existing_user:
                print(f"Registering new user: {user_id} ({p['identifier']})")
                
                # Create the user row
                # Note: We fill dummy values for email/password since they don't log in
                new_user = User(
                    firebase_id=user_id,
                    redcap_id=redcap,
                    is_active=True,
                    dropped=p.get('dropped', False)
                )
                db.session.add(new_user)
                added_count += 1
            else:
                print(f"User {user_id} already registered.")

        # 3. Save changes
        if added_count > 0:
            db.session.commit()
            print(f"Success! Added {added_count} users to SQL database.")
        else:
            print("No new users to add.")

if __name__ == "__main__":
    seed_participants()

    