from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

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

    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """Check if provided password matches hash"""
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<Admin {self.username}>'


class User(db.Model):
    """Study participant user model"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    firebase_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    redcap_id = db.Column(db.String(100), index=True)
    identifier = db.Column(db.String(255))  # Email or identifier from Firebase Authentication
    research_assistant = db.Column(db.String(100))  # RA assigned to this participant
    current_convo_id = db.Column(db.String(100))
    is_animated = db.Column(db.Boolean, default=False)
    is_dark_mode = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    last_synced = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    conversations = db.relationship('Conversation', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.firebase_id}>'


class Conversation(db.Model):
    """Conversation model"""
    __tablename__ = 'conversations'

    id = db.Column(db.Integer, primary_key=True)
    firebase_convo_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    prompt = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    risk_score = db.Column(db.Float)
    alert_sent = db.Column(db.Boolean, default=False)
    is_reviewed = db.Column(db.Boolean, default=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('admins.id'))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    reviewed_by = db.relationship('Admin', backref='reviewed_messages')

    def __repr__(self):
        return f'<Message {self.id} - Risk: {self.risk_score}>'


class SyncLog(db.Model):
    """Track sync operations to avoid re-processing old messages"""
    __tablename__ = 'sync_logs'

    id = db.Column(db.Integer, primary_key=True)
    last_sync_timestamp = db.Column(db.DateTime, nullable=False, index=True)
    messages_synced = db.Column(db.Integer, default=0)
    conversations_synced = db.Column(db.Integer, default=0)
    users_synced = db.Column(db.Integer, default=0)
    sync_duration_seconds = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<SyncLog {self.created_at} - {self.messages_synced} messages>'


class ParticipantNote(db.Model):
    """Notes about study participants"""
    __tablename__ = 'participant_notes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=False)
    note_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref='notes')
    admin = db.relationship('Admin', backref='participant_notes')

    def __repr__(self):
        return f'<ParticipantNote {self.id} for User {self.user_id}>'
