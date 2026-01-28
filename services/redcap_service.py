import requests
from config import Config, REDCapProjectConfig


class REDCapService:
    """Service for interacting with REDCap API - supports multiple projects"""

    def __init__(self, project_config: REDCapProjectConfig = None):
        """
        Initialize service for a specific project.
        If no project_config provided, uses first configured project.
        """
        if project_config:
            self.project_config = project_config
        else:
            # Fall back to first configured project for backward compatibility
            projects = Config.get_all_projects()
            self.project_config = projects[0] if projects else None

        if self.project_config:
            self.api_url = self.project_config.api_url
            self.api_token = self.project_config.api_token
            self.filter_logic = self.project_config.filter_logic
            self.form_name = self.project_config.form_name
            self.firebase_id_field = self.project_config.firebase_id_field
            self.ra_field = self.project_config.ra_field
            self.event_name = self.project_config.event_name
        else:
            self.api_url = None
            self.api_token = None
            self.filter_logic = ''
            self.form_name = ''
            self.firebase_id_field = 'firebase_id'
            self.ra_field = 'ra'
            self.event_name = ''

    def get_all_participants(self):
        """
        Fetch study participants from REDCap that match the filter logic.
        Returns list of dictionaries with participant data including firebase_id, RA,
        study dates, and custom display fields.
        """
        if not self.api_url or not self.api_token:
            print("Warning: REDCap credentials not configured")
            return []

        # Build list of fields to request
        fields = [self.firebase_id_field, self.ra_field, 'record_id', 'username', 'dropped', 'dropped_surveys']

        # Add study date fields if configured
        if self.project_config:
            if self.project_config.study_start_date_field:
                fields.append(self.project_config.study_start_date_field)
            if self.project_config.study_end_date_field:
                fields.append(self.project_config.study_end_date_field)

            # Add custom display fields
            for custom_field in self.project_config.custom_display_fields:
                field_name = custom_field.get('field')
                if field_name and field_name not in fields:
                    fields.append(field_name)

        data = {
            'token': self.api_token,
            'content': 'record',
            'format': 'json',
            'type': 'flat',
            'fields': ','.join(fields),
            'filterLogic': self.filter_logic,
            'returnFormat': 'json'
        }

        # Only add event if specified (for longitudinal projects)
        if self.event_name:
            data['events'] = self.event_name
        print(data)

        try:
            response = requests.post(self.api_url, data=data, timeout=30)
            response.raise_for_status()

            participants = response.json()

            # Attach project info to each participant
            if self.project_config:
                for p in participants:
                    p['_project_id'] = self.project_config.id
                    p['_project_name'] = self.project_config.name

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
            'fields': self.firebase_id_field,
            'filterLogic': self.filter_logic,
            'returnFormat': 'json'
        }

        # Only add event if specified (for longitudinal projects)
        if self.event_name:
            data['events'] = self.event_name

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
            'filterLogic': f'[{self.firebase_id_field}] = "{firebase_id}"',
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


class REDCapServiceManager:
    """Manager for handling multiple REDCap project services"""

    def __init__(self):
        self._services = {}

    def get_service(self, project_id):
        """Get or create a REDCapService for a specific project"""
        if project_id not in self._services:
            project_config = Config.get_project_by_id(project_id)
            if project_config:
                self._services[project_id] = REDCapService(project_config)
            else:
                return None
        return self._services[project_id]

    def get_all_participants_all_projects(self):
        """Fetch participants from all configured projects"""
        all_participants = []

        for project in Config.get_all_projects():
            service = self.get_service(project.id)
            if service:
                try:
                    participants = service.get_all_participants()
                    all_participants.extend(participants)
                except Exception as e:
                    print(f"Error fetching from project {project.id}: {e}")

        return all_participants

    def get_active_firebase_ids_all_projects(self):
        """Get all active Firebase IDs from all projects"""
        all_ids = set()

        for project in Config.get_all_projects():
            service = self.get_service(project.id)
            if service:
                try:
                    ids = service.get_active_participants()
                    all_ids.update(ids)
                except Exception as e:
                    print(f"Error fetching from project {project.id}: {e}")

        return list(all_ids)


# Singleton instances
redcap_service_manager = REDCapServiceManager()

# For backward compatibility - returns service for first/default project
redcap_service = REDCapService()
