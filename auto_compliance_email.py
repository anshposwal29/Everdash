#!/usr/bin/env python3
"""
Automated Compliance Email Script for Theradash

This script sends reminder emails to participants who haven't interacted
with the app in the last N days (default: 2 days), and also sends welcome
emails with login credentials to participants who have never logged in.

Run this script as a daily cron job:
    0 9 * * * /path/to/venv/bin/python /path/to/theradash/auto_compliance_email.py

Features:
- Pulls participant data from REDCap (email, first_name, username, password, etc.)
- Checks Firebase Auth to detect users who have never logged in
- Sends welcome emails with credentials and download instructions to never-logged-in users
- Checks message activity in the local database for logged-in users
- Sends personalized reminder emails to inactive users
- Logs all email correspondence to the Notes table (passwords are redacted)
- Skips participants who:
  - Have dropped from the study
  - Are past their intervention end date
  - Have interacted within the lookback period

Configuration (via .env file):
    EMAIL_SMTP_SERVER: SMTP server address (default: smtp.office365.com)
    EMAIL_SMTP_PORT: SMTP port (default: 587)
    EMAIL_USERNAME: SMTP login username
    EMAIL_PASSWORD: SMTP login password
    EMAIL_FROM_ADDRESS: From address for emails
    EMAIL_LOOKBACK_DAYS: Days of inactivity before sending email (default: 2)
    EMAIL_DRY_RUN: Set to 'true' to preview emails without sending (default: false)
    EMAIL_TEST_RECIPIENT: If set, all emails go to this address instead (for testing)

Usage:
    python auto_compliance_email.py                    # Run with default settings
    python auto_compliance_email.py --dry-run          # Preview without sending
    python auto_compliance_email.py --lookback 3       # Use 3-day lookback
    python auto_compliance_email.py --test-email user@example.com  # Send to test email

Author: Theradash Team
"""

import re
import sys
import argparse
import random
import smtplib
from datetime import datetime, timedelta
import pytz
import os
import msal
import requests
import json
from dotenv import load_dotenv

# 1. Load the .env file immediately
load_dotenv()

# Add the project root to the path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import User, Message, Notes
from config import Config
from services.firebase_service import firebase_service


# Email configuration - loaded from environment
EMAIL_SMTP_PORT = int(os.environ.get('EMAIL_SMTP_PORT', 587))
EMAIL_USERNAME = os.environ.get('EMAIL_USERNAME', '')
EMAIL_FROM_ADDRESS = os.environ.get('EMAIL_FROM_ADDRESS', 'therabot@dartmouth.edu')
EMAIL_LOOKBACK_DAYS = int(os.environ.get('EMAIL_LOOKBACK_DAYS', 2))
EMAIL_DRY_RUN = os.environ.get('EMAIL_DRY_RUN', 'false').lower() == 'true'
EMAIL_TEST_RECIPIENT = os.environ.get('EMAIL_TEST_RECIPIENT', '')

CLIENT_ID = '9d05976b-2ab6-4415-84a0-6d9c077babb6'
TENANT_ID = '995b0936-48d6-40e5-a31e-bf689ec9446f'
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES = ['https://graph.microsoft.com/Mail.Send']
CACHE_FILE = 'token_cache.bin'

# Timezone
ET_TZ = pytz.timezone('US/Eastern')

# Email templates - randomly selected for variety
EMAIL_TEMPLATES = [
    """\
Hello {first_name},<br><br>
It's {ra_first_name} getting in touch from the Dartmouth Therabot Team. I've noticed that you haven't been interacting much with Therabot over the past few days. We ask that you please interact with the Therabot app for at least five minutes each day.<br><br>
If you need any assistance, please don't hesitate to reach out to us at (603) 646-7015 or therabot@dartmouth.edu.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
""",
    """\
Dear {first_name},<br><br>
Thank you for taking the initial step in the study by downloading the Therabot app. To maximize your experience and benefit from this study, we ask that you please begin using the Therabot mobile application.<br><br>
If you need assistance or have any questions or feedback, please reach out to us at (603) 646-7015 or therabot@dartmouth.edu. We appreciate your commitment to the study and look forward to hearing about your progress.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
""",
    """\
Hello {first_name},<br><br>
We're delighted that you've taken the first step in our study by downloading the Therabot app. To get the most out of this study and enhance your experience, we kindly ask that you start engaging with the Therabot mobile app.<br><br>
Should you require any support, or if you have questions or wish to share your feedback, please don't hesitate to contact us at (603) 646-7015 or via email at therabot@dartmouth.edu. Your dedication to this study is highly valued, and we're eager to learn about your journey.<br><br>
Many thanks,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (feel free to call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
""",
    """\
Dear {first_name},<br><br>
Thank you for embarking on this journey with us by downloading the Therabot app. To ensure you gain the fullest experience and benefit from participating in this study, we encourage you to start utilizing the Therabot mobile app.<br><br>
For any assistance, questions, or to provide feedback, you are welcome to reach out to us at (603) 646-7015 or therabot@dartmouth.edu. We value your participation in the study and are keen to track your progress.<br><br>
Warm regards,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (available for calls or texts!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""
]


# Email template for participants who have never logged in
NEVER_LOGGED_IN_TEMPLATE = """\
Hello {first_name},<br><br>
It's {ra_first_name} getting in touch from the Dartmouth Therabot Team. We noticed that you haven't logged into the Therabot app yet. We wanted to reach out to make sure you have everything you need to get started.<br><br>
<strong>Your Login Credentials:</strong><br>
Username: {username}<br>
Password: {password}<br><br>
<strong>Download Instructions:</strong><br>
Please look for an email sent from Firebase that includes a link to download the app.<br><br>
<strong>For iPhone/iPad Users - Additional Steps:</strong><br>
After downloading the app, you will need to trust the developer certificate:<br>
<ol>
<li>Open <strong>Settings</strong> on your iPhone</li>
<li>Go to <strong>General → VPN & Device Management</strong></li>
<li>Under "Enterprise App," tap <strong>Dartmouth College</strong></li>
<li>Tap <strong>Trust "Dartmouth College"</strong> and confirm by tapping Trust</li>
<li>You may need to restart your phone after this step</li>
</ol>
<br>
Once you've downloaded the app, please log in using the credentials above and start interacting with Therabot. We ask that you please interact with the Therabot app for at least five minutes each day.<br><br>
If you need any assistance or have trouble logging in, please don't hesitate to reach out to us at (603) 646-7015 or therabot@dartmouth.edu.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""


def get_redcap_participant_data():
    """
    Fetch participant data from REDCap including email, first_name, phone, etc.
    Returns a dict keyed by record_id with participant details.
    """
    participants = {}

    for project_config in Config.get_all_projects():
        if not project_config.api_url or not project_config.api_token:
            continue

        # Fields to request from REDCap (main event)
        fields = [
            'record_id',
            project_config.firebase_id_field,
            project_config.ra_field,
            'first_name',
            'phone_number',
            'dropped',
            'randomization_group',
            'username',
            'password',
        ]

        # Only include email in main request if no separate email_event is configured
        if not project_config.email_event:
            fields.append('email')

        # Add study date fields if configured
        if project_config.study_start_date_field:
            fields.append(project_config.study_start_date_field)
        if project_config.study_end_date_field:
            fields.append(project_config.study_end_date_field)

        data = {
            'token': project_config.api_token,
            'content': 'record',
            'format': 'json',
            'type': 'flat',
            'fields': ','.join(fields),
            'filterLogic': project_config.filter_logic,
            'returnFormat': 'json'
        }

        if project_config.event_name:
            data['events'] = project_config.event_name

        try:
            response = requests.post(project_config.api_url, data=data, timeout=30)
            response.raise_for_status()
            redcap_data = response.json()

            for entry in redcap_data:
                record_id = entry.get('record_id')
                if not record_id:
                    continue

                participants[record_id] = {
                    'record_id': record_id,
                    'firebase_id': entry.get(project_config.firebase_id_field, '').strip(),
                    'research_assistant': entry.get(project_config.ra_field, '').strip(),
                    'email': entry.get('email', '').strip() if not project_config.email_event else '',
                    'first_name': entry.get('first_name', '').strip(),
                    'phone_number': entry.get('phone_number', '').strip(),
                    'dropped': entry.get('dropped', '') == '1',
                    'randomization_group': entry.get('randomization_group', '').strip(),
                    'intervention_start_date': entry.get(project_config.study_start_date_field, '') if project_config.study_start_date_field else '',
                    'intervention_end_date': entry.get(project_config.study_end_date_field, '') if project_config.study_end_date_field else '',
                    'project_id': project_config.id,
                    'username': entry.get('username', '').strip(),
                    'password': entry.get('password', '').strip(),
                }

            print(f"Fetched {len(redcap_data)} participants from REDCap project: {project_config.name}")

            # If email_event is configured, fetch emails from that event separately
            if project_config.email_event:
                email_data = {
                    'token': project_config.api_token,
                    'content': 'record',
                    'format': 'json',
                    'type': 'flat',
                    'fields': 'record_id,email',
                    'events': project_config.email_event,
                    'returnFormat': 'json'
                }

                try:
                    email_response = requests.post(project_config.api_url, data=email_data, timeout=30)
                    email_response.raise_for_status()
                    email_records = email_response.json()

                    email_count = 0
                    for email_entry in email_records:
                        record_id = email_entry.get('record_id')
                        email = email_entry.get('email', '').strip()
                        if record_id and record_id in participants and email:
                            participants[record_id]['email'] = email
                            email_count += 1

                    print(f"  Fetched {email_count} emails from event: {project_config.email_event}")

                except Exception as e:
                    print(f"  Error fetching emails from {project_config.email_event}: {e}")

        except Exception as e:
            print(f"Error fetching REDCap data from {project_config.name}: {e}")

    return participants


def is_past_intervention_end_date(end_date_str):
    """Check if current date is past the intervention end date."""
    if not end_date_str:
        return False
    try:
        end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
        return datetime.today().date() >= end_date
    except ValueError:
        return False


def is_within_intervention_window(start_date_str, end_date_str):
    """Check if current date is within the intervention window."""
    today = datetime.today().date()

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
            if today < start_date:
                return False
        except ValueError:
            pass

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
            if today > end_date:
                return False
        except ValueError:
            pass

    return True


def get_message_counts_for_user(user_id, lookback_days):
    """
    Get message counts for each day in the lookback period for a user.
    Returns a list of counts (most recent day first).
    """
    counts = []
    now_et = datetime.now(ET_TZ)

    for days_ago in range(lookback_days + 1):
        date = (now_et - timedelta(days=days_ago)).date()

        # Convert date to UTC range for database query
        date_start = ET_TZ.localize(datetime.combine(date, datetime.min.time()))
        date_end = ET_TZ.localize(datetime.combine(date, datetime.max.time()))
        start_utc = date_start.astimezone(pytz.utc).replace(tzinfo=None)
        end_utc = date_end.astimezone(pytz.utc).replace(tzinfo=None)

        count = Message.query.filter(
            Message.user_id == user_id,
            Message.timestamp >= start_utc,
            Message.timestamp <= end_utc
        ).count()

        counts.append(count)

    return counts


def has_ever_sent_messages(user_id):
    """Check if a user has ever sent any messages."""
    return Message.query.filter_by(user_id=user_id).count() > 0


def has_received_email_recently(participant_id, hours=24):
    """
    Check if a participant has received an auto-compliance email in the last N hours.
    Returns True if an email was sent recently, False otherwise.
    """
    cutoff_time = datetime.now() - timedelta(hours=hours)
    cutoff_str = cutoff_time.strftime('%Y-%m-%dT%H:%M')

    recent_email = Notes.query.filter(
        Notes.participant_id == str(participant_id),
        Notes.note_type == 'Email',
        Notes.note_reason == 'Auto-Compliance',
        Notes.datetime >= cutoff_str
    ).first()

    return recent_email is not None


def clean_and_capitalize(name):
    """Clean and capitalize a name string."""
    if not name:
        return ''
    cleaned = name.strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:] if len(cleaned) > 1 else cleaned.upper()
    return cleaned


def get_first_name(full_name):
    """Extract first name from a full name string."""
    if not full_name:
        return ''
    return full_name.strip().split()[0] if full_name.strip() else ''


def create_email_body(template, first_name, ra_first_name):
    """Create email body from template with personalization."""
    return template.format(
        first_name=first_name,
        ra_first_name=ra_first_name
    )


def create_never_logged_in_email_body(first_name, ra_first_name, username, password):
    """Create email body for never-logged-in users with credentials."""
    return NEVER_LOGGED_IN_TEMPLATE.format(
        first_name=first_name,
        ra_first_name=ra_first_name,
        username=username,
        password=password
    )


def check_user_has_logged_in(firebase_id):
    """
    Check if a user has ever logged into Firebase.
    Returns True if logged in, False if never logged in, None if error/not found.
    """
    if not firebase_id or firebase_id.startswith('redcap_'):
        # Placeholder IDs can't have login history
        return None
    try:
        return firebase_service.has_user_ever_logged_in(firebase_id)
    except Exception as e:
        print(f"  [ERROR] Failed to check login status for {firebase_id}: {e}")
        return None


def get_access_token():
    """Handles the OAuth2 token acquisition and caching."""
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache
    )

    # Try to get token silently from cache
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # If no valid token in cache, perform Device Code Flow (Initial Setup)
    if not result:
        print("No valid token found. Starting Device Code Flow...")
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise ValueError("Fail to create device flow. Err: %s" % json.dumps(flow, indent=4))

        print(flow["message"])  # This tells the user where to go and what code to enter
        result = app.acquire_token_by_device_flow(flow)

    # Save the cache if it changed
    if cache.has_state_changed:
        with open(CACHE_FILE, "w") as f:
            f.write(cache.serialize())

    if "access_token" in result:
        return result['access_token']
    else:
        raise Exception(f"Could not acquire token: {result.get('error_description')}")


def send_email(to_email, subject, html_body, dry_run=False):
    """Replaces the old smtplib logic with Microsoft Graph API."""
    if dry_run:
        print(f"  [DRY RUN] Would send Graph API email to: {to_email}")
        print(f"  [DRY RUN] Subject: {subject}")
        print(f"  [DRY RUN] Email body:")
        print("-" * 40)
        # Convert HTML to plain text for console readability
        plain_body = html_body.replace('<br>', '\n').replace('<br/>', '\n')
        plain_body = re.sub(r'<[^>]+>', '', plain_body)  # Strip HTML tags
        print(plain_body)
        print("-" * 40)
        return True

    try:
        token = get_access_token()
        endpoint = "https://graph.microsoft.com/v1.0/me/sendMail"

        # Prepare the JSON payload for Graph API
        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ]
            },
            "saveToSentItems": "true"
        }

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        response = requests.post(endpoint, headers=headers, json=email_data)

        if response.status_code == 202:
            print(f"  [SENT] OAuth Email sent successfully to {to_email}")
            return True
        else:
            print(f"  [ERROR] Graph API Error {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"  [ERROR] Failed to send OAuth email: {e}")
        return False


def log_email_to_notes(participant_id, email_body, dry_run=False):
    """Log the sent email to the Notes table."""
    if dry_run:
        print(f"  [DRY RUN] Would log note for participant: {participant_id}")
        return

    try:
        note = Notes(
            admin_id=999,  # System/automated admin ID
            participant_id=str(participant_id),
            note_type='Email',
            note_reason='Auto-Compliance',
            datetime=datetime.now().strftime('%Y-%m-%dT%H:%M'),
            duration='N/A',
            note=email_body
        )
        db.session.add(note)
        db.session.commit()
        print(f"  [LOGGED] Note created for participant {participant_id}")
    except Exception as e:
        print(f"  [ERROR] Failed to log note for participant {participant_id}: {e}")
        db.session.rollback()


def run_compliance_check(lookback_days=None, dry_run=None, test_email=None):
    """
    Main function to check compliance and send reminder emails.

    Args:
        lookback_days: Number of days to check for inactivity
        dry_run: If True, preview emails without sending
        test_email: If set, send all emails to this address instead
    """
    # Use arguments or fall back to environment defaults
    lookback = lookback_days if lookback_days is not None else EMAIL_LOOKBACK_DAYS
    is_dry_run = dry_run if dry_run is not None else EMAIL_DRY_RUN
    test_recipient = test_email if test_email else EMAIL_TEST_RECIPIENT

    print("=" * 60)
    print("Theradash Automated Compliance Email Check")
    print("=" * 60)
    print(f"Timestamp: {datetime.now(ET_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Lookback period: {lookback} days")
    print(f"Dry run mode: {is_dry_run}")
    if test_recipient:
        print(f"Test recipient: {test_recipient}")
    print()

    # Initialize Firebase for login checks
    print("Initializing Firebase...")
    try:
        firebase_service.initialize()
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Warning: Failed to initialize Firebase: {e}")
        print("Will skip never-logged-in checks")
    print()

    # Get participant data from REDCap
    print("Fetching participant data from REDCap...")
    redcap_participants = get_redcap_participant_data()
    print(f"Found {len(redcap_participants)} participants in REDCap")
    print()

    # Get users from local database
    users = User.query.filter_by(is_active=True).all()
    print(f"Found {len(users)} active users in local database")
    print()

    # Build a mapping of redcap_id to user
    users_by_redcap_id = {user.redcap_id: user for user in users if user.redcap_id}

    # Track statistics
    stats = {
        'total_checked': 0,
        'emails_sent': 0,
        'never_logged_in_emails_sent': 0,
        'skipped_dropped': 0,
        'skipped_past_end': 0,
        'skipped_compliant': 0,
        'skipped_recent_email': 0,
        'skipped_no_email': 0,
        'skipped_not_in_db': 0,
        'skipped_no_credentials': 0,
        'errors': 0,
    }

    # Zero counts list for comparison
    zero_counts = [0] * (lookback + 1)

    print("Processing participants...")
    print("-" * 60)

    for record_id, participant in redcap_participants.items():
        stats['total_checked'] += 1

        study = participant.get('project_id', 'unknown').upper()
        print(f"\nParticipant: {record_id} (Study: {study})")

        # Skip if dropped
        if participant['dropped']:
            print(f"  [SKIP] Dropped from study")
            stats['skipped_dropped'] += 1
            continue

        # Skip if past intervention end date
        if is_past_intervention_end_date(participant['intervention_end_date']):
            print(f"  [SKIP] Past intervention end date ({participant['intervention_end_date']})")
            stats['skipped_past_end'] += 1
            continue

        # Skip if not within intervention window
        if not is_within_intervention_window(
            participant['intervention_start_date'],
            participant['intervention_end_date']
        ):
            print(f"  [SKIP] Not within intervention window")
            stats['skipped_past_end'] += 1
            continue

        # Find user in local database
        user = users_by_redcap_id.get(record_id)
        if not user:
            # Try by firebase_id
            firebase_id = participant['firebase_id']
            if firebase_id:
                user = User.query.filter_by(firebase_id=firebase_id).first()

        if not user:
            print(f"  [SKIP] Not found in local database")
            stats['skipped_not_in_db'] += 1
            continue

        # Check if we have an email address (needed for all email types)
        email = participant['email']
        if not email:
            print(f"  [SKIP] No email address available")
            stats['skipped_no_email'] += 1
            continue

        # Check if participant already received an email in the last 24 hours
        if has_received_email_recently(record_id, hours=24):
            print(f"  [SKIP] Already received an email in the last 24 hours")
            stats['skipped_recent_email'] += 1
            continue

        # Check if user has ever logged in to Firebase
        firebase_id = participant['firebase_id'] or user.firebase_id
        has_logged_in = check_user_has_logged_in(firebase_id)

        if has_logged_in is False:
            # User has never logged in - send credentials email
            print(f"  [NEVER LOGGED IN] User has never logged into the app")

            # Check if we have credentials to send
            username = participant['username']
            password = participant['password']

            if not username or not password:
                print(f"  [SKIP] No username/password available in REDCap")
                stats['skipped_no_credentials'] += 1
                continue

            # Prepare never-logged-in email
            first_name = clean_and_capitalize(participant['first_name']) or 'Participant'
            ra_name = participant['research_assistant'] or 'The Research Team'
            ra_first_name = get_first_name(ra_name) or 'The Research Team'

            email_body = create_never_logged_in_email_body(first_name, ra_first_name, username, password)
            email_subject = "Therabot App - Getting Started"

            # Determine recipient
            recipient = test_recipient if test_recipient else email

            # Send email
            success = send_email(recipient, email_subject, email_body, dry_run=is_dry_run)

            if success:
                stats['never_logged_in_emails_sent'] += 1
                # Log to notes table
                # Redact password in the logged note
                logged_body = email_body.replace(password, '********')
                log_email_to_notes(record_id, logged_body, dry_run=is_dry_run)
            else:
                stats['errors'] += 1
            continue

        # Get message counts for lookback period
        message_counts = get_message_counts_for_user(user.id, lookback)
        print(f"  Message counts (last {lookback + 1} days): {message_counts}")

        # Check if all counts are zero
        if message_counts != zero_counts:
            print(f"  [SKIP] Compliant - has recent activity")
            stats['skipped_compliant'] += 1
            continue

        # User needs a reminder email
        print(f"  [NEEDS EMAIL] No activity in last {lookback} days")

        # Prepare email
        first_name = clean_and_capitalize(participant['first_name']) or 'Participant'
        ra_name = participant['research_assistant'] or 'The Research Team'
        ra_first_name = get_first_name(ra_name) or 'The Research Team'

        # Select random email template
        template = random.choice(EMAIL_TEMPLATES)
        email_body = create_email_body(template, first_name, ra_first_name)
        email_subject = "Therabot Study Team Checking In"

        # Determine recipient
        recipient = test_recipient if test_recipient else email

        # Send email
        success = send_email(recipient, email_subject, email_body, dry_run=is_dry_run)

        if success:
            stats['emails_sent'] += 1
            # Log to notes table
            log_email_to_notes(record_id, email_body, dry_run=is_dry_run)
        else:
            stats['errors'] += 1

    # Print summary
    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total participants checked: {stats['total_checked']}")
    print(f"Compliance reminder emails sent: {stats['emails_sent']}")
    print(f"Never-logged-in emails sent: {stats['never_logged_in_emails_sent']}")
    print(f"Skipped - dropped: {stats['skipped_dropped']}")
    print(f"Skipped - past end date: {stats['skipped_past_end']}")
    print(f"Skipped - compliant: {stats['skipped_compliant']}")
    print(f"Skipped - recent email (24h): {stats['skipped_recent_email']}")
    print(f"Skipped - no email: {stats['skipped_no_email']}")
    print(f"Skipped - not in DB: {stats['skipped_not_in_db']}")
    print(f"Skipped - no credentials: {stats['skipped_no_credentials']}")
    print(f"Errors: {stats['errors']}")
    print("=" * 60)

    return stats


def main():
    """Main entry point with command-line argument parsing."""
    parser = argparse.ArgumentParser(
        description='Send compliance reminder emails to inactive participants',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auto_compliance_email.py                         # Run with defaults
  python auto_compliance_email.py --dry-run               # Preview without sending
  python auto_compliance_email.py --lookback 3            # Use 3-day lookback
  python auto_compliance_email.py --test-email me@ex.com  # Send to test address
        """
    )

    parser.add_argument(
        '--dry-run', '-d',
        action='store_true',
        help='Preview emails without actually sending them'
    )

    parser.add_argument(
        '--lookback', '-l',
        type=int,
        default=None,
        help=f'Number of days to check for inactivity (default: {EMAIL_LOOKBACK_DAYS})'
    )

    parser.add_argument(
        '--test-email', '-t',
        type=str,
        default=None,
        help='Send all emails to this test address instead of actual recipients'
    )

    args = parser.parse_args()

    # Run within Flask app context for database access
    with app.app_context():
        run_compliance_check(
            lookback_days=args.lookback,
            dry_run=args.dry_run,
            test_email=args.test_email
        )


if __name__ == '__main__':
    main()
