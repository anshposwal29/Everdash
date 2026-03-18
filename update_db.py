from app import app, db
from sqlalchemy import text

print("Starting database update...")

with app.app_context():
    # 1. Create the new table (PassiveDailySummary)
    db.create_all()
    print("✅ Created new tables.")

    # 2. Add the new column (symptom_radar) to the User table
    # We use a try/except block just in case you already ran it
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN symptom_radar INTEGER DEFAULT 5"))
            conn.commit()
            print("✅ Added 'symptom_radar' column to Users table.")
    except Exception as e:
        print(f"ℹ️ Note: {e}")
        print("   (This usually means the column already exists, which is fine.)")

print("Database update complete!")

