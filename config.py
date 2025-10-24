"""
Theradash Configuration Module

This module loads all configuration settings from environment variables using python-dotenv.
Configuration values are loaded from the .env file in the project root.

Environment Variables Required:
    - SECRET_KEY: Flask secret key for session management
    - DATABASE_URL: SQLAlchemy database connection string
    - FIREBASE_CREDENTIALS_PATH: Path to Firebase service account JSON
    - REDCAP_API_URL: REDCap API endpoint
    - REDCAP_API_TOKEN: REDCap API authentication token
    - TWILIO_*: Twilio SMS service credentials
    - IP_PREFIX_ALLOWED: Allowed IP address prefix for security
    - REGISTRATION_KEY: Key required for admin registration

See .env.example for a complete list of configuration options.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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

    # Firebase settings
    FIREBASE_CREDENTIALS_PATH = os.environ.get('FIREBASE_CREDENTIALS_PATH')

    # REDCap settings
    REDCAP_API_URL = os.environ.get('REDCAP_API_URL')
    REDCAP_API_TOKEN = os.environ.get('REDCAP_API_TOKEN')
    REDCAP_FILTER_LOGIC = os.environ.get('REDCAP_FILTER_LOGIC', '[interview_1_arm_1][first_interview_updated_complete]="2"')
    REDCAP_FORM_NAME = os.environ.get('REDCAP_FORM_NAME', 'clinical_trial_monitoring')
    REDCAP_EVENT_NAME = os.environ.get('REDCAP_EVENT_NAME', 'screening_part_2_arm_1')
    REDCAP_FIREBASE_ID_FIELD = os.environ.get('REDCAP_FIREBASE_ID_FIELD', 'firebase_id')
    REDCAP_RA_FIELD = os.environ.get('REDCAP_RA_FIELD', 'ra')

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

    # Risk score settings
    RISK_SCORE_THRESHOLD = float(os.environ.get('RISK_SCORE_THRESHOLD', '0.7'))

    # Timezone
    TIMEZONE = 'America/New_York'  # Eastern Time
