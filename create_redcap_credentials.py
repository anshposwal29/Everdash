#!/usr/bin/env python3
"""
Script to create Firebase Authentication credentials and add them to REDCap records.

This script:
1. Fetches records from REDCap based on filter logic
2. Creates Firebase Auth users with generated username/password
3. Updates REDCap records with the credentials

Usage:
    python create_redcap_credentials.py \
        --redcap-url "https://redcap.example.com/api/" \
        --redcap-token "YOUR_TOKEN" \
        --firebase-creds "/path/to/firebase-credentials.json" \
        --suffix "calm" \
        --username-length 6 \
        --password-length 10

    # With custom filter and field names:
    python create_redcap_credentials.py \
        --redcap-url "https://redcap.example.com/api/" \
        --redcap-token "YOUR_TOKEN" \
        --firebase-creds "/path/to/firebase-credentials.json" \
        --suffix "calm" \
        --filter '[screening_part_2_arm_1][randomization_group]="Treatment"' \
        --instrument "clinical_trial_monitoring" \
        --username-field "username" \
        --password-field "password"

    # When filter variable is in a different event from the credentials:
    # (e.g., randomization_group is in screening_part_2_arm_1 but
    # username/password fields are in baseline_arm_1)
    python create_redcap_credentials.py \
        --redcap-url "https://redcap.example.com/api/" \
        --redcap-token "YOUR_TOKEN" \
        --firebase-creds "/path/to/firebase-credentials.json" \
        --suffix "calm" \
        --filter '[randomization_group]="Treatment"' \
        --filter-event "screening_part_2_arm_1" \
        --event "baseline_arm_1" \
        --instrument "clinical_trial_monitoring"
"""

import argparse
import random
import csv
import json
import requests
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth


# Characters for credential generation (excluding confusing ones: I, l, 1, O, 0)
# For usernames - uppercase and digits only for clarity
USERNAME_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
# For passwords - mixed case and digits
PASSWORD_CHARS = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'


def generate_username(suffix, length):
    """
    Generate a username in email format with random alphanumeric prefix.
    Example: 6 chars + @calm.com = A3BX7K@calm.com
    """
    random_part = ''.join(random.choice(USERNAME_CHARS) for _ in range(length))
    return f"{random_part}@{suffix}.com"


def generate_password(length):
    """
    Generate a random alphanumeric password.
    Excludes confusing characters like I, l, 1, O, 0.
    """
    return ''.join(random.choice(PASSWORD_CHARS) for _ in range(length))


def fetch_record_ids_by_filter(api_url, api_token, filter_logic, filter_event=None):
    """
    Step 1: Fetch record IDs that match the filter logic.
    This is done separately because filterLogic only works within the requested event/form.
    """
    data = {
        'token': api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'fields': 'record_id',
        'filterLogic': filter_logic,
        'returnFormat': 'json'
    }

    if filter_event:
        data['events'] = filter_event

    try:
        response = requests.post(api_url, data=data, timeout=30)
        response.raise_for_status()
        records = response.json()
        # Extract unique record IDs
        record_ids = list(set(r.get('record_id') for r in records if r.get('record_id')))
        print(f"Found {len(record_ids)} records matching filter criteria")
        return record_ids
    except requests.exceptions.RequestException as e:
        print(f"Error fetching REDCap record IDs: {e}")
        raise


def fetch_redcap_records(api_url, api_token, filter_logic, instrument, event_name,
                         username_field, password_field, filter_event=None):
    """
    Fetch records from REDCap that match the filter logic.
    Uses a two-step approach to handle cross-event filtering:
    1. First fetch record IDs matching the filter (from filter_event if specified)
    2. Then fetch the credential fields from the target event/instrument

    Args:
        filter_event: The event where the filter variable lives (if different from event_name)
    """
    # Step 1: Get record IDs that match the filter
    # Use filter_event if specified, otherwise use the main event
    filter_event_to_use = filter_event if filter_event else event_name
    matching_record_ids = fetch_record_ids_by_filter(
        api_url, api_token, filter_logic, filter_event_to_use
    )

    if not matching_record_ids:
        return []

    # Step 2: Fetch credential fields for those records from the target event/instrument
    data = {
        'token': api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'forms': instrument,
        'fields': f'record_id,{username_field},{password_field}',
        'records': ','.join(matching_record_ids),
        'returnFormat': 'json'
    }

    if event_name:
        data['events'] = event_name

    try:
        response = requests.post(api_url, data=data, timeout=30)
        response.raise_for_status()
        records = response.json()
        print(f"Fetched {len(records)} records from REDCap for credential fields")
        return records
    except requests.exceptions.RequestException as e:
        print(f"Error fetching REDCap data: {e}")
        raise


def update_redcap_record(api_url, api_token, record_id, event_name,
                         username_field, username, password_field, password,
                         firebase_id_field=None, firebase_uid=None):
    """
    Update a REDCap record with the generated credentials.
    """
    record_data = [{
        'record_id': str(record_id),
        username_field: username,
        password_field: password
    }]

    if firebase_id_field and firebase_uid:
        record_data[0][firebase_id_field] = firebase_uid

    if event_name:
        record_data[0]['redcap_event_name'] = event_name

    data = {
        'token': api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'overwriteBehavior': 'overwrite',
        'data': json.dumps(record_data),
        'returnContent': 'count',
        'returnFormat': 'json'
    }

    try:
        response = requests.post(api_url, data=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get('count', 0) > 0
    except requests.exceptions.RequestException as e:
        print(f"Error updating REDCap record {record_id}: {e}")
        # Print response body for debugging
        if hasattr(e, 'response') and e.response is not None:
            print(f"  REDCap response: {e.response.text}")
        return False


def create_firebase_user(username, password):
    """
    Create a user in Firebase Authentication.
    Username is already in email format (e.g., A3BX7K@calm.com)

    Returns:
        tuple: (uid, error_message) - uid is None if creation failed
    """
    email = username.lower()

    try:
        user_record = auth.create_user(
            email=email,
            password=password,
            display_name=username.split('@')[0]  # Use the random part as display name
        )
        return user_record.uid, None
    except auth.EmailAlreadyExistsError:
        # User already exists, try to get existing user
        try:
            existing_user = auth.get_user_by_email(email)
            return existing_user.uid, "already_exists"
        except Exception as e:
            return None, f"User exists but could not retrieve: {e}"
    except Exception as e:
        return None, str(e)


def update_firebase_user_password(email, new_password):
    """
    Update password for an existing Firebase user.
    """
    try:
        user = auth.get_user_by_email(email)
        auth.update_user(user.uid, password=new_password)
        return True, user.uid
    except Exception as e:
        return False, str(e)


def prompt_overwrite(record_id, existing_username):
    """
    Prompt user to confirm overwriting existing credentials.
    """
    while True:
        response = input(
            f"\nRecord {record_id} already has credentials (username: {existing_username}). "
            f"Overwrite? [y/n/a(ll)/s(kip all)]: "
        ).strip().lower()

        if response in ['y', 'yes']:
            return 'yes'
        elif response in ['n', 'no']:
            return 'no'
        elif response in ['a', 'all']:
            return 'all'
        elif response in ['s', 'skip']:
            return 'skip_all'
        else:
            print("Please enter y(es), n(o), a(ll), or s(kip all)")


def save_credentials_to_csv(credentials_list, filename=None):
    """
    Save generated credentials to a CSV file.
    """
    if filename is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'redcap_credentials_{timestamp}.csv'

    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['record_id', 'username', 'password', 'firebase_uid', 'email', 'status']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for cred in credentials_list:
            writer.writerow(cred)

    return filename


def main():
    parser = argparse.ArgumentParser(
        description='Create Firebase credentials and add them to REDCap records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Required arguments
    parser.add_argument(
        '--redcap-url',
        type=str,
        required=True,
        help='REDCap API URL (e.g., https://redcap.example.com/api/)'
    )
    parser.add_argument(
        '--redcap-token',
        type=str,
        required=True,
        help='REDCap API token'
    )
    parser.add_argument(
        '--firebase-creds',
        type=str,
        required=True,
        help='Path to Firebase service account credentials JSON file'
    )
    parser.add_argument(
        '--suffix',
        type=str,
        required=True,
        help='Email domain suffix (e.g., "calm" creates usernames like A3BX7K@calm.com)'
    )

    # Optional arguments with defaults
    parser.add_argument(
        '--filter',
        type=str,
        default='[screening_part_2_arm_1][randomization_group]="Treatment"',
        help='REDCap filter logic (default: [screening_part_2_arm_1][randomization_group]="Treatment")'
    )
    parser.add_argument(
        '--instrument',
        type=str,
        default='clinical_trial_monitoring',
        help='REDCap instrument/form name (default: clinical_trial_monitoring)'
    )
    parser.add_argument(
        '--event',
        type=str,
        default='screening_part_2_arm_1',
        help='REDCap event name where credentials will be stored (default: screening_part_2_arm_1)'
    )
    parser.add_argument(
        '--filter-event',
        type=str,
        default=None,
        help='REDCap event name where the filter variable lives (if different from --event). '
             'Use this when filtering on a variable in a different event than where credentials are stored.'
    )
    parser.add_argument(
        '--username-field',
        type=str,
        default='username',
        help='REDCap field name for username (default: username)'
    )
    parser.add_argument(
        '--password-field',
        type=str,
        default='password',
        help='REDCap field name for password (default: password)'
    )
    parser.add_argument(
        '--firebase-id-field',
        type=str,
        default=None,
        help='REDCap field name for Firebase UID (optional, e.g., firebase_id)'
    )
    parser.add_argument(
        '--username-length',
        type=int,
        default=6,
        help='Length of random part of username (default: 6)'
    )
    parser.add_argument(
        '--password-length',
        type=int,
        default=10,
        help='Length of generated password (default: 10)'
    )
    parser.add_argument(
        '--csv',
        type=str,
        default=None,
        help='Output CSV filename (default: redcap_credentials_YYYYMMDD_HHMMSS.csv)'
    )
    parser.add_argument(
        '--no-csv',
        action='store_true',
        help='Skip creating CSV file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be done without making changes'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.username_length < 4:
        print("Error: Username length must be at least 4")
        return
    if args.password_length < 8:
        print("Error: Password length must be at least 8 for security")
        return

    # Initialize Firebase
    print("Initializing Firebase...")
    try:
        cred = credentials.Certificate(args.firebase_creds)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully\n")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        return

    # Fetch REDCap records
    print(f"Fetching records from REDCap...")
    print(f"  Filter: {args.filter}")
    print(f"  Filter event: {args.filter_event or args.event}")
    print(f"  Credentials event: {args.event}")
    print(f"  Instrument: {args.instrument}")
    print()

    try:
        records = fetch_redcap_records(
            args.redcap_url,
            args.redcap_token,
            args.filter,
            args.instrument,
            args.event,
            args.username_field,
            args.password_field,
            args.filter_event
        )
    except Exception as e:
        print(f"Failed to fetch REDCap records: {e}")
        return

    if not records:
        print("No records found matching the filter criteria.")
        return

    # Process records
    print(f"\nProcessing {len(records)} records...\n")
    print("-" * 80)

    created_credentials = []
    skipped_records = []
    failed_records = []
    overwrite_all = False
    skip_all = False

    for record in records:
        record_id = record.get('record_id')
        existing_username = record.get(args.username_field, '').strip()
        existing_password = record.get(args.password_field, '').strip()

        # Check if credentials already exist
        if existing_username and existing_password:
            if skip_all:
                print(f"Skipping record {record_id} (existing credentials)")
                skipped_records.append({
                    'record_id': record_id,
                    'username': existing_username,
                    'reason': 'skip_all'
                })
                continue

            if not overwrite_all:
                response = prompt_overwrite(record_id, existing_username)
                if response == 'no':
                    print(f"Skipping record {record_id}")
                    skipped_records.append({
                        'record_id': record_id,
                        'username': existing_username,
                        'reason': 'user_declined'
                    })
                    continue
                elif response == 'skip_all':
                    skip_all = True
                    print(f"Skipping record {record_id} and all remaining with credentials")
                    skipped_records.append({
                        'record_id': record_id,
                        'username': existing_username,
                        'reason': 'skip_all'
                    })
                    continue
                elif response == 'all':
                    overwrite_all = True
                    print("Will overwrite all existing credentials")

        # Generate new credentials
        username = generate_username(args.suffix, args.username_length)
        password = generate_password(args.password_length)

        print(f"\nRecord {record_id}:")
        print(f"  Username: {username}")
        print(f"  Password: {password}")

        if args.dry_run:
            print(f"  [DRY RUN] Would create Firebase user and update REDCap")
            created_credentials.append({
                'record_id': record_id,
                'username': username,
                'password': password,
                'firebase_uid': 'DRY_RUN',
                'email': username.lower(),
                'status': 'dry_run'
            })
            continue

        # Create Firebase user
        firebase_uid, error = create_firebase_user(username, password)

        if error == "already_exists":
            # Update password for existing user
            print(f"  Firebase user exists, updating password...")
            email = username.lower()
            success, result = update_firebase_user_password(email, password)
            if success:
                firebase_uid = result
                print(f"  Firebase password updated (UID: {firebase_uid})")
            else:
                print(f"  Failed to update Firebase password: {result}")
                failed_records.append({
                    'record_id': record_id,
                    'username': username,
                    'error': f"Firebase password update failed: {result}"
                })
                continue
        elif error:
            print(f"  Failed to create Firebase user: {error}")
            failed_records.append({
                'record_id': record_id,
                'username': username,
                'error': f"Firebase creation failed: {error}"
            })
            continue
        else:
            print(f"  Firebase user created (UID: {firebase_uid})")

        # Update REDCap record
        success = update_redcap_record(
            args.redcap_url,
            args.redcap_token,
            record_id,
            args.event,
            args.username_field,
            username,
            args.password_field,
            password,
            args.firebase_id_field,
            firebase_uid
        )

        if success:
            print(f"  REDCap record updated successfully")
            created_credentials.append({
                'record_id': record_id,
                'username': username,
                'password': password,
                'firebase_uid': firebase_uid,
                'email': username.lower(),
                'status': 'created'
            })
        else:
            print(f"  Failed to update REDCap record")
            failed_records.append({
                'record_id': record_id,
                'username': username,
                'error': 'REDCap update failed'
            })

    # Summary
    print("\n" + "-" * 80)
    print("\nSUMMARY")
    print("=" * 80)
    print(f"  Total records processed: {len(records)}")
    print(f"  Credentials created: {len(created_credentials)}")
    print(f"  Skipped (existing): {len(skipped_records)}")
    print(f"  Failed: {len(failed_records)}")

    # Display created credentials
    if created_credentials:
        print("\n" + "=" * 80)
        print("CREATED CREDENTIALS")
        print("=" * 80)
        print(f"\n{'Record ID':<12} {'Username':<20} {'Password':<15} {'Firebase UID':<30}")
        print("-" * 80)
        for cred in created_credentials:
            print(f"{cred['record_id']:<12} {cred['username']:<20} {cred['password']:<15} {cred['firebase_uid']:<30}")

    # Display failed records
    if failed_records:
        print("\n" + "=" * 80)
        print("FAILED RECORDS")
        print("=" * 80)
        for record in failed_records:
            print(f"  Record {record['record_id']}: {record['error']}")

    # Save to CSV
    if created_credentials and not args.no_csv:
        try:
            csv_filename = save_credentials_to_csv(created_credentials, args.csv)
            print("\n" + "=" * 80)
            print("CSV FILE CREATED")
            print("=" * 80)
            print(f"  Credentials saved to: {csv_filename}")
            print(f"  Total records in file: {len(created_credentials)}")
        except Exception as e:
            print(f"\nError creating CSV file: {e}")

    print("\n" + "=" * 80)
    if not args.dry_run:
        print("IMPORTANT: Save these credentials securely!")
        print("Passwords cannot be retrieved from Firebase later.")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
