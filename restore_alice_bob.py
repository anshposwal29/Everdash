"""
Restore Alice and Bob to the local database.
Bypasses Firebase checks so we can test the UI immediately.
"""
from database import get_db
from schema import User
import datetime

def restore_local_users():
    print("--- Restoring Alice and Bob (Local Only) ---")
    db = next(get_db())
    
    # 1. Alice
    alice = db.query(User).filter_by(identifier='alice@example.com').first()
    if not alice:
        print("Creating Alice...")
        alice = User(
            firebase_id='demo_alice_123',
            identifier='alice@example.com',
            is_active=True,
            is_animated=True,
            study_start_date=datetime.date.today() - datetime.timedelta(days=20)
        )
        db.add(alice)
    else:
        print("✓ Alice already exists.")

    # 2. Bob
    bob = db.query(User).filter_by(identifier='bob@example.com').first()
    if not bob:
        print("Creating Bob...")
        bob = User(
            firebase_id='demo_bob_456',
            identifier='bob@example.com',
            is_active=True,
            study_start_date=datetime.date.today() - datetime.timedelta(days=20)
        )
        db.add(bob)
    else:
        print("✓ Bob already exists.")

    db.commit()
    print("✓ Done. Database is ready for seeding.")

if __name__ == "__main__":
    restore_local_users()

    