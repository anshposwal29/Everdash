import json
from datetime import datetime, date
from app import db, app
from models import User, Conversation, Message, Admin

def seed_from_json():
    try:
        with open('db.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Error: db.json not found.")
        return

    with app.app_context():
        # 1. Reset everything for a clean start
        print("Wiping database and building fresh tables...")
        db.drop_all()
        db.create_all()
        
        # 2. Create your working Admin
        admin_user = "admin"
        admin_pass = "AdminPass123!" 
        new_admin = Admin(
            username=admin_user, 
            email="admin@study.edu", 
            is_active=True, 
            is_approved=True
        )
        new_admin.set_password(admin_pass)
        db.session.add(new_admin)
        print(f"Admin '{admin_user}' ready.")

        # 3. Add Users
        for u in data['users']:
            new_user = User(
                id=u['id'],
                firebase_id=u['firebase_id'],
                redcap_id=u['redcap_id'],
                identifier=u['identifier'],
                is_active=u.get('is_active', True),
                dropped=u.get('dropped', False),
                # THIS IS THE FIX: Convert string to Python date object
                study_start_date=date.fromisoformat(u['study_start_date'])
            )
            db.session.add(new_user)
        
        # 4. Add Conversations (Now including topic and trigger_type!)
        for c in data['conversations']:
            c_copy = c.copy()
            # Convert ISO strings to Python datetime objects
            c_copy['timestamp'] = datetime.fromisoformat(c['timestamp'].replace('Z', ''))
            c_copy['created_at'] = datetime.fromisoformat(c['created_at'].replace('Z', ''))
            db.session.add(Conversation(**c_copy))
            
        # 5. Add Messages
        for m in data['messages']:
            m_copy = m.copy()
            # Remove 'author_role' (it's in JSON but not in your Message model)
            m_copy.pop('author_role', None) 
            m_copy['timestamp'] = datetime.fromisoformat(m['timestamp'].replace('Z', ''))
            db.session.add(Message(**m_copy))
        
        try:
            db.session.commit()
            print("\nSUCCESS: Database seeded and all links preserved!")
            print(f"Login at the dashboard with: {admin_user} / {admin_pass}")
        except Exception as e:
            db.session.rollback()
            print(f"\nCRITICAL ERROR during commit: {e}")

if __name__ == "__main__":
    seed_from_json()