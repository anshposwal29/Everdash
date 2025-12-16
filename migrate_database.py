#!/usr/bin/env python3
"""
Consolidated database migration script for Theradash.

This script handles all database schema updates in a single file.
It is idempotent - safe to run multiple times on the same database.

Migrations included:

Tables (created if missing):
- redcap_projects: Multi-project REDCap configuration
- user_custom_fields: Custom REDCap field values per user
- participant_notes: Notes about study participants

Columns (added if missing):
- users.identifier: Firebase Auth email/phone
- users.research_assistant: Assigned RA
- users.dropped, users.dropped_surveys: Participant status
- users.redcap_firebase_id: Display ID from REDCap
- users.project_id: Multi-project support
- users.study_start_date, users.study_end_date: Study dates
- admins.is_approved: Admin approval workflow
- messages.is_risky: Risk flag (migrates from risk_score if exists)

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


def table_exists(inspector, table_name):
    """Check if a table exists in the database."""
    return table_name in inspector.get_table_names()


def create_redcap_projects_table(conn, inspector):
    """Create the redcap_projects table if it doesn't exist."""
    print("\n--- REDCap Projects Table ---")

    if table_exists(inspector, 'redcap_projects'):
        print("  [SKIP] redcap_projects table already exists")
        return True

    print("  [CREATE] Creating redcap_projects table...")
    conn.execute(text('''
        CREATE TABLE redcap_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            api_url VARCHAR(500) NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    '''))
    conn.execute(text('CREATE INDEX idx_redcap_projects_project_id ON redcap_projects(project_id)'))
    print("  [CREATE] redcap_projects table created successfully")
    return True


def create_user_custom_fields_table(conn, inspector):
    """Create the user_custom_fields table if it doesn't exist."""
    print("\n--- User Custom Fields Table ---")

    if table_exists(inspector, 'user_custom_fields'):
        print("  [SKIP] user_custom_fields table already exists")
        return True

    print("  [CREATE] Creating user_custom_fields table...")
    conn.execute(text('''
        CREATE TABLE user_custom_fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            field_label VARCHAR(200),
            field_value TEXT,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    '''))
    conn.execute(text('CREATE INDEX idx_user_custom_fields_user_id ON user_custom_fields(user_id)'))
    conn.execute(text('CREATE INDEX idx_user_field ON user_custom_fields(user_id, field_name)'))
    print("  [CREATE] user_custom_fields table created successfully")
    return True


def create_participant_notes_table(conn, inspector):
    """Create the participant_notes table if it doesn't exist."""
    print("\n--- Participant Notes Table ---")

    if table_exists(inspector, 'participant_notes'):
        print("  [SKIP] participant_notes table already exists")
        return True

    print("  [CREATE] Creating participant_notes table...")
    conn.execute(text('''
        CREATE TABLE participant_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            admin_id INTEGER NOT NULL,
            note_text TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (admin_id) REFERENCES admins(id)
        )
    '''))
    conn.execute(text('CREATE INDEX idx_participant_notes_user_id ON participant_notes(user_id)'))
    conn.execute(text('CREATE INDEX idx_participant_notes_created_at ON participant_notes(created_at)'))
    print("  [CREATE] participant_notes table created successfully")
    return True


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
            # First, create any missing tables
            redcap_ok = create_redcap_projects_table(conn, inspector)
            custom_fields_ok = create_user_custom_fields_table(conn, inspector)
            notes_ok = create_participant_notes_table(conn, inspector)

            # Then, run column migrations on existing tables
            users_ok = migrate_users_table(conn, inspector)
            admins_ok = migrate_admins_table(conn, inspector)
            messages_ok = migrate_messages_table(conn, inspector)

            # Commit all changes
            conn.commit()

        print("\n" + "=" * 60)
        all_ok = redcap_ok and custom_fields_ok and notes_ok and users_ok and admins_ok and messages_ok
        if all_ok:
            print("Migration completed successfully!")
            print("\nNext steps:")
            print("1. Run a sync to populate new fields from REDCap/Firebase")
            print("2. Verify the dashboard displays data correctly")
        else:
            print("Migration completed with errors - check output above")
        print("=" * 60)


if __name__ == '__main__':
    run_migrations()
