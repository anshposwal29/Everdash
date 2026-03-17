from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random

db = SQLAlchemy()


class Admin(UserMixin, db.Model):
    """Admin user model for authentication"""
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=True)
    phone_number = db.Column(db.String(20), nullable=True) 

    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'


class REDCapProject(db.Model):
    """REDCap project configuration stored in database"""
    __tablename__ = 'redcap_projects'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    api_url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    users = db.relationship('User', backref='project', lazy='dynamic')

    def __repr__(self):
        return f'<REDCapProject {self.project_id}>'


class User(db.Model):
    """Study participant user model"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    firebase_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    redcap_firebase_id = db.Column(db.String(100), index=True)  # Original firebase_id from REDCap
    redcap_id = db.Column(db.String(100), index=True)
    identifier = db.Column(db.String(255))
    research_assistant = db.Column(db.String(100))
    current_convo_id = db.Column(db.String(100))
    is_animated = db.Column(db.Boolean, default=False)
    is_dark_mode = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    symptom_radar = db.Column(db.Integer, nullable=False, default=5)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Multi-project support
    project_id = db.Column(db.String(50), db.ForeignKey('redcap_projects.project_id'), index=True)

    # Study dates
    study_start_date = db.Column(db.Date)
    study_end_date = db.Column(db.Date)
    dropped = db.Column(db.Boolean, default=False)
    dropped_surveys = db.Column(db.Boolean, default=False)

    # Relationships
    conversations = db.relationship('Conversation', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    custom_fields = db.relationship('UserCustomField', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.firebase_id}>'


class UserCustomField(db.Model):
    """Store custom REDCap field values per user"""
    __tablename__ = 'user_custom_fields'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    field_name = db.Column(db.String(100), nullable=False)
    field_label = db.Column(db.String(200))
    field_value = db.Column(db.Text)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_user_field', 'user_id', 'field_name'),
    )

    def __repr__(self):
        return f'<UserCustomField {self.field_name}={self.field_value}>'


class Conversation(db.Model):
    """Conversation model"""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    firebase_convo_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    prompt = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # --- ADDED FOR V2 UI ---
    trigger_type = db.Column(db.String(50), default='user_initiated') # 'passive_sensing' or 'user_initiated'
    has_risk = db.Column(db.Boolean, default=False)
    # -----------------------

    # Relationships
    messages = db.relationship('Message', backref='conversation', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Conversation {self.firebase_convo_id}>'


class Message(db.Model):
    """Message model"""
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    firebase_message_id = db.Column(db.String(100), unique=True, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversations.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    is_risky = db.Column(db.Boolean, default=False)
    alert_sent = db.Column(db.Boolean, default=False)
    is_reviewed = db.Column(db.Boolean, default=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reviewed_by = db.relationship('Admin', backref='reviewed_messages')

    def __repr__(self):
        return f'<Message {self.id} - Risky: {self.is_risky}>'


class SyncLog(db.Model):
    """Track sync operations"""
    __tablename__ = 'sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    last_sync_timestamp = db.Column(db.DateTime, nullable=False, index=True)
    messages_synced = db.Column(db.Integer, default=0)
    conversations_synced = db.Column(db.Integer, default=0)
    users_synced = db.Column(db.Integer, default=0)
    sync_duration_seconds = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SyncLog {self.created_at}>'


class PassiveData(db.Model):
    """Flexible storage for passive sensing metrics."""
    __tablename__ = 'passive_data'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    metric_type = db.Column(db.String(50), nullable=False, index=True)
    value = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(50)) 

    def __repr__(self):
        return f'<PassiveData {self.metric_type}: {self.value}>'


class Notes(db.Model):
    """Notes about study participants"""
    __tablename__ = 'notes'

    note_id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer)
    participant_id = db.Column(db.String(16), index=True)
    note_type = db.Column(db.String(256))
    note_reason = db.Column(db.String(256))
    datetime = db.Column(db.String(256))
    duration = db.Column(db.String(25))
    note = db.Column(db.String(2500))

    def __repr__(self):
        return f'<Notes {self.note_id} for Participant {self.participant_id}>'
    
class PassiveDailySummary(db.Model):
    """
    Tracks daily passive data compliance (hours collected).
    Required for the 'Priority View' radar.
    """
    __tablename__ = "passive_daily_summary"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)

    # Hours collected per sensor
    loc_hours = db.Column(db.Float, nullable=False, default=0.0)
    bat_hours = db.Column(db.Float, nullable=False, default=0.0)
    acc_hours = db.Column(db.Float, nullable=False, default=0.0)
    gyr_hours = db.Column(db.Float, nullable=False, default=0.0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("user_id", "day", name="uq_passive_user_day"),
        db.Index("ix_passive_user_day", "user_id", "day"),
    )

    def __repr__(self):
        return f"<PassiveDailySummary user_id={self.user_id} day={self.day}>"
    
    