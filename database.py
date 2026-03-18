import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.engine import Engine
from config import Config  # Import the specific class

# 1. Get the connection string directly from your Config class
# This reuses the logic you already have for reading DATABASE_URL
DATABASE_URL = Config.SQLALCHEMY_DATABASE_URI

# 2. Create the SQLAlchemy Engine
# pool_pre_ping=True helps prevent "server closed the connection unexpectedly" errors
engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# 3. Create a Thread-Safe Session Factory
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

def get_db():
    """
    Dependency helper for use in scripts or API routes.
    Yields a database session and ensures it closes after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_connection():
    """
    Simple test to verify we can talk to the database.
    """
    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            # Simple query to check connection
            # 'SELECT 1' is standard; 'SELECT current_user' works on Postgres
            result = conn.execute(text("SELECT 1")).scalar()
            print(f"✅ database.py: Successfully connected! (Test query returned: {result})")
        return True
    except Exception as e:
        print(f"❌ database.py: Connection failed: {e}")
        return False

# Self-test when running this file directly
if __name__ == "__main__":
    ensure_connection()