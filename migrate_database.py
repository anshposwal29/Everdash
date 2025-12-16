#!/usr/bin/env python3
"""
Consolidated database migration script for Theradash.

This script handles all database schema updates in a single file.
It is idempotent - safe to run multiple times on the same database.

Migrations included:
1. Add 'identifier' column to users table (for Firebase Auth email/phone)
2. Add 'research_assistant' column to users table (for assigned RA)
3. Add 'dropped' and 'dropped_surveys' columns to users table (participant status)
4. Add 'redcap_firebase_id' column to users table (display ID from REDCap)
5. Add 'project_id' column to users table (multi-project support)
6. Add 'study_start_date' and 'study_end_date' columns to users table
7. Add 'is_approved' column to admins table (for admin approval workflow)
8. Add 'is_risky' column to messages table (replaces risk_score)
9. Migrate data from risk_score to is_risky (if risk_score exists)

Usage:
    python migrate_database.py

Run this script once on production after deploying code changes.
After migration, run a sync to populate new fields with data from REDCap/Firebase.
"""

from app import app, db
from sqlalchemy import inspect, text


def get_table_columns(inspector, table_name):
    """Get list of column names for a table."""
    try:
        return [col['name'] for col in inspector.get_columns(table_name)]
    except Exception:
        return []


def add_column_if_missing(conn, table_name, column_name, column_type, columns):
    """Add a column to a table if it doesn't already exist."""
    if column_name in columns:
        print(f"  [SKIP] {table_name}.{column_name} already exists")
        return False

    print(f"  [ADD]  {table_name}.{column_name} ({column_type})")
    conn.execute(text(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}'))
    return True


def migrate_users_table(conn, inspector):
    """Apply all migrations to the users table."""
    print("\n--- Users Table Migrations ---")

    columns = get_table_columns(inspector, 'users')
    if not columns:
        print("  [ERROR] Users table not found")
        return False

    migrations_applied = 0

    # Migration 1: identifier field
    if add_column_if_missing(conn, 'users', 'identifier', 'VARCHAR(255)', columns):
        migrations_applied += 1

    # Migration 2: research_assistant field
    if add_column_if_missing(conn, 'users', 'research_assistant', 'VARCHAR(100)', columns):
        migrations_applied += 1

    # Migration 3: dropped fields
    if add_column_if_missing(conn, 'users', 'dropped', 'BOOLEAN DEFAULT 0', columns):
        migrations_applied += 1

    if add_column_if_missing(conn, 'users', 'dropped_surveys', 'BOOLEAN DEFAULT 0', columns):
        migrations_applied += 1

    # Migration 4: redcap_firebase_id field
    if add_column_if_missing(conn, 'users', 'redcap_firebase_id', 'VARCHAR(100)', columns):
        migrations_applied += 1

    # Migration 5: project_id field (multi-project support)
    if add_column_if_missing(conn, 'users', 'project_id', 'VARCHAR(50)', columns):
        migrations_applied += 1

    # Migration 6: study_start_date and study_end_date fields
    if add_column_if_missing(conn, 'users', 'study_start_date', 'DATE', columns):
        migrations_applied += 1

    if add_column_if_missing(conn, 'users', 'study_end_date', 'DATE', columns):
        migrations_applied += 1

    if migrations_applied > 0:
        print(f"  Applied {migrations_applied} migration(s) to users table")
    else:
        print("  No migrations needed for users table")

    return True


def migrate_admins_table(conn, inspector):
    """Apply all migrations to the admins table."""
    print("\n--- Admins Table Migrations ---")

    columns = get_table_columns(inspector, 'admins')
    if not columns:
        print("  [ERROR] Admins table not found")
        return False

    migrations_applied = 0

    # Migration: is_approved field
    if add_column_if_missing(conn, 'admins', 'is_approved', 'BOOLEAN DEFAULT 0', columns):
        migrations_applied += 1
        # Set existing admins to approved by default
        print("  [DATA] Setting existing admins to approved...")
        result = conn.execute(text('UPDATE admins SET is_approved = 1'))
        print(f"  [DATA] Set {result.rowcount} existing admin(s) to approved")

    if migrations_applied > 0:
        print(f"  Applied {migrations_applied} migration(s) to admins table")
    else:
        print("  No migrations needed for admins table")

    return True


def migrate_messages_table(conn, inspector):
    """Apply all migrations to the messages table."""
    print("\n--- Messages Table Migrations ---")

    columns = get_table_columns(inspector, 'messages')
    if not columns:
        print("  [ERROR] Messages table not found")
        return False

    migrations_applied = 0

    # Migration 5: is_risky field
    if add_column_if_missing(conn, 'messages', 'is_risky', 'BOOLEAN DEFAULT 0', columns):
        migrations_applied += 1

        # Migration 6: Migrate data from risk_score to is_risky (if risk_score exists)
        if 'risk_score' in columns:
            print("  [DATA] Migrating risk_score to is_risky...")
            result = conn.execute(text('''
                UPDATE messages
                SET is_risky = 1
                WHERE risk_score IS NOT NULL AND risk_score >= 0.7
            '''))
            print(f"  [DATA] Migrated {result.rowcount} messages to is_risky = True")
            print("  [NOTE] Old risk_score column kept for safety (not removed)")

    if migrations_applied > 0:
        print(f"  Applied {migrations_applied} migration(s) to messages table")
    else:
        print("  No migrations needed for messages table")

    return True


def run_migrations():
    """Run all database migrations."""
    print("=" * 60)
    print("Theradash Database Migration")
    print("=" * 60)

    with app.app_context():
        inspector = inspect(db.engine)

        with db.engine.connect() as conn:
            # Run all migrations
            users_ok = migrate_users_table(conn, inspector)
            admins_ok = migrate_admins_table(conn, inspector)
            messages_ok = migrate_messages_table(conn, inspector)

            # Commit all changes
            conn.commit()

        print("\n" + "=" * 60)
        if users_ok and admins_ok and messages_ok:
            print("Migration completed successfully!")
            print("\nNext steps:")
            print("1. Run a sync to populate new fields from REDCap/Firebase")
            print("2. Verify the dashboard displays data correctly")
        else:
            print("Migration completed with errors - check output above")
        print("=" * 60)


if __name__ == '__main__':
    run_migrations()
