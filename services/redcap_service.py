import requests
from config import Config


class REDCapService:
    """Service for interacting with REDCap API"""

    def __init__(self):
        self.api_url = Config.REDCAP_API_URL
        self.api_token = Config.REDCAP_API_TOKEN
        self.filter_logic = Config.REDCAP_FILTER_LOGIC
        self.form_name = Config.REDCAP_FORM_NAME
        self.firebase_id_field = Config.REDCAP_FIREBASE_ID_FIELD
        self.ra_field = Config.REDCAP_RA_FIELD
        self.event_name = Config.REDCAP_EVENT_NAME

    def get_all_participants(self):
        """
        Fetch study participants from REDCap that match the filter logic.
        Returns list of dictionaries with participant data including firebase_id and RA.
        """
        if not self.api_url or not self.api_token:
            print("Warning: REDCap credentials not configured")
            return []

        data = {
            'token': self.api_token,
            'content': 'record',
            'format': 'json',
            'type': 'flat',
            'forms': self.form_name,
            'event': self.event_name,
            'fields': f'record_id,{self.firebase_id_field},{self.ra_field}',
            'filterLogic': self.filter_logic,
            'returnFormat': 'json'
        }
        print(data)

        try:
            response = requests.post(self.api_url, data=data, timeout=30)
            response.raise_for_status()

            participants = response.json()
            print(f"Fetched {len(participants)} participants from REDCap (filter: {self.filter_logic})")
            print(participants)
            return participants

        except requests.exceptions.RequestException as e:
            print(f"Error fetching REDCap data: {e}")
            raise

    def get_active_participants(self):
        """
        Fetch active study participants from REDCap based on filter logic.
        Returns list of firebase_id values for active participants.
        """
        if not self.api_url or not self.api_token:
            print("Warning: REDCap credentials not configured")
            return []

        data = {
            'token': self.api_token,
            'content': 'record',
            'format': 'json',
            'type': 'flat',
            'forms': self.form_name,
            'event': self.event_name,
            'fields': self.firebase_id_field,
            'filterLogic': self.filter_logic,
            'returnFormat': 'json'
        }

        try:
            response = requests.post(self.api_url, data=data, timeout=30)
            response.raise_for_status()

            participants = response.json()
            print(participants)

            # Extract firebase_id values using the configurable field name
            firebase_ids = []
            for participant in participants:
                if self.firebase_id_field in participant and participant[self.firebase_id_field]:
                    firebase_ids.append(participant[self.firebase_id_field])

            print(f"Fetched {len(firebase_ids)} active participants from REDCap")
            return firebase_ids

        except requests.exceptions.RequestException as e:
            print(f"Error fetching REDCap data: {e}")
            raise

    def get_participant_details(self, firebase_id):
        """
        Fetch detailed information for a specific participant by firebase_id.
        """
        if not self.api_url or not self.api_token:
            print("Warning: REDCap credentials not configured")
            return None

        data = {
            'token': self.api_token,
            'content': 'record',
            'format': 'json',
            'type': 'flat',
            'filterLogic': f'[firebase_id] = "{firebase_id}"',
            'returnFormat': 'json'
        }

        try:
            response = requests.post(self.api_url, data=data, timeout=30)
            response.raise_for_status()

            participants = response.json()

            if participants and len(participants) > 0:
                return participants[0]
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error fetching participant details: {e}")
            raise

    def validate_participant(self, firebase_id):
        """
        Check if a participant with given firebase_id is active in REDCap.
        """
        active_participants = self.get_active_participants()
        return firebase_id in active_participants


# Singleton instance
redcap_service = REDCapService()
