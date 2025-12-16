"""
Theradash Configuration Module

This module loads all configuration settings from environment variables using python-dotenv.
Configuration values are loaded from the .env file in the project root.

Environment Variables Required:
    - SECRET_KEY: Flask secret key for session management
    - DATABASE_URL: SQLAlchemy database connection string
    - FIREBASE_CREDENTIALS_PATH: Path to Firebase service account JSON
    - REDCAP_PROJECTS: JSON array of REDCap project configurations (or legacy single-project vars)
    - TWILIO_*: Twilio SMS service credentials
    - IP_PREFIX_ALLOWED: Allowed IP address prefix for security
    - REGISTRATION_KEY: Key required for admin registration

See .env.example for a complete list of configuration options.
"""

import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class REDCapProjectConfig:
    """Configuration for a single REDCap project"""

    def __init__(self, config_dict):
        self.id = config_dict.get('id')
        self.name = config_dict.get('name', self.id)
        self.api_url = config_dict.get('api_url')
        self.api_token = config_dict.get('api_token')
        self.filter_logic = config_dict.get('filter_logic', '')
        self.form_name = config_dict.get('form_name', '')
        self.event_name = config_dict.get('event_name', '')
        self.firebase_id_field = config_dict.get('firebase_id_field', 'firebase_id')
        self.ra_field = config_dict.get('ra_field', 'ra')
        self.study_start_date_field = config_dict.get('study_start_date_field')
        self.study_end_date_field = config_dict.get('study_end_date_field')
        self.custom_display_fields = config_dict.get('custom_display_fields', [])

    def is_valid(self):
        """Check if minimum required fields are configured"""
        return bool(self.id and self.api_url and self.api_token)

    def __repr__(self):
        return f'<REDCapProjectConfig {self.id}: {self.name}>'


class Config:
    """
    Configuration class for Theradash application.

    All settings are loaded from environment variables with sensible defaults.
    In production, ensure all sensitive values are set via environment variables.
    """

    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///theradash.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Firebase settings (shared across all projects)
    FIREBASE_CREDENTIALS_PATH = os.environ.get('FIREBASE_CREDENTIALS_PATH')

    # REDCap Projects - parsed from JSON or legacy config
    REDCAP_PROJECTS = []
    _redcap_projects_json = os.environ.get('REDCAP_PROJECTS', '')

    # Legacy single-project REDCap settings (for backward compatibility)
    _LEGACY_REDCAP_API_URL = os.environ.get('REDCAP_API_URL')
    _LEGACY_REDCAP_API_TOKEN = os.environ.get('REDCAP_API_TOKEN')
    _LEGACY_REDCAP_FILTER_LOGIC = os.environ.get('REDCAP_FILTER_LOGIC', '[interview_1_arm_1][first_interview_updated_complete]="2"')
    _LEGACY_REDCAP_FORM_NAME = os.environ.get('REDCAP_FORM_NAME', 'clinical_trial_monitoring')
    _LEGACY_REDCAP_EVENT_NAME = os.environ.get('REDCAP_EVENT_NAME', 'screening_part_2_arm_1')
    _LEGACY_REDCAP_FIREBASE_ID_FIELD = os.environ.get('REDCAP_FIREBASE_ID_FIELD', 'firebase_id')
    _LEGACY_REDCAP_RA_FIELD = os.environ.get('REDCAP_RA_FIELD', 'ra')

    @classmethod
    def _parse_redcap_projects(cls):
        """Parse REDCap projects from environment variable"""
        if cls.REDCAP_PROJECTS:
            return  # Already parsed

        # Try to parse JSON array first
        if cls._redcap_projects_json.strip():
            try:
                projects_data = json.loads(cls._redcap_projects_json)
                for proj_data in projects_data:
                    project = REDCapProjectConfig(proj_data)
                    if project.is_valid():
                        cls.REDCAP_PROJECTS.append(project)
                    else:
                        print(f"Warning: Skipping invalid project config: {proj_data.get('id', 'unknown')}")
                if cls.REDCAP_PROJECTS:
                    print(f"Loaded {len(cls.REDCAP_PROJECTS)} REDCap project(s) from JSON config")
                    return
            except json.JSONDecodeError as e:
                print(f"Error parsing REDCAP_PROJECTS JSON: {e}")

        # Fall back to legacy single-project config
        cls._parse_legacy_config()

    @classmethod
    def _parse_legacy_config(cls):
        """Fall back to legacy single-project configuration for backward compatibility"""
        if cls._LEGACY_REDCAP_API_URL and cls._LEGACY_REDCAP_API_TOKEN:
            legacy_project = REDCapProjectConfig({
                'id': 'default',
                'name': 'Default Project',
                'api_url': cls._LEGACY_REDCAP_API_URL,
                'api_token': cls._LEGACY_REDCAP_API_TOKEN,
                'filter_logic': cls._LEGACY_REDCAP_FILTER_LOGIC,
                'form_name': cls._LEGACY_REDCAP_FORM_NAME,
                'event_name': cls._LEGACY_REDCAP_EVENT_NAME,
                'firebase_id_field': cls._LEGACY_REDCAP_FIREBASE_ID_FIELD,
                'ra_field': cls._LEGACY_REDCAP_RA_FIELD,
            })
            cls.REDCAP_PROJECTS.append(legacy_project)
            print("Using legacy single-project REDCap configuration")

    @classmethod
    def get_project_by_id(cls, project_id):
        """Get a specific project configuration by ID"""
        cls._parse_redcap_projects()
        for project in cls.REDCAP_PROJECTS:
            if project.id == project_id:
                return project
        return None

    @classmethod
    def get_all_projects(cls):
        """Get all configured REDCap projects"""
        cls._parse_redcap_projects()
        return cls.REDCAP_PROJECTS

    # User selection settings
    # Options: 'redcap' (use REDCap filter only), 'uids' (use Firebase UIDs only), 'both' (combine both methods), 'all' (pull all Firebase users)
    USER_SELECTION_MODE = os.environ.get('USER_SELECTION_MODE', 'redcap')
    # Comma-separated list of Firebase UIDs to monitor (used when mode is 'uids' or 'both')
    FIREBASE_UIDS = [uid.strip() for uid in os.environ.get('FIREBASE_UIDS', '').split(',') if uid.strip()]

    # Twilio settings
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_FROM_NUMBER = os.environ.get('TWILIO_FROM_NUMBER')
    TWILIO_ADMIN_NUMBERS = os.environ.get('TWILIO_ADMIN_NUMBERS', '').split(',')

    # Security settings
    IP_PREFIX_ALLOWED = os.environ.get('IP_PREFIX_ALLOWED', '192.168.1')  # First 3 digits of allowed IP
    REGISTRATION_KEY = os.environ.get('REGISTRATION_KEY', 'default-registration-key-change-me')

    # Timezone
    TIMEZONE = 'America/New_York'  # Eastern Time


# Initialize parsing on module load
Config._parse_redcap_projects()
