import firebase_admin
from firebase_admin import credentials, firestore, auth
from datetime import datetime
import pytz
from config import Config


class FirebaseService:
    """Service for interacting with Firebase Firestore"""

    def __init__(self):
        self.db = None
        self.initialized = False

    def initialize(self):
        """Initialize Firebase Admin SDK"""
        if self.initialized:
            return

        try:
            if Config.FIREBASE_CREDENTIALS_PATH:
                cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred)
            else:
                # Use default credentials (e.g., in GCP environment)
                firebase_admin.initialize_app()

            self.db = firestore.client()
            self.initialized = True
            print("Firebase initialized successfully")
        except Exception as e:
            print(f"Error initializing Firebase: {e}")
            raise

    def get_users(self):
        """Fetch all users from Firebase"""
        if not self.initialized:
            self.initialize()

        users_ref = self.db.collection('users')
        users = []

        try:
            for doc in users_ref.stream():
                user_data = doc.to_dict()
                user_data['firebase_id'] = doc.id
                users.append(user_data)
        except Exception as e:
            print(f"Error fetching users: {e}")
            raise

        return users

    def get_conversations_since(self, since_timestamp=None):
        """Fetch conversations from Firebase, optionally since a specific timestamp"""
        if not self.initialized:
            self.initialize()

        convos_ref = self.db.collection('convos')

        if since_timestamp:
            convos_ref = convos_ref.where('timestamp', '>', since_timestamp)

        conversations = []

        try:
            for doc in convos_ref.stream():
                convo_data = doc.to_dict()
                convo_data['firebase_convo_id'] = doc.id
                conversations.append(convo_data)
        except Exception as e:
            print(f"Error fetching conversations: {e}")
            raise

        return conversations

    def get_messages_since(self, since_timestamp=None):
        """
        Fetch messages from Firebase, optionally since a specific timestamp.
        This is the critical method to only pull new messages.
        """
        if not self.initialized:
            self.initialize()

        messages_ref = self.db.collection('messages')

        if since_timestamp:
            # Only fetch messages after the last sync timestamp
            messages_ref = messages_ref.where('timestamp', '>', since_timestamp)

        messages = []

        try:
            for doc in messages_ref.stream():
                message_data = doc.to_dict()
                message_data['firebase_message_id'] = doc.id
                messages.append(message_data)
        except Exception as e:
            print(f"Error fetching messages: {e}")
            raise

        return messages

    def get_user_by_id(self, firebase_id):
        """Fetch a specific user by Firebase ID"""
        if not self.initialized:
            self.initialize()

        try:
            user_ref = self.db.collection('users').document(firebase_id)
            user_doc = user_ref.get()

            if user_doc.exists:
                user_data = user_doc.to_dict()
                user_data['firebase_id'] = user_doc.id
                return user_data
            return None
        except Exception as e:
            print(f"Error fetching user {firebase_id}: {e}")
            raise

    def get_conversation_by_id(self, convo_id):
        """Fetch a specific conversation by ID"""
        if not self.initialized:
            self.initialize()

        try:
            convo_ref = self.db.collection('convos').document(convo_id)
            convo_doc = convo_ref.get()

            if convo_doc.exists:
                convo_data = convo_doc.to_dict()
                convo_data['firebase_convo_id'] = convo_doc.id
                return convo_data
            return None
        except Exception as e:
            print(f"Error fetching conversation {convo_id}: {e}")
            raise

    def get_messages_for_conversation(self, convo_id):
        """Fetch all messages for a specific conversation"""
        if not self.initialized:
            self.initialize()

        messages_ref = self.db.collection('messages').where('convoID', '==', convo_id)
        messages = []

        try:
            for doc in messages_ref.stream():
                message_data = doc.to_dict()
                message_data['firebase_message_id'] = doc.id
                messages.append(message_data)
        except Exception as e:
            print(f"Error fetching messages for conversation {convo_id}: {e}")
            raise

        return messages

    def get_messages_for_user(self, user_firebase_id, since_timestamp=None):
        """Fetch all messages for a specific user, optionally since a specific timestamp"""
        if not self.initialized:
            self.initialize()

        messages_ref = self.db.collection('messages').where('userID', '==', user_firebase_id)

        if since_timestamp:
            messages_ref = messages_ref.where('timestamp', '>', since_timestamp)

        messages = []

        try:
            for doc in messages_ref.stream():
                message_data = doc.to_dict()
                message_data['firebase_message_id'] = doc.id
                messages.append(message_data)
        except Exception as e:
            print(f"Error fetching messages for user {user_firebase_id}: {e}")
            raise

        return messages

    def get_auth_user(self, firebase_id):
        """Fetch user authentication data from Firebase Authentication"""
        if not self.initialized:
            self.initialize()

        try:
            user_record = auth.get_user(firebase_id)
            return {
                'uid': user_record.uid,
                'email': user_record.email,
                'phone_number': user_record.phone_number,
                'display_name': user_record.display_name,
                'disabled': user_record.disabled,
                'email_verified': user_record.email_verified
            }
        except auth.UserNotFoundError:
            print(f"Authentication user {firebase_id} not found")
            return None
        except Exception as e:
            print(f"Error fetching auth user {firebase_id}: {e}")
            return None

    def has_user_ever_logged_in(self, firebase_id):
        """
        Check if a user has ever logged in by checking their last_sign_in_timestamp.
        Returns True if user has logged in at least once, False if never logged in,
        or None if user not found or error occurred.
        """
        if not self.initialized:
            self.initialize()

        try:
            user_record = auth.get_user(firebase_id)
            # user_metadata.last_sign_in_timestamp is None if user has never signed in
            last_sign_in = user_record.user_metadata.last_sign_in_timestamp
            return last_sign_in is not None
        except auth.UserNotFoundError:
            print(f"Authentication user {firebase_id} not found")
            return None
        except Exception as e:
            print(f"Error checking login status for {firebase_id}: {e}")
            return None


# Singleton instance
firebase_service = FirebaseService()
