# Theradash Architecture Overview

## System Architecture

Theradash is a Flask-based web application that monitors conversations between study participants and the Therabot AI chatbot. The system integrates with three external services and provides a web dashboard for research administrators.

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Services                        │
├──────────────────┬─────────────────────┬────────────────────────┤
│  Firebase        │    REDCap           │      Twilio            │
│  Firestore       │    API              │      SMS               │
│  - Users         │  - Participants     │   - Alerts             │
│  - Conversations │  - Firebase IDs     │                        │
│  - Messages      │  - RA assignments   │                        │
└──────────────────┴─────────────────────┴────────────────────────┘
           ▲                 ▲                      ▲
           │                 │                      │
           │   API Calls     │                      │
           └─────────────────┴──────────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   Sync Service   │
                    │  (sync_service)  │
                    │                  │
                    │ - Orchestrates   │
                    │ - Incremental    │
                    │ - Risk checking  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  SQLite Database │
                    │  (theradash.db)  │
                    │                  │
                    │ - Users          │
                    │ - Conversations  │
                    │ - Messages       │
                    │ - Admins         │
                    │ - Sync Logs      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   Flask App      │
                    │   (app.py)       │
                    │                  │
                    │ - Routes         │
                    │ - Authentication │
                    │ - API endpoints  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Web Dashboard   │
                    │  (HTML/CSS/JS)   │
                    │                  │
                    │ - Grid view      │
                    │ - Message detail │
                    │ - Admin panel    │
                    └──────────────────┘
                             │
                    ┌────────▼─────────┐
                    │   Administrators │
                    │   (via Browser)  │
                    └──────────────────┘
```

## Component Breakdown

### 1. Core Application (app.py)

**Purpose**: Main Flask application providing web interface and API endpoints

**Key Responsibilities**:
- HTTP routing and request handling
- Admin authentication and session management
- Dashboard rendering with conversation grid
- API endpoints for data sync and message review
- IP filtering middleware for security

**Key Routes**:
- `/dashboard` - Main grid view of participants and dates
- `/user/<firebase_id>` - Detailed view of user's conversations
- `/api/sync` - Trigger manual data synchronization
- `/api/messages/<id>/mark-reviewed` - Mark message as reviewed
- `/admin/users` - Admin account management

**Technologies**:
- Flask 3.0.0 (web framework)
- Flask-Login (authentication)
- Jinja2 (templating)

### 2. Database Layer (models.py)

**Purpose**: SQLAlchemy ORM models for local data storage

**Database Schema**:

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   Admin     │     │    User      │     │ Conversation │
├─────────────┤     ├──────────────┤     ├──────────────┤
│ id          │     │ id           │     │ id           │
│ username    │     │ firebase_id  │───┐ │ firebase_id  │
│ email       │     │ redcap_id    │   │ │ user_id      │──┐
│ password    │     │ ra           │   │ │ prompt       │  │
│ created_at  │     │ current_conv │   │ │ timestamp    │  │
│ last_login  │     │ is_active    │   │ └──────────────┘  │
└─────────────┘     └──────────────┘   │                   │
       │                                │                   │
       │ reviewed_by                    │                   │
       │                                │                   │
       └────────────────────────────────┼───────────────────┤
                                        │                   │
                               ┌────────▼─────────┐         │
                               │    Message       │◄────────┘
                               ├──────────────────┤
                               │ id               │
                               │ firebase_msg_id  │
                               │ conversation_id  │
                               │ user_id          │
                               │ text             │
                               │ risk_score       │
                               │ alert_sent       │
                               │ is_reviewed      │
                               │ reviewed_by_id   │
                               │ timestamp        │
                               └──────────────────┘

┌──────────────────┐          ┌────────────────────┐
│   SyncLog        │          │ ParticipantNote    │
├──────────────────┤          ├────────────────────┤
│ id               │          │ id                 │
│ last_sync_time   │          │ user_id            │
│ messages_synced  │          │ admin_id           │
│ conversations    │          │ note_text          │
│ users_synced     │          │ created_at         │
│ duration         │          │ updated_at         │
│ created_at       │          └────────────────────┘
└──────────────────┘
```

**Key Models**:
- **Admin**: Admin user accounts with authentication
- **User**: Study participants (links REDCap and Firebase)
- **Conversation**: Chat sessions with prompts
- **Message**: Individual messages with risk scores
- **SyncLog**: Tracks synchronization history
- **ParticipantNote**: Admin notes about participants

**Database**: SQLite (single file, no server required)

### 3. Configuration (config.py)

**Purpose**: Centralized configuration management

**Configuration Sources**:
1. Environment variables (.env file)
2. Default fallback values

**Key Configuration Groups**:
- Flask settings (SECRET_KEY, database)
- Firebase credentials
- REDCap API settings
- Twilio SMS settings
- Security (IP filtering, registration keys)
- User selection mode
- Risk thresholds

### 4. Service Layer

#### 4.1 Firebase Service (services/firebase_service.py)

**Purpose**: Interface with Firebase Firestore

**Key Functions**:
- `get_users(uids)` - Fetch user data for specific UIDs
- `get_conversations(user_id)` - Get all conversations for a user
- `get_messages(user_id, conversation_id, since_timestamp)` - Fetch messages (incremental)
- `get_user_data(user_id)` - Get single user's preferences

**Optimizations**:
- Incremental message fetching (reduces read costs)
- Batch requests where possible
- Timezone-aware timestamp handling

#### 4.2 REDCap Service (services/redcap_service.py)

**Purpose**: Interface with REDCap API for participant data

**Key Functions**:
- `get_participants()` - Fetch study participants based on filter logic
- Extracts: REDCap ID, Firebase ID, Research Assistant assignment

**Configuration**:
- `REDCAP_FILTER_LOGIC` - Query to select participants
- `REDCAP_FORM_NAME` - Form containing data
- `REDCAP_FIREBASE_ID_FIELD` - Field name for Firebase UID
- `REDCAP_RA_FIELD` - Field name for RA assignment

#### 4.3 Twilio Service (services/twilio_service.py)

**Purpose**: Send SMS alerts for high-risk messages

**Key Functions**:
- `send_risk_alert(user_id, message_text, risk_score)` - Send SMS to admins

**Configuration**:
- `TWILIO_ACCOUNT_SID` - Account identifier
- `TWILIO_AUTH_TOKEN` - Authentication token
- `TWILIO_FROM_NUMBER` - SMS sender number
- `TWILIO_ADMIN_NUMBERS` - Recipients (comma-separated)

#### 4.4 Sync Service (services/sync_service.py)

**Purpose**: Orchestrate data synchronization

**Key Functions**:
- `full_sync()` - Complete sync workflow
- `sync_users()` - Sync user data
- `sync_conversations()` - Sync conversations
- `sync_messages()` - Sync messages (incremental)
- `check_and_send_alerts()` - Check risk scores and alert

**User Selection Modes**:
1. **REDCap Mode**: Monitor only REDCap participants
2. **UIDs Mode**: Monitor only specified Firebase UIDs
3. **Both Mode**: Monitor REDCap + specified UIDs

**Sync Process Flow**:
```
1. Determine user selection mode
2. Get list of users to monitor
   ├─ REDCap mode: Query REDCap API
   ├─ UIDs mode: Use configured UIDs
   └─ Both mode: Combine REDCap + UIDs
3. For each user:
   ├─ Sync user data from Firebase
   ├─ Sync conversations
   └─ Sync messages (only new since last sync)
4. Check risk scores
   └─ Send alerts for high-risk messages
5. Log sync results
```

**Cost Optimization**:
- Only fetches messages newer than last sync timestamp
- Tracks what was synced in SyncLog table
- Minimizes Firebase Firestore read operations

### 5. Security Layer (middleware.py)

**Purpose**: Authentication and IP filtering

**Components**:
- `check_ip_whitelist()` - Verify request IP is allowed
- `@login_required` - Flask-Login decorator
- `@admin_required` - Custom admin verification

**IP Filtering**:
- Checks `X-Forwarded-For` header (for proxies)
- Falls back to `request.remote_addr`
- Compares first 3 octets (e.g., "10.0.0")
- Applies to all routes except static files

### 6. Automated Sync (cron_sync.py)

**Purpose**: Cron job script for automated synchronization

**Usage**:
```bash
*/2 * * * * cd /path/to/theradash && /path/to/venv/bin/python cron_sync.py >> logs/cron_sync.log 2>&1
```

**Features**:
- Runs every 2 minutes (configurable)
- Logs all activity to file
- Error handling and reporting
- Returns exit codes for monitoring

**Setup Script** (`setup_cron.sh`):
- Automatically installs cron job
- Detects virtual environment
- Creates log directory
- Tests sync on installation

### 7. Frontend (templates/ and static/)

#### Templates (Jinja2)
- `base.html` - Base template with navigation
- `dashboard.html` - Main grid view
- `user_detail.html` - User conversation history
- `login.html` / `register.html` - Authentication
- `admin_users.html` - Admin management
- `settings.html` - Configuration display

#### Static Assets
- `static/css/style.css` - Custom styles
- `static/js/main.js` - JavaScript utilities
- Bootstrap 5 (from CDN) - UI framework

#### Dashboard Grid
```
         Date1    Date2    Date3    Date4
User1    [●]      [●]      [○]      [●]
User2    [●]      [○]      [●]      [●]
User3    [○]      [●]      [●]      [○]

Legend:
[●] - Messages exist (green = normal, red = high-risk)
[○] - No messages (gray)
```

## Data Flow

### Sync Flow (Every 2 Minutes)

```
Cron Job Triggers
       │
       ▼
  cron_sync.py
       │
       ▼
  sync_service.full_sync()
       │
       ├──► Get user list (based on mode)
       │    │
       │    ├──► REDCap mode: Query REDCap API
       │    ├──► UIDs mode: Use config UIDs
       │    └──► Both mode: Combine both
       │
       ├──► For each user:
       │    │
       │    ├──► Sync user data (Firebase)
       │    ├──► Sync conversations (Firebase)
       │    └──► Sync messages (Firebase, incremental)
       │
       ├──► Check risk scores
       │    └──► Send SMS alerts if > threshold
       │
       └──► Log sync results to database
```

### User Request Flow

```
Browser Request
       │
       ▼
  Nginx (Reverse Proxy)
       │
       ▼
  IP Filter Check (middleware)
       │
       ▼
  Authentication Check (Flask-Login)
       │
       ▼
  Route Handler (app.py)
       │
       ├──► Query Database (SQLAlchemy)
       │
       ├──► Render Template (Jinja2)
       │
       └──► Return Response
```

### Manual Sync Flow

```
User clicks "Refresh Data"
       │
       ▼
  POST /api/sync
       │
       ▼
  sync_service.full_sync()
       │
       └──► (Same as automated sync)
       │
       ▼
  Return JSON response
       │
       ▼
  Dashboard updates
```

## Deployment Architecture

### Development

```
localhost:5001
       │
       ▼
  Flask Development Server
       │
       ▼
  SQLite Database (local file)
```

### Production (AWS)

```
Internet
   │
   ▼
AWS Security Group (VPN IP restriction)
   │
   ▼
AWS EC2 Instance (t2.medium)
   │
   ├──► Nginx (Port 80/443)
   │    │
   │    ├──► SSL Certificate (Let's Encrypt)
   │    │
   │    └──► Reverse Proxy to Gunicorn
   │         │
   │         ▼
   │    Gunicorn (Port 8000)
   │    - 4-8 workers
   │    - WSGI server
   │         │
   │         ▼
   │    Flask Application
   │         │
   │         ▼
   │    SQLite Database (/home/ubuntu/theradash/instance/)
   │
   └──► Supervisor
        - Process management
        - Auto-restart on failure
        - Logging

Background Process:
   Cron (every 2 minutes)
   └──► cron_sync.py
        └──► Sync data
```

## Security Architecture

### Authentication Flow

```
User visits /dashboard
       │
       ▼
  Session check (Flask-Login)
       │
       ├──► Not authenticated
       │    └──► Redirect to /login
       │
       └──► Authenticated
            └──► Load dashboard
```

### IP Filtering

```
Request arrives
       │
       ▼
Check X-Forwarded-For or remote_addr
       │
       ├──► IP prefix matches IP_PREFIX_ALLOWED
       │    └──► Allow request
       │
       └──► IP prefix doesn't match
            └──► Return 403 Forbidden
```

### Admin Registration

```
User visits /register
       │
       ▼
Enter credentials + REGISTRATION_KEY
       │
       ├──► Key matches Config.REGISTRATION_KEY
       │    └──► Create admin account
       │
       └──► Key doesn't match
            └──► Reject registration
```

## Scalability Considerations

### Current Scale (Single EC2 Instance)
- **Users**: Up to 100 study participants
- **Messages**: Thousands per day
- **Admins**: Up to 10 concurrent
- **Database**: SQLite (single file, 200KB typical)

### Scaling Options

**Horizontal Scaling** (Multiple instances):
1. Replace SQLite with PostgreSQL (RDS)
2. Use Application Load Balancer
3. Deploy to Auto Scaling Group
4. Use ElastiCache for sessions

**Vertical Scaling** (Larger instance):
1. Upgrade to t2.large or t3.large
2. Increase Gunicorn workers
3. Add more memory for caching

## Monitoring and Logging

### Log Files
- `logs/gunicorn_access.log` - HTTP access logs
- `logs/gunicorn_error.log` - Application errors
- `logs/supervisor_*.log` - Process management logs
- `logs/cron_sync.log` - Sync job logs
- `/var/log/nginx/` - Nginx logs

### Database Monitoring
- `SyncLog` table tracks all syncs
- Dashboard shows last sync time
- Cron status script (`check_cron_status.sh`)

### Alert Mechanisms
1. **SMS Alerts**: High-risk messages via Twilio
2. **Sync Failures**: Logged to cron_sync.log
3. **Application Errors**: Logged to gunicorn_error.log

## Technology Stack

### Backend
- Python 3.8+
- Flask 3.0.0 (web framework)
- SQLAlchemy 3.1.1 (ORM)
- Flask-Login 0.6.3 (authentication)
- Gunicorn (WSGI server)

### Database
- SQLite 3 (development and production)
- PostgreSQL (optional for scale)

### Frontend
- HTML5
- Bootstrap 5 (CSS framework)
- Vanilla JavaScript
- Jinja2 templating

### External Services
- Firebase Admin SDK 6.3.0
- Twilio SDK 8.11.0
- REDCap API (HTTP/JSON)

### Infrastructure
- AWS EC2 (Ubuntu 22.04 LTS)
- Nginx (reverse proxy)
- Supervisor (process management)
- Let's Encrypt (SSL certificates)

## File Structure

```
theradash/
├── app.py                        # Main Flask application (17KB)
├── config.py                     # Configuration loader (2KB)
├── models.py                     # Database models (5KB)
├── middleware.py                 # Security middleware (2KB)
├── cron_sync.py                  # Automated sync script (2KB)
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (gitignored)
├── .env.example                  # Example configuration
├── .gitignore                    # Git ignore rules
├── deploy_aws.sh                 # AWS deployment automation
├── setup_cron.sh                 # Cron setup script
├── check_cron_status.sh          # Cron monitoring script
├── gunicorn_config.py            # Gunicorn settings (created by deploy)
├── services/
│   ├── firebase_service.py       # Firebase integration (7KB)
│   ├── redcap_service.py         # REDCap integration (4KB)
│   ├── twilio_service.py         # Twilio SMS integration (3KB)
│   └── sync_service.py           # Sync orchestration (20KB)
├── templates/
│   ├── base.html                 # Base template
│   ├── dashboard.html            # Main dashboard
│   ├── user_detail.html          # User detail view
│   ├── login.html                # Login page
│   ├── register.html             # Registration page
│   ├── admin_users.html          # Admin management
│   ├── settings.html             # Settings display
│   ├── 403.html                  # Access denied
│   └── 404.html                  # Not found
├── static/
│   ├── css/
│   │   └── style.css             # Custom styles
│   └── js/
│       └── main.js               # JavaScript utilities
├── instance/
│   └── theradash.db              # SQLite database (gitignored)
├── logs/                         # Log files (gitignored)
│   ├── gunicorn_access.log
│   ├── gunicorn_error.log
│   ├── supervisor_access.log
│   ├── supervisor_error.log
│   └── cron_sync.log
├── venv/                         # Virtual environment (gitignored)
└── docs/
    ├── README.md                 # Main documentation
    ├── AWS_DEPLOYMENT_GUIDE.md   # AWS deployment guide
    ├── ARCHITECTURE.md           # This file
    ├── PROJECT_SUMMARY.md        # Project overview
    ├── CRON_SETUP.md             # Cron configuration
    ├── IMPLEMENTATION_NOTES.md   # Technical notes
    └── UPDATES.md                # Change log
```

## Key Design Decisions

### Why SQLite?
- **Simplicity**: Single file, no database server
- **Reliability**: ACID compliant, battle-tested
- **Sufficient Scale**: Handles hundreds of users
- **Easy Backup**: Just copy the file
- **Upgrade Path**: Can migrate to PostgreSQL if needed

### Why Incremental Sync?
- **Cost Optimization**: Firebase charges per read
- **Speed**: Only fetch new data
- **Bandwidth**: Reduce data transfer
- **Tracked in**: SyncLog table

### Why Cron Instead of Celery?
- **Simplicity**: No broker (Redis/RabbitMQ) required
- **Reliability**: Built into OS
- **Monitoring**: Easy to check with crontab
- **Sufficient**: 2-minute interval is adequate

### Why Three User Selection Modes?
- **Flexibility**: Different deployment scenarios
- **REDCap Mode**: Production study participants
- **UIDs Mode**: External testers without REDCap
- **Both Mode**: Combined testing and production

## Performance Characteristics

### Response Times (Typical)
- Dashboard load: 200-500ms
- User detail page: 100-300ms
- Manual sync: 5-15 seconds (depends on data volume)
- Automated sync: 2-10 seconds

### Resource Usage (t2.medium)
- CPU: 5-15% average, 40% during sync
- Memory: 500MB-1GB
- Disk I/O: Minimal (SQLite is fast)
- Network: Low (except during Firebase sync)

### Concurrent Users
- **Current Capacity**: 10-20 simultaneous admins
- **Bottleneck**: SQLite write concurrency
- **Solution if needed**: Migrate to PostgreSQL

## Future Enhancements

### Potential Improvements
1. **Testing**: Add pytest test suite
2. **Monitoring**: CloudWatch integration
3. **Alerts**: Email alerts in addition to SMS
4. **Analytics**: Dashboard metrics and charts
5. **Export**: CSV/Excel export of messages
6. **Search**: Full-text search of messages
7. **Filtering**: Advanced dashboard filters
8. **API**: REST API for external integrations
9. **Mobile**: Responsive design improvements
10. **Database**: PostgreSQL migration for scale

### Known Limitations
1. SQLite concurrency (solved by PostgreSQL)
2. No automated testing
3. Basic error handling in some areas
4. Limited logging in production
5. No API rate limiting

## Conclusion

Theradash is a well-architected, production-ready monitoring platform with:
- Clear separation of concerns
- Modular service architecture
- Cost-optimized synchronization
- Comprehensive security
- Complete deployment automation

The architecture supports the current requirements and provides clear upgrade paths for future scaling needs.
