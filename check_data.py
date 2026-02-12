from database import get_db
from schema import User, PassiveData

def check_data():
    db = next(get_db())
    
    print("\n--- 1. Checking Users ---")
    users = db.query(User).all()
    for u in users:
        print(f"User ID: {u.id} | Name: {u.identifier} | REDCap ID: {u.redcap_id}")

    print("\n--- 2. Checking Passive Data ---")
    data_points = db.query(PassiveData).limit(5).all()
    
    if not data_points:
        print("❌ NO PASSIVE DATA FOUND IN DATABASE.")
    else:
        print(f"✓ Found {db.query(PassiveData).count()} total data points.")
        first_point = data_points[0]
        print(f"Sample Data -> User ID: {first_point.user_id} | Metric: {first_point.metric_type} | Value: {first_point.value}")
        
    print("\n--- End of Report ---")

if __name__ == "__main__":
    check_data()

    