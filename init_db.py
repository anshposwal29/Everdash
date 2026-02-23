from database import engine
from schema import Base

print("--- Initializing Database ---")
print(f"Target Database: {engine.url}")

try:
    # This command creates all tables defined in schema.py
    Base.metadata.create_all(bind=engine)
    print("Successfully created all tables.")
except Exception as e:
    print(f"Error creating tables: {e}")
    