#!/usr/bin/env python3
"""
Migration script to add research_assistant field to users table.
Run this once to update your existing database.
"""
import sqlite3
import os

# Get database path from environment or use default
database_url = os.environ.get('DATABASE_URL', 'sqlite:///theradash.db')
db_path = database_url.replace('sqlite:///', '')

print(f"Connecting to database: {db_path}")

try:
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'research_assistant' in columns:
        print("Column 'research_assistant' already exists in users table. No migration needed.")
    else:
        # Add the new column
        print("Adding 'research_assistant' column to users table...")
        cursor.execute("ALTER TABLE users ADD COLUMN research_assistant VARCHAR(100)")
        conn.commit()
        print("Migration completed successfully!")

    conn.close()

except Exception as e:
    print(f"Error during migration: {e}")
    print("\nIf the database doesn't exist yet, you can ignore this error.")
    print("The field will be created when you initialize the database.")
