#!/usr/bin/env python3
"""
One-time script to find and sync missing conversations and messages
between Firebase and the local theradash.db.

This script compares all data in Firebase with the local database and
syncs any conversations or messages that are missing locally.

Usage:
    python sync_missing_data.py [--dry-run]

Options:
    --dry-run   Show what would be synced without actually syncing
"""

import sys
import os

# Add the parent directory to the path so we can import from the app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Conversation, Message
from services.firebase_service import firebase_service
from services.twilio_service import twilio_service
from datetime import datetime


def find_missing_conversations(dry_run=False):
    """
    Find conversations in Firebase that are missing from the local database.
    Returns list of missing conversation data.
    """
    print("\n" + "=" * 60)
    print("CHECKING CONVERSATIONS")
    print("=" * 60)

    # Get all conversations from Firebase (no timestamp filter)
    firebase_convos = firebase_service.get_conversations_since(since_timestamp=None)
    print(f"Found {len(firebase_convos)} total conversations in Firebase")

    # Get all conversation IDs from local database
    local_convo_ids = set(
        c.firebase_convo_id for c in Conversation.query.all()
    )
    print(f"Found {len(local_convo_ids)} conversations in local database")

    # Find missing conversations
    missing_convos = []
    for fb_convo in firebase_convos:
        firebase_convo_id = fb_convo.get('firebase_convo_id')
        if firebase_convo_id not in local_convo_ids:
            missing_convos.append(fb_convo)

    print(f"Found {len(missing_convos)} missing conversations")

    if missing_convos:
        print("\nMissing conversations:")
        for convo in missing_convos:
            user_id = convo.get('userID', 'unknown')
            timestamp = convo.get('timestamp', 'unknown')
            print(f"  - {convo.get('firebase_convo_id')} (user: {user_id}, timestamp: {timestamp})")

    return missing_convos


def find_missing_messages(dry_run=False):
    """
    Find messages in Firebase that are missing from the local database.
    Returns list of missing message data.
    """
    print("\n" + "=" * 60)
    print("CHECKING MESSAGES")
    print("=" * 60)

    # Get all messages from Firebase (no timestamp filter)
    firebase_messages = firebase_service.get_messages_since(since_timestamp=None)
    print(f"Found {len(firebase_messages)} total messages in Firebase")

    # Get all message IDs from local database
    local_message_ids = set(
        m.firebase_message_id for m in Message.query.all()
    )
    print(f"Found {len(local_message_ids)} messages in local database")

    # Find missing messages
    missing_messages = []
    for fb_message in firebase_messages:
        firebase_message_id = fb_message.get('firebase_message_id')
        if firebase_message_id not in local_message_ids:
            missing_messages.append(fb_message)

    print(f"Found {len(missing_messages)} missing messages")

    if missing_messages and len(missing_messages) <= 50:
        print("\nMissing messages:")
        for msg in missing_messages:
            convo_id = msg.get('convoID', 'unknown')
            user_id = msg.get('userID', 'unknown')
            timestamp = msg.get('timestamp', 'unknown')
            text_preview = (msg.get('text', '')[:50] + '...') if len(msg.get('text', '')) > 50 else msg.get('text', '')
            print(f"  - {msg.get('firebase_message_id')} (convo: {convo_id}, user: {user_id})")
            print(f"    timestamp: {timestamp}")
            print(f"    text: {text_preview}")
    elif missing_messages:
        print(f"\n(Too many missing messages to list individually)")

    return missing_messages


def sync_missing_conversations(missing_convos, dry_run=False):
    """
    Sync missing conversations to the local database.
    """
    if not missing_convos:
        print("\nNo missing conversations to sync")
        return 0

    if dry_run:
        print(f"\n[DRY RUN] Would sync {len(missing_convos)} conversations")
        return 0

    print(f"\nSyncing {len(missing_convos)} missing conversations...")
    synced_count = 0
    skipped_count = 0

    for fb_convo in missing_convos:
        firebase_convo_id = fb_convo.get('firebase_convo_id')
        user_firebase_id = fb_convo.get('userID')

        # Find the user
        user = User.query.filter_by(firebase_id=user_firebase_id).first()
        if not user:
            print(f"  Warning: User {user_firebase_id} not found for conversation {firebase_convo_id}, skipping")
            skipped_count += 1
            continue

        # Create the conversation (use current time if timestamp missing)
        convo = Conversation(
            firebase_convo_id=firebase_convo_id,
            user_id=user.id,
            prompt=fb_convo.get('prompt', ''),
            timestamp=fb_convo.get('timestamp') or datetime.utcnow()
        )
        db.session.add(convo)
        synced_count += 1
        print(f"  Synced conversation: {firebase_convo_id}")

    db.session.commit()
    print(f"\nSynced {synced_count} conversations ({skipped_count} skipped due to missing users)")
    return synced_count


def is_risky(risk_value):
    """Check if message is risky based on Firebase riskScore field."""
    if risk_value is None:
        return False
    if isinstance(risk_value, str):
        return risk_value.strip().lower() == "risky"
    return False


def sync_missing_messages(missing_messages, dry_run=False):
    """
    Sync missing messages to the local database.
    """
    if not missing_messages:
        print("\nNo missing messages to sync")
        return 0, 0

    if dry_run:
        print(f"\n[DRY RUN] Would sync {len(missing_messages)} messages")
        return 0, 0

    print(f"\nSyncing {len(missing_messages)} missing messages...")
    synced_count = 0
    skipped_count = 0
    alerts_sent = 0

    for fb_message in missing_messages:
        firebase_message_id = fb_message.get('firebase_message_id')
        convo_id_str = fb_message.get('convoID')
        user_firebase_id = fb_message.get('userID')

        # Find the conversation
        conversation = Conversation.query.filter_by(firebase_convo_id=convo_id_str).first()
        if not conversation:
            print(f"  Warning: Conversation {convo_id_str} not found for message {firebase_message_id}, skipping")
            skipped_count += 1
            continue

        # Find the user
        user = User.query.filter_by(firebase_id=user_firebase_id).first()
        if not user:
            print(f"  Warning: User {user_firebase_id} not found for message {firebase_message_id}, skipping")
            skipped_count += 1
            continue

        # Check if message is risky
        risky = is_risky(fb_message.get('riskScore'))

        # Create the message
        message = Message(
            firebase_message_id=firebase_message_id,
            conversation_id=conversation.id,
            user_id=user.id,
            text=fb_message.get('text', ''),
            timestamp=fb_message.get('timestamp'),
            is_risky=risky
        )
        db.session.add(message)
        synced_count += 1

        # Send alert if message is risky
        if risky:
            try:
                alert_sent = twilio_service.send_risk_alert(
                    user_firebase_id,
                    message.text
                )
                if alert_sent:
                    message.alert_sent = True
                    alerts_sent += 1
                    print(f"  Risk alert sent for message {firebase_message_id}")
            except Exception as e:
                print(f"  Error sending risk alert: {e}")

        if synced_count % 100 == 0:
            print(f"  Progress: {synced_count} messages synced...")

    db.session.commit()
    print(f"\nSynced {synced_count} messages ({skipped_count} skipped)")
    if alerts_sent > 0:
        print(f"Sent {alerts_sent} risk alerts")
    return synced_count, alerts_sent


def main():
    dry_run = '--dry-run' in sys.argv

    if dry_run:
        print("\n" + "*" * 60)
        print("* DRY RUN MODE - No changes will be made")
        print("*" * 60)

    print("\n" + "=" * 60)
    print("SYNC MISSING DATA SCRIPT")
    print("=" * 60)
    print(f"Started at: {datetime.utcnow()}")

    with app.app_context():
        # Initialize Firebase
        print("\nInitializing Firebase...")
        firebase_service.initialize()

        # Find missing data
        missing_convos = find_missing_conversations(dry_run)
        missing_messages = find_missing_messages(dry_run)

        # Summary before sync
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Missing conversations: {len(missing_convos)}")
        print(f"Missing messages: {len(missing_messages)}")

        if not missing_convos and not missing_messages:
            print("\nAll data is already in sync!")
            return

        if dry_run:
            print("\n[DRY RUN] Run without --dry-run to perform the sync")
            return

        # Confirm before syncing
        print("\nProceed with sync? (y/n): ", end='')
        response = input().strip().lower()
        if response != 'y':
            print("Sync cancelled")
            return

        # Sync missing data
        # IMPORTANT: Sync conversations first, then messages
        convos_synced = sync_missing_conversations(missing_convos, dry_run)
        messages_synced, alerts = sync_missing_messages(missing_messages, dry_run)

        # Final summary
        print("\n" + "=" * 60)
        print("FINAL RESULTS")
        print("=" * 60)
        print(f"Conversations synced: {convos_synced}")
        print(f"Messages synced: {messages_synced}")
        print(f"Risk alerts sent: {alerts}")
        print(f"Completed at: {datetime.utcnow()}")


if __name__ == '__main__':
    main()
