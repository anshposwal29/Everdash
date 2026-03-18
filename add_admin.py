from app import app
from models import db, Admin

MY_USERNAME = "ansh"
MY_EMAIL = "anshoswal05@gmail.com"
MY_PHONE = "+18025473110"
MY_PASSWORD = "123"

with app.app_context():
    # 1. This is the missing line! It builds the empty tables first.
    db.create_all()
    
    # 2. Create the admin and automatically approve them
    new_admin = Admin(
        username=MY_USERNAME,
        email=MY_EMAIL,
        phone_number=MY_PHONE,
        is_approved=True,
        is_active=True
    )
    
    # 3. Securely hash the password
    new_admin.set_password(MY_PASSWORD)
    
    # 4. Save to database
    db.session.add(new_admin)
    db.session.commit()
    
    print(f"Success! Admin {MY_USERNAME} has been created and approved.")