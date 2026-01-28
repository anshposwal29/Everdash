# Theradash - Therabot Conversation Monitoring Platform

A production-ready Flask-based dashboard for monitoring and reviewing Therabot conversations in real-time with Firebase, REDCap, and Twilio integration.

## Overview

Theradash provides study administrators with a comprehensive monitoring platform for tracking conversations between participants and the Therabot AI chatbot. The system automatically syncs data from Firebase Firestore, integrates with REDCap to identify study participants, and sends SMS alerts for high-risk messages.

**Quick Links:**
- [AWS Deployment Guide](AWS_DEPLOYMENT_GUIDE.md) - Complete guide for production deployment
- [Project Summary](PROJECT_SUMMARY.md) - Detailed technical overview
- [Cron Setup Guide](CRON_SETUP.md) - Automated sync configuration

## Features

- **Real-time Dashboard**: View user conversations organized by dates (Eastern Time)
- **REDCap Integration**: Automatically pulls active study participants
- **Firebase Sync**: Syncs messages, conversations, and user data (only pulls new messages to save costs)
- **Risk Score Monitoring**: Highlights high-risk messages and sends SMS alerts via Twilio
- **Message Review Tracking**: Track which messages have been reviewed and by whom
- **Participant Notes**: Add and manage notes about study participants
- **IP Filtering**: Restricts access to specified IP ranges (VPN required)
- **Admin Authentication**: Secure admin accounts with registration keys

## Quick Start (Local Development)

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd theradash
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env` and configure all settings:

```bash
cp .env.example .env
nano .env  # Or use your preferred editor
```

**Required Configuration:**

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Flask secret key | Generate with: `python3 -c 'import secrets; print(secrets.token_hex(32))'` |
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase service account JSON | `./firebase-credentials.json` |
| `REDCAP_API_URL` | REDCap API endpoint | `https://redcap.example.com/api/` |
| `REDCAP_API_TOKEN` | REDCap API token | Your token with read access |
| `USER_SELECTION_MODE` | User selection method | `redcap`, `uids`, or `both` |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | From Twilio dashboard |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | From Twilio dashboard |
| `TWILIO_FROM_NUMBER` | SMS sender number | `+15551234567` (E.164 format) |
| `TWILIO_ADMIN_NUMBERS` | SMS alert recipients | `+15551234567,+15559876543` |
| `IP_PREFIX_ALLOWED` | Allowed IP prefix | `10.0.0` (first 3 octets) |
| `REGISTRATION_KEY` | Admin registration key | Choose a secure password |

**See [.env.example](.env.example) for complete configuration options.**

### 5. Initialize Database

```bash
python app.py
```

This creates the SQLite database at `instance/theradash.db` with all necessary tables.

### 6. Create First Admin User

1. Start the application: `python app.py`
2. Navigate to `http://localhost:5001/register`
3. Enter username, email, and password
4. Use your **REGISTRATION_KEY** from `.env`
5. Login and access the dashboard

### 7. Setup Automated Sync (Optional)

For automatic data synchronization every 2 minutes:

```bash
./setup_cron.sh
```

Check sync status:
```bash
./check_cron_status.sh
```

**See [CRON_SETUP.md](CRON_SETUP.md) for detailed information.**

## Usage

### User Selection Configuration

Theradash supports three methods for selecting which users to monitor:

1. **REDCap Mode (`USER_SELECTION_MODE=redcap`)**
   - Default mode
   - Monitors users based on REDCap filter logic
   - Best for monitoring study participants
   - Users must be in your REDCap project

2. **Firebase UIDs Mode (`USER_SELECTION_MODE=uids`)**
   - Monitors specific Firebase users by their UID
   - Add UIDs to `FIREBASE_UIDS` (comma-separated)
   - Perfect for external testers not in REDCap
   - Example: `FIREBASE_UIDS=abc123,def456,ghi789`

3. **Both Mode (`USER_SELECTION_MODE=both`)**
   - Combines REDCap participants AND Firebase UIDs
   - Monitors all study participants plus external testers
   - Most comprehensive option

**Example Configuration:**
```bash
# Monitor only external testers
USER_SELECTION_MODE=uids
FIREBASE_UIDS=test_user_1,test_user_2,test_user_3

# Monitor study participants + external testers
USER_SELECTION_MODE=both
FIREBASE_UIDS=external_tester_1,external_tester_2
```

### Syncing Data

1. **Initial Sync**: Click "Refresh Data" on the dashboard to pull all participants and messages
2. **Regular Syncs**: The system only fetches NEW messages since the last sync to minimize Firebase costs
3. **REDCap Participants**: All participants from REDCap will be shown, even if they don't have Firebase IDs yet
4. **UID-Based Users**: Users specified in `FIREBASE_UIDS` will appear as "External Tester" in the dashboard

### Dashboard View

- **Rows**: Study participants (from REDCap)
- **Columns**: Dates (in Eastern Time)
- **Green Cells**: Messages exist for that day
- **Red Cells**: High-risk messages detected (above threshold)
- **Gray Cells**: No messages for that day
- **Click Any Cell**: View messages for that user/day

### Message Review

- Click on any user/day cell to view messages
- Mark messages as reviewed to track your progress
- Add notes about participants as needed

### Risk Alerts

When a message with a risk score above the threshold is detected:
1. The dashboard cell turns red
2. SMS alerts are automatically sent to configured admin phone numbers
3. Alert status is tracked in the database

## Project Structure

```
theradash/
├── app.py                    # Main Flask application
├── config.py                 # Configuration management
├── models.py                 # SQLAlchemy database models
├── middleware.py             # IP filtering and auth decorators
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables (not in git)
├── .env.example              # Example environment file
├── services/
│   ├── firebase_service.py   # Firebase Firestore integration
│   ├── redcap_service.py     # REDCap API integration
│   ├── twilio_service.py     # Twilio SMS integration
│   └── sync_service.py       # Data synchronization logic
├── templates/                # HTML templates
│   ├── base.html
│   ├── dashboard.html
│   ├── login.html
│   ├── register.html
│   ├── user_detail.html
│   ├── admin_users.html
│   ├── settings.html
│   ├── 403.html
│   └── 404.html
└── static/
    ├── css/
    │   └── style.css         # Custom styles
    └── js/
        └── main.js           # JavaScript utilities
```

## Database Models

- **Admin**: Admin user accounts
- **User**: Study participants (linked to REDCap and Firebase)
- **Conversation**: Chat conversations
- **Message**: Individual messages with risk scores
- **SyncLog**: Tracks sync operations
- **ParticipantNote**: Notes about participants

## Security Features

1. **IP Filtering**: All requests must come from allowed IP prefix
2. **Admin Authentication**: Flask-Login with password hashing
3. **Registration Keys**: Required for creating new admin accounts
4. **Session Management**: Secure cookie-based sessions

## API Endpoints

- `GET /` - Redirect to dashboard
- `GET /dashboard` - Main dashboard view
- `GET /user/<firebase_id>` - User detail page
- `POST /api/sync` - Trigger data sync
- `GET /admin/users` - Manage admin users
- `POST /admin/users/<id>/toggle` - Toggle admin status
- `GET /settings` - View application settings
- `GET /login` - Login page
- `POST /login` - Authenticate admin
- `GET /register` - Registration page
- `POST /register` - Create new admin
- `GET /logout` - Logout current admin

## Important Notes

### Cost Optimization

The sync system is designed to minimize Firebase costs:
- **First Sync**: Pulls all data
- **Subsequent Syncs**: Only fetches messages newer than the last sync timestamp
- Sync logs track what was pulled and when

### REDCap Integration

- Displays ALL participants from REDCap
- Shows "No Firebase ID" for participants who haven't set up Firebase yet
- Uses `firebase_id` field in REDCap to link participants
- Filter logic can be customized via `REDCAP_FILTER_LOGIC` environment variable

### Time Zones

- All times displayed in Eastern Time (America/New_York)
- Timestamps stored in UTC in the database
- Conversion happens at display time

## Production Deployment

### AWS EC2 Deployment (Recommended)

For production deployment on AWS EC2, we provide a complete automated deployment solution:

**📖 See [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md) for detailed instructions**

**Quick Deployment Steps:**

1. **Launch EC2 Instance**
   - Ubuntu 22.04 LTS
   - t2.medium (2 vCPU, 4 GB RAM)
   - 20 GB storage
   - Configure Security Group with VPN IP restrictions

2. **Clone and Configure**
   ```bash
   git clone <your-repo-url>
   cd theradash
   cp .env.example .env
   nano .env  # Configure all settings
   ```

3. **Run Automated Deployment**
   ```bash
   chmod +x deploy_aws.sh
   ./deploy_aws.sh
   ```

The deployment script automatically:
- ✅ Installs all system dependencies (Python, Nginx, Supervisor)
- ✅ Creates virtual environment and installs Python packages
- ✅ Initializes SQLite database
- ✅ Configures Gunicorn (WSGI server) with optimal settings
- ✅ Sets up Supervisor (process management)
- ✅ Configures Nginx (reverse proxy with SSL)
- ✅ Installs automated sync cron job (runs every 2 minutes)
- ✅ Configures firewall rules

**Deployment Time:** ~5-10 minutes

**Monthly Cost:** ~$32-38 (t2.medium + storage)

### Manual Deployment

If you prefer manual deployment or are using a different hosting provider:

1. **Install Dependencies**
   ```bash
   sudo apt-get install python3.8 python3.8-venv nginx supervisor
   ```

2. **Setup Application**
   ```bash
   python3.8 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   pip install gunicorn
   ```

3. **Configure Gunicorn**
   ```bash
   gunicorn -w 4 -b 127.0.0.1:8000 app:app
   ```

4. **Configure Nginx** (see AWS_DEPLOYMENT_GUIDE.md for complete config)

5. **Setup SSL** with Let's Encrypt
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

## Troubleshooting

### Firebase Connection Issues
- Verify `FIREBASE_CREDENTIALS_PATH` points to valid JSON file
- Ensure Firebase service account has Firestore permissions

### REDCap Connection Issues
- Check `REDCAP_API_URL` is correct (must end with `/api/`)
- Verify `REDCAP_API_TOKEN` has read access
- Test filter logic in REDCap's API playground

### Twilio SMS Not Sending
- Verify Twilio credentials are correct
- Check phone numbers are in E.164 format (+1234567890)
- Ensure Twilio account is funded and active

### IP Blocking Issues
- Temporarily disable IP filter in `app.py` for testing
- Verify your IP matches the `IP_PREFIX_ALLOWED` setting
- Check if you're behind a proxy (X-Forwarded-For header)

## Support

For issues or questions, contact the development team.

## License

Proprietary - For authorized use only.
