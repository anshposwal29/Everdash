"""
Theradash Data Synchronization Service

This module orchestrates the synchronization of data from multiple sources:
- Firebase Firestore (messages, conversations, user preferences)
- REDCap (study participant information)

Key Features:
- Incremental sync: Only fetches new messages since last sync to minimize costs
- Three user selection modes: REDCap-only, UID-only, or combined
- Automatic SMS alerts via Twilio for high-risk messages
- Comprehensive sync logging and error handling

User Selection Modes:
    redcap: Monitor only users found in REDCap with matching Firebase IDs
    uids: Monitor only specific Firebase UIDs (defined in config)
    both: Monitor all REDCap participants AND specific Firebase UIDs
    all: Monitor all Firebase users (no filtering)

The sync process:
1. Get list of users to monitor (based on mode)
2. Fetch user data from Firebase (preferences, current conversation)
3. Fetch conversations for each user
4. Fetch messages incrementally (only new ones since last sync)
5. Check risk scores and send alerts if needed
6. Log sync results

Author: Theradash Team
Last Updated: October 2025
"""

from models import db, User, Conversation, Message, SyncLog, REDCapProject, UserCustomField
from services.firebase_service import firebase_service
from services.redcap_service import redcap_service, REDCapService
from services.twilio_service import twilio_service
from datetime import datetime
from config import Config
import pytz


class SyncService:
    """
    Service for syncing data from Firebase and REDCap to local SQLite database.

    This service handles the complete synchronization workflow including:
    - User selection based on configured mode
    - Incremental message syncing to reduce Firebase costs
    - Risk score monitoring and SMS alerting
    - Sync logging and error tracking

    Attributes:
        timezone (pytz.timezone): Configured timezone for timestamp conversion
    """

    def __init__(self):
        self.timezone = pytz.timezone(Config.TIMEZONE)

    def _fetch_and_update_auth_identifier(self, user):
        """
        Fetch authentication data from Firebase Auth and update user's identifier.
        The identifier is typically the email address from Firebase Authentication.
        If Firebase Auth doesn't provide an identifier, preserve the existing one (e.g., username from REDCap).
        """
        try:
            auth_data = firebase_service.get_auth_user(user.firebase_id)
            if auth_data:
                # Use email as the identifier, fall back to phone number or display name
                auth_identifier = auth_data.get('email') or auth_data.get('phone_number') or auth_data.get('display_name')
                if auth_identifier:
                    user.identifier = auth_identifier
                    print(f"Updated identifier for {user.firebase_id}: {user.identifier}")
                # If no auth identifier, keep existing identifier (e.g., username from REDCap)
            # If no auth_data, keep existing identifier (don't overwrite with '-')
        except Exception as e:
            print(f"Error fetching auth identifier for {user.firebase_id}: {e}")
            # Keep existing identifier on error (don't overwrite with '-')

    def _is_risky(self, risk_value):
        """
        Check if message is risky based on Firebase riskScore field.
        Returns True if value is "Risky", False otherwise.
        """
        if risk_value is None:
            return False
        if isinstance(risk_value, str):
            return risk_value.strip().lower() == "risky"
        return False

    def get_last_sync_timestamp(self):
        """Get the timestamp of the last successful sync"""
        last_sync = SyncLog.query.order_by(SyncLog.last_sync_timestamp.desc()).first()
        if last_sync:
            return last_sync.last_sync_timestamp
        return None

    def _parse_date(self, date_str):
        """Parse date string from REDCap into a date object"""
        if not date_str or not date_str.strip():
            return None
        try:
            # Try common REDCap date formats
            for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y', '%m-%d-%Y']:
                try:
                    return datetime.strptime(date_str.strip(), fmt).date()
                except ValueError:
                    continue
        except Exception as e:
            print(f"Error parsing date '{date_str}': {e}")
        return None

    def _parse_boolean(self, value):
        """Parse REDCap boolean-like values (1, '1', 'yes', 'true') to Python bool"""
        if value is None or value == '':
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value == 1
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'yes', 'true')
        return False

    def _sync_project_to_db(self, project_config):
        """Ensure project exists in database"""
        project = REDCapProject.query.filter_by(project_id=project_config.id).first()
        if not project:
            project = REDCapProject(
                project_id=project_config.id,
                name=project_config.name,
                api_url=project_config.api_url,
                is_active=True
            )
            db.session.add(project)
            db.session.commit()
            print(f"Created REDCap project record: {project_config.id}")
        return project

    def _sync_user_custom_fields(self, user, participant_data, project_config):
        """Sync custom REDCap fields for a user"""
        for custom_field_config in project_config.custom_display_fields:
            field_name = custom_field_config.get('field')
            field_label = custom_field_config.get('label', field_name)
            field_value = participant_data.get(field_name, '')

            if not field_name:
                continue

            # Find or create custom field record
            custom_field = UserCustomField.query.filter_by(
                user_id=user.id,
                field_name=field_name
            ).first()

            if not custom_field:
                custom_field = UserCustomField(
                    user_id=user.id,
                    field_name=field_name,
                    field_label=field_label,
                    field_value=str(field_value) if field_value else ''
                )
                db.session.add(custom_field)
            else:
                custom_field.field_value = str(field_value) if field_value else ''
                custom_field.field_label = field_label
                custom_field.last_updated = datetime.utcnow()

    def sync_uid_users(self):
        """
        Sync users specified by Firebase UIDs directly (not from REDCap).
        This is useful for external testers who are not in REDCap.
        """
        synced_count = 0

        for firebase_id in Config.FIREBASE_UIDS:
            if not firebase_id:
                continue

            print(f"Processing UID-specified user: firebase_id={firebase_id}")

            try:
                # Check if this Firebase user exists
                firebase_user = firebase_service.get_user_by_id(firebase_id)

                if not firebase_user:
                    print(f"Warning: Firebase ID '{firebase_id}' not found in Firebase users collection")
                    # Still create a placeholder in case they're added later
                    user = User.query.filter_by(firebase_id=firebase_id).first()
                    if not user:
                        user = User(
                            firebase_id=firebase_id,
                            redcap_id=None,
                            research_assistant='External Tester',
                            is_active=True
                        )
                        db.session.add(user)
                        print(f"Created placeholder for UID user {firebase_id}")
                    else:
                        user.is_active = True
                        user.research_assistant = 'External Tester'
                    synced_count += 1
                    continue

                # Firebase user exists - create or update local user
                user = User.query.filter_by(firebase_id=firebase_id).first()

                if not user:
                    user = User(
                        firebase_id=firebase_id,
                        redcap_id=None,
                        research_assistant='External Tester'
                    )
                    db.session.add(user)
                    print(f"Created new UID user with Firebase ID {firebase_id}")
                else:
                    # Don't overwrite REDCap data if it exists
                    if not user.redcap_id:
                        user.research_assistant = 'External Tester'
                    print(f"Updated existing UID user with Firebase ID {firebase_id}")

                user.is_active = True
                user.last_synced = datetime.utcnow()

                # Fetch and update identifier from Firebase Authentication
                self._fetch_and_update_auth_identifier(user)

                synced_count += 1

            except Exception as e:
                print(f"Error syncing UID user {firebase_id}: {e}")
                # Create placeholder user on error
                user = User.query.filter_by(firebase_id=firebase_id).first()
                if not user:
                    user = User(
                        firebase_id=firebase_id,
                        redcap_id=None,
                        research_assistant='External Tester',
                        is_active=True
                    )
                    db.session.add(user)
                synced_count += 1

        db.session.commit()
        print(f"Synced {synced_count} UID-specified users")
        return synced_count

    def sync_all_firebase_users(self):
        """
        Sync all users from Firebase without any filtering.
        This pulls every user from the Firebase users collection.
        """
        synced_count = 0

        try:
            firebase_users = firebase_service.get_users()
            print(f"Found {len(firebase_users)} users in Firebase")

            for fb_user in firebase_users:
                firebase_id = fb_user.get('firebase_id')

                if not firebase_id:
                    print(f"Warning: Firebase user without ID found, skipping")
                    continue

                # Check if user exists in local database
                user = User.query.filter_by(firebase_id=firebase_id).first()

                if not user:
                    # Create new user
                    user = User(
                        firebase_id=firebase_id,
                        redcap_id=None,
                        research_assistant='Firebase User',
                        is_active=True
                    )
                    db.session.add(user)
                    print(f"Created new user with Firebase ID {firebase_id}")
                else:
                    # Update existing user
                    # Don't overwrite REDCap data if it exists
                    if not user.redcap_id:
                        user.research_assistant = 'Firebase User'
                    user.is_active = True
                    print(f"Updated existing user with Firebase ID {firebase_id}")

                # Update Firebase-specific fields
                user.current_convo_id = fb_user.get('convoID', '')
                user.is_animated = fb_user.get('isAnimate', False)
                user.is_dark_mode = fb_user.get('isDark', False)
                user.last_synced = datetime.utcnow()

                # Fetch and update identifier from Firebase Authentication
                self._fetch_and_update_auth_identifier(user)

                synced_count += 1

            db.session.commit()
            print(f"Synced {synced_count} Firebase users")
            return synced_count

        except Exception as e:
            print(f"Error syncing all Firebase users: {e}")
            db.session.rollback()
            return 0

    def sync_redcap_participants(self):
        """
        Sync participants from ALL REDCap projects to local database.
        Iterates through each configured project and syncs participants with
        project_id, study dates, and custom fields.

        The firebase_id from REDCap should match the Firebase document ID in the users collection.
        """
        total_synced = 0

        # Get all configured projects
        projects = Config.get_all_projects()
        print(f"Syncing participants from {len(projects)} REDCap project(s)")

        for project_config in projects:
            print(f"\n--- Syncing project: {project_config.name} ({project_config.id}) ---")

            # Ensure project exists in database
            self._sync_project_to_db(project_config)

            # Create service for this specific project
            project_service = REDCapService(project_config)

            try:
                redcap_participants = project_service.get_all_participants()
            except Exception as e:
                print(f"Error fetching participants from {project_config.name}: {e}")
                continue

            firebase_id_field = project_config.firebase_id_field
            ra_field = project_config.ra_field
            synced_count = 0

            for participant in redcap_participants:
                record_id = participant.get('record_id') or participant.get('id')
                firebase_id = participant.get(firebase_id_field, '').strip()
                research_assistant = participant.get(ra_field, '').strip()
                username = participant.get('username', '').strip()  # Get username from REDCap

                # Parse study dates
                study_start = self._parse_date(
                    participant.get(project_config.study_start_date_field, '')
                ) if project_config.study_start_date_field else None

                study_end = self._parse_date(
                    participant.get(project_config.study_end_date_field, '')
                ) if project_config.study_end_date_field else None

                # Parse dropped status fields
                dropped = self._parse_boolean(participant.get('dropped', ''))
                dropped_surveys = self._parse_boolean(participant.get('dropped_surveys', ''))

                print(f"Processing participant: record_id={record_id}, firebase_id={firebase_id}, RA={research_assistant}")

                if not firebase_id or firebase_id == '':
                    # No Firebase ID - create placeholder user with REDCap ID only
                    if not record_id:
                        print(f"Skipping participant with no record_id and no firebase_id")
                        continue

                    # Use project-specific placeholder ID
                    placeholder_firebase_id = f'redcap_{project_config.id}_{record_id}'
                    user = User.query.filter_by(firebase_id=placeholder_firebase_id).first()
                    if not user:
                        user = User(
                            firebase_id=placeholder_firebase_id,
                            redcap_firebase_id='',  # No firebase_id in REDCap
                            redcap_id=str(record_id),
                            identifier=username or '-',  # Use username from REDCap
                            research_assistant=research_assistant,
                            project_id=project_config.id,
                            study_start_date=study_start,
                            study_end_date=study_end,
                            dropped=dropped,
                            dropped_surveys=dropped_surveys,
                            is_active=True
                        )
                        db.session.add(user)
                        print(f"Created placeholder user for REDCap ID {record_id}")
                    else:
                        user.redcap_firebase_id = ''
                        user.identifier = username or user.identifier or '-'  # Use username from REDCap
                        user.research_assistant = research_assistant
                        user.project_id = project_config.id
                        user.study_start_date = study_start
                        user.study_end_date = study_end
                        user.dropped = dropped
                        user.dropped_surveys = dropped_surveys
                        user.is_active = True
                        print(f"Updated placeholder user for REDCap ID {record_id}")

                    # Sync custom fields
                    db.session.flush()  # Ensure user.id is set
                    self._sync_user_custom_fields(user, participant, project_config)
                    synced_count += 1
                else:
                    # Has Firebase ID - verify it exists in Firebase and create/update user
                    try:
                        firebase_user = firebase_service.get_user_by_id(firebase_id)

                        if not firebase_user:
                            print(f"Warning: Firebase ID '{firebase_id}' from REDCap record {record_id} not found in Firebase")
                            placeholder_firebase_id = f'redcap_{project_config.id}_{record_id}'
                            user = User.query.filter_by(firebase_id=placeholder_firebase_id).first()
                            if not user:
                                user = User(
                                    firebase_id=placeholder_firebase_id,
                                    redcap_firebase_id=firebase_id,  # Store actual firebase_id from REDCap
                                    redcap_id=str(record_id),
                                    identifier=username or '-',  # Use username from REDCap
                                    research_assistant=research_assistant,
                                    project_id=project_config.id,
                                    study_start_date=study_start,
                                    study_end_date=study_end,
                                    dropped=dropped,
                                    dropped_surveys=dropped_surveys,
                                    is_active=True
                                )
                                db.session.add(user)
                            else:
                                user.redcap_firebase_id = firebase_id  # Store actual firebase_id from REDCap
                                user.identifier = username or user.identifier or '-'  # Use username from REDCap
                                user.research_assistant = research_assistant
                                user.project_id = project_config.id
                                user.study_start_date = study_start
                                user.study_end_date = study_end
                                user.dropped = dropped
                                user.dropped_surveys = dropped_surveys
                                user.is_active = True

                            db.session.flush()
                            self._sync_user_custom_fields(user, participant, project_config)
                            synced_count += 1
                            continue

                        # Firebase user exists - create or update local user
                        user = User.query.filter_by(firebase_id=firebase_id).first()

                        if not user:
                            # Check for placeholder user
                            placeholder_firebase_id = f'redcap_{project_config.id}_{record_id}'
                            placeholder_user = User.query.filter_by(firebase_id=placeholder_firebase_id).first()
                            if placeholder_user:
                                user = placeholder_user
                                user.firebase_id = firebase_id
                                user.redcap_firebase_id = firebase_id  # Store actual firebase_id from REDCap
                                print(f"Updated placeholder with actual Firebase ID {firebase_id}")
                            else:
                                user = User(
                                    firebase_id=firebase_id,
                                    redcap_firebase_id=firebase_id,  # Store actual firebase_id from REDCap
                                    redcap_id=str(record_id) if record_id else None,
                                    identifier=username or '-',  # Use username from REDCap as default
                                    research_assistant=research_assistant,
                                    project_id=project_config.id,
                                    study_start_date=study_start,
                                    study_end_date=study_end,
                                    dropped=dropped,
                                    dropped_surveys=dropped_surveys
                                )
                                db.session.add(user)
                                print(f"Created new user with Firebase ID {firebase_id}")
                        else:
                            user.redcap_firebase_id = firebase_id  # Store actual firebase_id from REDCap
                            user.redcap_id = str(record_id) if record_id else user.redcap_id
                            # Use username from REDCap if no identifier exists yet
                            if not user.identifier or user.identifier == '-':
                                user.identifier = username or '-'
                            user.research_assistant = research_assistant
                            user.project_id = project_config.id
                            user.study_start_date = study_start
                            user.study_end_date = study_end
                            user.dropped = dropped
                            user.dropped_surveys = dropped_surveys
                            print(f"Updated existing user with Firebase ID {firebase_id}")

                        user.is_active = True
                        user.last_synced = datetime.utcnow()

                        # Fetch identifier from Firebase Auth (will override username if user has Firebase Auth)
                        if not user.firebase_id.startswith('redcap_'):
                            self._fetch_and_update_auth_identifier(user)

                        # Sync custom fields
                        db.session.flush()
                        self._sync_user_custom_fields(user, participant, project_config)
                        synced_count += 1

                    except Exception as e:
                        print(f"Error checking Firebase user {firebase_id}: {e}")
                        placeholder_firebase_id = f'redcap_{project_config.id}_{record_id}'
                        user = User.query.filter_by(firebase_id=placeholder_firebase_id).first()
                        if not user:
                            user = User(
                                firebase_id=placeholder_firebase_id,
                                redcap_firebase_id=firebase_id,  # Store actual firebase_id from REDCap
                                redcap_id=str(record_id),
                                identifier=username or '-',  # Use username from REDCap
                                research_assistant=research_assistant,
                                project_id=project_config.id,
                                study_start_date=study_start,
                                study_end_date=study_end,
                                dropped=dropped,
                                dropped_surveys=dropped_surveys,
                                is_active=True
                            )
                            db.session.add(user)
                        else:
                            user.redcap_firebase_id = firebase_id
                            user.identifier = username or user.identifier or '-'
                            user.dropped = dropped
                            user.dropped_surveys = dropped_surveys
                        db.session.flush()
                        self._sync_user_custom_fields(user, participant, project_config)
                        synced_count += 1

            db.session.commit()
            print(f"Synced {synced_count} participants from project {project_config.name}")
            total_synced += synced_count

        print(f"\nTotal synced across all projects: {total_synced}")
        return total_synced

    def sync_users(self, active_firebase_ids=None):
        """
        Sync users from Firebase to local database.
        If active_firebase_ids is provided, only sync those users.
        """
        firebase_users = firebase_service.get_users()
        synced_count = 0

        for fb_user in firebase_users:
            firebase_id = fb_user.get('firebase_id')

            # Filter by active participants if list is provided
            if active_firebase_ids and firebase_id not in active_firebase_ids:
                continue

            # Check if user exists
            user = User.query.filter_by(firebase_id=firebase_id).first()

            if not user:
                user = User(firebase_id=firebase_id)
                db.session.add(user)

            # Update user fields
            user.current_convo_id = fb_user.get('convoID', '')
            user.is_animated = fb_user.get('isAnimate', False)
            user.is_dark_mode = fb_user.get('isDark', False)
            user.is_active = active_firebase_ids is None or firebase_id in active_firebase_ids
            user.last_synced = datetime.utcnow()

            # Fetch and update identifier from Firebase Authentication
            self._fetch_and_update_auth_identifier(user)

            synced_count += 1

        db.session.commit()
        print(f"Synced {synced_count} users")
        return synced_count

    def sync_conversations(self, since_timestamp=None):
        """Sync conversations from Firebase"""
        conversations = firebase_service.get_conversations_since(since_timestamp)
        synced_count = 0

        for fb_convo in conversations:
            firebase_convo_id = fb_convo.get('firebase_convo_id')
            user_firebase_id = fb_convo.get('userID')

            # Check if conversation already exists
            convo = Conversation.query.filter_by(firebase_convo_id=firebase_convo_id).first()

            if not convo:
                # Find the user
                user = User.query.filter_by(firebase_id=user_firebase_id).first()
                if not user:
                    print(f"Warning: User {user_firebase_id} not found for conversation {firebase_convo_id}")
                    continue

                convo = Conversation(
                    firebase_convo_id=firebase_convo_id,
                    user_id=user.id
                )
                db.session.add(convo)

            # Update conversation fields
            convo.prompt = fb_convo.get('prompt', '')
            convo.timestamp = fb_convo.get('timestamp')

            synced_count += 1

        db.session.commit()
        print(f"Synced {synced_count} conversations")
        return synced_count

    def sync_messages(self, since_timestamp=None, uid_list=None):
        """
        Sync messages from Firebase. This is the key method that only pulls new messages.
        Also handles risk score monitoring and alerts.

        Args:
            since_timestamp: Only fetch messages after this timestamp (unless uid_list is provided)
            uid_list: If provided, fetch ALL messages for these UIDs regardless of timestamp
        """
        synced_count = 0
        alerts_sent = 0
        all_messages = []

        if uid_list:
            # For UID mode: fetch ALL messages for each UID user (ignore timestamp)
            print(f"Fetching ALL messages for {len(uid_list)} UID users...")
            for firebase_id in uid_list:
                try:
                    user_messages = firebase_service.get_messages_for_user(firebase_id)
                    all_messages.extend(user_messages)
                    print(f"Retrieved {len(user_messages)} messages for UID {firebase_id}")
                except Exception as e:
                    print(f"Error fetching messages for UID {firebase_id}: {e}")
        else:
            # Regular mode: fetch only new messages since last sync
            all_messages = firebase_service.get_messages_since(since_timestamp)

        for fb_message in all_messages:
            firebase_message_id = fb_message.get('firebase_message_id')
            convo_id_str = fb_message.get('convoID')
            user_firebase_id = fb_message.get('userID')

            # Check if message already exists
            message = Message.query.filter_by(firebase_message_id=firebase_message_id).first()

            if message:
                # Message already synced, skip
                continue

            # Find the conversation
            conversation = Conversation.query.filter_by(firebase_convo_id=convo_id_str).first()
            if not conversation:
                print(f"Warning: Conversation {convo_id_str} not found for message {firebase_message_id}")
                continue

            # Find the user
            user = User.query.filter_by(firebase_id=user_firebase_id).first()
            if not user:
                print(f"Warning: User {user_firebase_id} not found for message {firebase_message_id}")
                continue

            # Check if message is risky (binary "Risky" / "Not Risky")
            is_risky = self._is_risky(fb_message.get('riskScore'))

            # Create new message
            message = Message(
                firebase_message_id=firebase_message_id,
                conversation_id=conversation.id,
                user_id=user.id,
                text=fb_message.get('text', ''),
                timestamp=fb_message.get('timestamp'),
                is_risky=is_risky
            )

            db.session.add(message)
            synced_count += 1

            # Send alert if message is risky
            if is_risky:
                try:
                    alert_sent = twilio_service.send_risk_alert(
                        user_firebase_id,
                        message.text
                    )

                    if alert_sent:
                        message.alert_sent = True
                        alerts_sent += 1
                        print(f"Risk alert sent for message {firebase_message_id}")
                except Exception as e:
                    print(f"Error sending risk alert: {e}")

        db.session.commit()
        print(f"Synced {synced_count} messages, sent {alerts_sent} alerts")
        return synced_count, alerts_sent

    def full_sync(self):
        """
        Perform a full sync of all data.
        Only fetches new messages since last sync to save costs.
        Respects USER_SELECTION_MODE configuration for determining which users to sync.
        """
        start_time = datetime.utcnow()
        print(f"Starting full sync at {start_time}")
        print(f"User selection mode: {Config.USER_SELECTION_MODE}")

        try:
            # Initialize Firebase if not already done
            firebase_service.initialize()

            # Reset all users to inactive before syncing
            # The sync process will reactivate users that match the current selection mode
            # This ensures users from a previous mode (e.g., switching from 'uids' to 'redcap')
            # are properly deactivated
            deactivated_count = User.query.filter_by(is_active=True).update({'is_active': False})
            db.session.commit()
            print(f"Reset {deactivated_count} users to inactive (will reactivate matching users)")

            # Sync users based on selection mode
            users_synced = 0

            if Config.USER_SELECTION_MODE == 'redcap':
                # Only sync REDCap participants
                users_synced = self.sync_redcap_participants()

            elif Config.USER_SELECTION_MODE == 'uids':
                # Only sync users from Firebase UID list
                users_synced = self.sync_uid_users()

            elif Config.USER_SELECTION_MODE == 'both':
                # Sync both REDCap participants and UID list
                redcap_count = self.sync_redcap_participants()
                uid_count = self.sync_uid_users()
                users_synced = redcap_count + uid_count
                print(f"Combined sync: {redcap_count} REDCap users + {uid_count} UID users")

            elif Config.USER_SELECTION_MODE == 'all':
                # Sync all Firebase users without filtering
                users_synced = self.sync_all_firebase_users()

            else:
                print(f"Warning: Unknown USER_SELECTION_MODE '{Config.USER_SELECTION_MODE}', defaulting to REDCap")
                users_synced = self.sync_redcap_participants()

            # Then sync Firebase user data for those who have Firebase IDs
            # (Skip this for 'all' mode since sync_all_firebase_users already does this)
            if Config.USER_SELECTION_MODE != 'all':
                firebase_users = firebase_service.get_users()
                for fb_user in firebase_users:
                    firebase_id = fb_user.get('firebase_id')
                    user = User.query.filter_by(firebase_id=firebase_id).first()
                    if user:
                        user.current_convo_id = fb_user.get('convoID', '')
                        user.is_animated = fb_user.get('isAnimate', False)
                        user.is_dark_mode = fb_user.get('isDark', False)
                        # Fetch and update identifier from Firebase Authentication
                        if not user.firebase_id.startswith('redcap_'):
                            self._fetch_and_update_auth_identifier(user)
                db.session.commit()

            # Get last sync timestamp to only fetch new data
            last_sync_timestamp = self.get_last_sync_timestamp()

            # Sync conversations (only new ones)
            conversations_synced = self.sync_conversations(last_sync_timestamp)

            # Sync messages
            # For UID mode, fetch ALL messages for UID users (ignore timestamp)
            # For redcap and all modes, only fetch new messages since last sync
            uid_list = None
            if Config.USER_SELECTION_MODE in ['uids', 'both']:
                # Get list of Firebase IDs to fetch all messages for
                uid_list = [uid for uid in Config.FIREBASE_UIDS if uid]
                print(f"UID mode active: will fetch ALL messages for {len(uid_list)} UIDs")

            messages_synced, alerts_sent = self.sync_messages(
                since_timestamp=last_sync_timestamp if Config.USER_SELECTION_MODE in ['redcap', 'all'] else None,
                uid_list=uid_list
            )

            # Record sync log
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            sync_log = SyncLog(
                last_sync_timestamp=end_time,
                messages_synced=messages_synced,
                conversations_synced=conversations_synced,
                users_synced=users_synced,
                sync_duration_seconds=duration
            )
            db.session.add(sync_log)
            db.session.commit()

            print(f"Sync completed in {duration:.2f} seconds")
            print(f"Users: {users_synced}, Conversations: {conversations_synced}, Messages: {messages_synced}, Alerts: {alerts_sent}")

            return {
                'success': True,
                'users_synced': users_synced,
                'conversations_synced': conversations_synced,
                'messages_synced': messages_synced,
                'alerts_sent': alerts_sent,
                'duration': duration
            }

        except Exception as e:
            print(f"Error during sync: {e}")
            db.session.rollback()
            return {
                'success': False,
                'error': str(e)
            }


# Singleton instance
sync_service = SyncService()
