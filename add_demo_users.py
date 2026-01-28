#!/usr/bin/env python3
"""
Script to add demo users to Firebase Authentication.
User documents in Firestore will be created automatically on first login.

Usage:
    python add_demo_users.py --count 5
    python add_demo_users.py --count 10 --start 1
"""

import argparse
import random
import csv
from datetime import datetime
from firebase_admin import auth
from services.firebase_service import firebase_service


# Characters for password generation (excluding confusing ones: I, l, O, 0)
PASSWORD_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'


def generate_password(length=12):
    """
    Generate a random alphanumeric password.
    Excludes confusing characters like I, l, O, 0.
    """
    return ''.join(random.choice(PASSWORD_CHARS) for _ in range(length))


def get_next_user_number(start_number=None):
    """
    Get the next available user number by checking existing users in Firestore.
    If start_number is provided, start from that number instead.
    """
    if start_number is not None:
        return start_number

    try:
        # Get all existing demo-internal users
        users = firebase_service.get_users()
        existing_numbers = []

        for user in users:
            email = user.get('email', '')
            if email.startswith('demo-internal-') and email.endswith('@test.com'):
                # Extract the number from email
                try:
                    num_str = email.replace('demo-internal-', '').replace('@test.com', '')
                    existing_numbers.append(int(num_str))
                except ValueError:
                    continue

        if existing_numbers:
            return max(existing_numbers) + 1
        else:
            return 1
    except Exception as e:
        print(f"Warning: Could not determine next user number: {e}")
        return 1


def create_demo_user(user_number, password):
    """
    Create a demo user in Firebase Authentication.
    User document in Firestore will be created automatically on first login.

    Args:
        user_number: The user number (e.g., 1 for demo-internal-001)
        password: The password for the user

    Returns:
        dict: User data including uid, email, and password
    """
    # Format email with 3-digit number
    email = f"demo-internal-{user_number:03d}@test.com"

    try:
        # Create user in Firebase Authentication
        user_record = auth.create_user(
            email=email,
            password=password,
            display_name=f"Demo User {user_number:03d}"
        )

        uid = user_record.uid
        print(f"✓ Created Firebase Auth user: {email} (UID: {uid})")

        return {
            'uid': uid,
            'email': email,
            'password': password,
            'success': True
        }

    except Exception as e:
        print(f"✗ Error creating user {email}: {e}")
        return {
            'email': email,
            'password': password,
            'error': str(e),
            'success': False
        }


def save_credentials_to_csv(users, filename=None):
    """
    Save user credentials to a CSV file for distribution to research assistants.

    Args:
        users: List of user dictionaries containing email, password, and uid
        filename: Optional custom filename (default: demo_users_YYYYMMDD_HHMMSS.csv)

    Returns:
        str: The filename where credentials were saved
    """
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'demo_users_{timestamp}.csv'

    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['email', 'password', 'uid', 'display_name']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for user in users:
            writer.writerow({
                'email': user['email'],
                'password': user['password'],
                'uid': user['uid'],
                'display_name': user['email'].replace('@test.com', '').replace('demo-internal-', 'Demo User ')
            })

    return filename


def main():
    parser = argparse.ArgumentParser(
        description='Add demo users to Firebase Authentication'
    )
    parser.add_argument(
        '--count',
        type=int,
        required=True,
        help='Number of users to create'
    )
    parser.add_argument(
        '--start',
        type=int,
        default=None,
        help='Starting user number (default: auto-detect next available)'
    )
    parser.add_argument(
        '--password-length',
        type=int,
        default=12,
        help='Length of generated passwords (default: 12)'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default=None,
        help='Save credentials to CSV file (default: demo_users_YYYYMMDD_HHMMSS.csv)'
    )
    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip creating CSV file'
    )

    args = parser.parse_args()

    if args.count < 1:
        print("Error: Count must be at least 1")
        return

    if args.password_length < 6:
        print("Error: Password length must be at least 6")
        return

    # Initialize Firebase
    print("Initializing Firebase...")
    firebase_service.initialize()
    print("✓ Firebase initialized\n")

    # Determine starting number
    start_num = get_next_user_number(args.start)
    print(f"Starting from user number: {start_num}\n")

    # Create users
    created_users = []
    failed_users = []

    print(f"Creating {args.count} demo users...\n")
    print("-" * 80)

    for i in range(args.count):
        user_num = start_num + i
        password = generate_password(args.password_length)

        result = create_demo_user(user_num, password)

        if result['success']:
            created_users.append(result)
        else:
            failed_users.append(result)

        print()  # Empty line between users

    print("-" * 80)
    print("\nSummary:")
    print(f"  Successfully created: {len(created_users)} users")
    print(f"  Failed: {len(failed_users)} users")
    print()

    # Display credentials
    if created_users:
        print("\n" + "=" * 80)
        print("CREDENTIALS FOR CREATED USERS")
        print("=" * 80)
        print(f"\n{'Email':<40} {'Password':<20} {'UID':<30}")
        print("-" * 80)
        for user in created_users:
            print(f"{user['email']:<40} {user['password']:<20} {user['uid']:<30}")
        print()
        print("⚠️  IMPORTANT: Save these credentials securely!")
        print("   Passwords cannot be retrieved later.")
        print("=" * 80)

    if failed_users:
        print("\n" + "=" * 80)
        print("FAILED USERS")
        print("=" * 80)
        for user in failed_users:
            print(f"  Email: {user['email']}")
            print(f"  Error: {user['error']}")
            print()

    # Save to CSV if requested (enabled by default)
    if created_users and not args.no_csv:
        try:
            csv_filename = save_credentials_to_csv(created_users, args.csv)
            print("\n" + "=" * 80)
            print("CSV FILE CREATED")
            print("=" * 80)
            print(f"✓ Credentials saved to: {csv_filename}")
            print(f"  Total users in file: {len(created_users)}")
            print("\n  This file can be used by research assistants to")
            print("  distribute credentials to internal testers via email.")
            print("=" * 80)
        except Exception as e:
            print(f"\n✗ Error creating CSV file: {e}")


if __name__ == '__main__':
    main()
