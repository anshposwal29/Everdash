#!/usr/bin/env python3
"""
Migration script to add identifier field to users table.
This field stores the email or other identifier from Firebase Authentication.
"""

import sqlite3
import os

def migrate():
    # Get the database path from the instance folder
    db_path = os.path.join('instance', 'theradash.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        print("Please ensure the database exists before running this migration.")
        return

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if the identifier column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'identifier' in columns:
            print("The 'identifier' column already exists in the users table.")
            print("No migration needed.")
            return

        # Add the identifier column
        print("Adding 'identifier' column to users table...")
        cursor.execute("""
            ALTER TABLE users
            ADD COLUMN identifier VARCHAR(255)
        """)

        conn.commit()
        print("Migration completed successfully!")
        print("The 'identifier' column has been added to the users table.")
        print("\nNext steps:")
        print("1. Run a sync to populate the identifier field from Firebase Authentication")
        print("2. The identifier will be automatically fetched during the next sync operation")

    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
