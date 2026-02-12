"""
Schema Bridge
Defines the database tables using pure SQLAlchemy.
This allows scripts to access the database without loading the entire Flask website.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, ForeignKey, Float
from sqlalchemy.orm import relationship, declarative_base

# The base class for all database models
Base = declarative_base()

class REDCapProject(Base):
    __tablename__ = 'redcap_projects'
    
    id = Column(Integer, primary_key=True)
    project_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    api_url = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    firebase_id = Column(String(100), unique=True, nullable=False, index=True)
    
    # REDCap Data
    redcap_firebase_id = Column(String(100), index=True)
    redcap_id = Column(String(100), index=True)
    identifier = Column(String(255))
    research_assistant = Column(String(100))
    
    # Project Link
    project_id = Column(String(50), ForeignKey('redcap_projects.project_id'), index=True)
    
    # Study Dates
    study_start_date = Column(Date)
    study_end_date = Column(Date)
    
    # Status
    dropped = Column(Boolean, default=False)
    dropped_surveys = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_synced = Column(DateTime, default=datetime.utcnow)
    
    # Firebase Params
    current_convo_id = Column(String(100))
    is_animated = Column(Boolean, default=False)
    is_dark_mode = Column(Boolean, default=False)

    # Relationships
    custom_fields = relationship('UserCustomField', backref='user', cascade='all, delete-orphan')

class UserCustomField(Base):
    __tablename__ = 'user_custom_fields'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    field_label = Column(String(200))
    field_value = Column(Text)
    last_updated = Column(DateTime, default=datetime.utcnow)

class PassiveData(Base):
    """
    Flexible storage for passive sensing metrics.
    Row-based design allows adding new metric types (steps, sleep, etc.) 
    without changing the database structure.
    """
    __tablename__ = 'passive_data'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True) # e.g. 'steps', 'sleep_minutes', 'home_time'
    value = Column(Float, nullable=False)
    
    # Optional: Source of the data (e.g., 'fitbit', 'apple_health', 'aware')
    source = Column(String(50)) 

    def __repr__(self):
        return f'<PassiveData {self.metric_type}: {self.value} @ {self.timestamp}>'

class SyncLog(Base):
    __tablename__ = 'sync_logs'

    id = Column(Integer, primary_key=True)
    last_sync_timestamp = Column(DateTime, nullable=False, index=True)
    messages_synced = Column(Integer, default=0)
    conversations_synced = Column(Integer, default=0)
    users_synced = Column(Integer, default=0)
    sync_duration_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

