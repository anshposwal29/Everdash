from app import app, db
from models import Admin
from datetime import datetime, timezone

def create_custom_admin():
    with app.app_context():
        print("Recreating database tables to include new columns...")
        # WARNING: This deletes existing admin data. 
        # Use this only for development/resetting.
        db.drop_all() 
        db.create_all()

        # Define your custom admin details
        custom_username = 'new_admin'
        custom_email = 'admin@everdash.com'
        custom_password = 'pass123'
        custom_phone = '+17042400795' # E.164 format for Twilio

        # Check if user already exists (just in case)
        existing_admin = Admin.query.filter_by(username=custom_username).first()
        
        if not existing_admin:
            new_admin = Admin(
                username=custom_username,
                email=custom_email,
                phone_number=custom_phone,
                is_approved=True,
                is_active=True,
                created_at=datetime.now(timezone.utc)
            )
            new_admin.set_password(custom_password)
            
            db.session.add(new_admin)
            db.session.commit()
            print(f"Successfully created custom admin: {custom_username}")
            print(f"Phone number set to: {custom_phone}")
        else:
            print(f"Admin '{custom_username}' already exists.")

if __name__ == "__main__":
    create_custom_admin()
    