# Theradash Implementation Notes

## What's Been Built

### Core Infrastructure
- ✅ Flask application with SQLAlchemy ORM
- ✅ SQLite database (perfect for AWS deployment)
- ✅ Flask-Login authentication system
- ✅ IP filtering middleware for VPN security
- ✅ Registration key system for admin accounts

### Data Integration
- ✅ Firebase Firestore integration
- ✅ REDCap API integration
- ✅ Twilio SMS integration
- ✅ Smart sync system (only pulls new messages to save Firebase costs)

### Database Models
- ✅ Admin users with password hashing
- ✅ Users (study participants) linked to both REDCap and Firebase
- ✅ Conversations and Messages
- ✅ Message review tracking (tracks which admin reviewed which messages)
- ✅ Participant notes (admins can add notes about participants)
- ✅ Sync logs (tracks all sync operations)

### Features Implemented
- ✅ Dashboard with user rows × date columns (Eastern Time)
- ✅ Date range filtering
- ✅ Real-time refresh button
- ✅ Risk score monitoring with red highlighting
- ✅ Automatic SMS alerts for high-risk messages
- ✅ User detail pages showing all messages
- ✅ Admin user management
- ✅ Settings/configuration page
- ✅ All REDCap participants shown (even without Firebase IDs)

## What Still Needs Implementation

### 1. Message Review Interface (PRIORITY)

You need to add routes and UI for:

**In `app.py`, add:**

```python
from models import ParticipantNote

@app.route('/messages/<date>/user/<firebase_id>')
@login_required
def messages_by_date(firebase_id, date):
    """View messages for a specific user on a specific date"""
    user = User.query.filter_by(firebase_id=firebase_id).first_or_404()

    # Parse date
    date_obj = datetime.strptime(date, '%Y-%m-%d').date()
    date_start = et_tz.localize(datetime.combine(date_obj, datetime.min.time()))
    date_end = et_tz.localize(datetime.combine(date_obj, datetime.max.time()))

    # Convert to UTC
    date_start_utc = date_start.astimezone(pytz.utc).replace(tzinfo=None)
    date_end_utc = date_end.astimezone(pytz.utc).replace(tzinfo=None)

    # Get messages
    messages = Message.query.filter(
        and_(
            Message.user_id == user.id,
            Message.timestamp >= date_start_utc,
            Message.timestamp <= date_end_utc
        )
    ).order_by(Message.timestamp.asc()).all()

    # Convert timestamps to ET
    for message in messages:
        message.timestamp_et = message.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)

    # Get participant notes
    notes = ParticipantNote.query.filter_by(user_id=user.id).order_by(ParticipantNote.created_at.desc()).all()

    return render_template('messages_by_date.html',
                         user=user,
                         messages=messages,
                         date=date_obj,
                         notes=notes,
                         risk_threshold=Config.RISK_SCORE_THRESHOLD)

@app.route('/api/messages/<int:message_id>/review', methods=['POST'])
@login_required
def mark_message_reviewed(message_id):
    """Mark a message as reviewed"""
    message = Message.query.get_or_404(message_id)

    message.is_reviewed = True
    message.reviewed_by_id = current_user.id
    message.reviewed_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Message marked as reviewed',
        'reviewed_by': current_user.username
    })

@app.route('/api/user/<int:user_id>/notes', methods=['POST'])
@login_required
def add_participant_note(user_id):
    """Add a note about a participant"""
    user = User.query.get_or_404(user_id)
    note_text = request.json.get('note_text')

    if not note_text:
        return jsonify({'success': False, 'message': 'Note text required'}), 400

    note = ParticipantNote(
        user_id=user.id,
        admin_id=current_user.id,
        note_text=note_text
    )

    db.session.add(note)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Note added successfully',
        'note': {
            'id': note.id,
            'text': note.note_text,
            'admin': current_user.username,
            'created_at': note.created_at.strftime('%Y-%m-%d %I:%M %p')
        }
    })
```

### 2. Create `messages_by_date.html` Template

Create a new template with:
- List of messages for that day
- Checkboxes to mark messages as reviewed
- Section to add/view participant notes
- Show review status (reviewed/not reviewed, by whom, when)

### 3. Update Dashboard to Link to Day-Specific Views

In `dashboard.html`, make the cells clickable:

```html
<td class="message-cell {% if cell_data.has_high_risk %}high-risk{% elif cell_data.count > 0 %}has-messages{% endif %}"
    onclick="window.location='{{ url_for('messages_by_date', firebase_id=user_row.firebase_id, date=date.isoformat()) }}'"
    style="cursor: pointer;">
```

### 4. Add Bootstrap (User Requested Clean Design)

Update `base.html` to include Bootstrap 5:

```html
<head>
    ...
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
    ...
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
</body>
```

Then update your CSS to work WITH Bootstrap (enhance, don't override).

### 5. Update Dashboard to Show Firebase Status

In the dashboard, show which participants have/don't have Firebase IDs:

```html
{% if user_row.firebase_id.startswith('redcap_') %}
<span class="badge bg-warning">No Firebase ID</span>
{% endif %}
```

### 6. Testing Checklist

Before deploying:
- [ ] Test Firebase connection
- [ ] Test REDCap API connection
- [ ] Test Twilio SMS sending
- [ ] Test sync with no previous data
- [ ] Test sync with existing data (should only pull new messages)
- [ ] Test IP filtering
- [ ] Test admin registration
- [ ] Test admin login/logout
- [ ] Test dashboard date filtering
- [ ] Test user detail pages
- [ ] Test message review marking
- [ ] Test participant notes
- [ ] Test risk score alerts

## Environment Setup

### Required Environment Variables

```bash
# Flask
SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">

# Firebase
FIREBASE_CREDENTIALS_PATH=/path/to/service-account.json

# REDCap
REDCAP_API_URL=https://redcap.institution.edu/api/
REDCAP_API_TOKEN=<your-token>
REDCAP_FILTER_LOGIC=[enrollment_status]="1"

# Twilio
TWILIO_ACCOUNT_SID=<from-twilio-console>
TWILIO_AUTH_TOKEN=<from-twilio-console>
TWILIO_FROM_NUMBER=+15555551234
TWILIO_ADMIN_NUMBERS=+15555555678,+15555559012

# Security
IP_PREFIX_ALLOWED=192.168.1
REGISTRATION_KEY=<create-secure-key>

# Risk Monitoring
RISK_SCORE_THRESHOLD=0.7
```

## AWS Deployment Steps

1. **Launch EC2 Instance**
   - Amazon Linux 2 or Ubuntu 20.04
   - t2.small or larger
   - Configure security group to allow SSH and HTTP/HTTPS
   - Add your VPN IP range to security group

2. **Install Dependencies**
   ```bash
   sudo yum update -y
   sudo yum install python3 python3-pip git -y
   ```

3. **Clone and Setup**
   ```bash
   git clone <your-repo>
   cd theradash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   nano .env  # Edit with your credentials
   ```

5. **Initialize Database**
   ```bash
   python app.py
   # Ctrl+C after tables are created
   ```

6. **Set Up Systemd Service**
   Create `/etc/systemd/system/theradash.service`:
   ```ini
   [Unit]
   Description=Theradash Flask Application
   After=network.target

   [Service]
   User=ec2-user
   WorkingDirectory=/home/ec2-user/theradash
   Environment="PATH=/home/ec2-user/theradash/venv/bin"
   ExecStart=/home/ec2-user/theradash/venv/bin/gunicorn -w 4 -b 0.0.0.0:8000 app:app

   [Install]
   WantedBy=multi-user.target
   ```

   Enable and start:
   ```bash
   sudo systemctl enable theradash
   sudo systemctl start theradash
   ```

7. **Set Up Nginx**
   Install: `sudo yum install nginx -y`

   Configure `/etc/nginx/conf.d/theradash.conf`:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }
   }
   ```

8. **SSL with Let's Encrypt**
   ```bash
   sudo yum install certbot python3-certbot-nginx -y
   sudo certbot --nginx -d your-domain.com
   ```

## Firebase Setup

1. Go to Firebase Console
2. Create/select your project
3. Go to Project Settings → Service Accounts
4. Click "Generate New Private Key"
5. Save the JSON file securely
6. Set `FIREBASE_CREDENTIALS_PATH` to point to this file

## REDCap Setup

1. Go to REDCap project
2. API → Generate API Token
3. Ensure `firebase_id` field exists in your project
4. Test the filter logic in API playground
5. Set `REDCAP_API_TOKEN` in environment

## Twilio Setup

1. Create Twilio account
2. Get a phone number
3. Copy Account SID and Auth Token from console
4. Set environment variables
5. Ensure recipient numbers are verified (if using trial account)

## Next Steps

1. Implement the message review interface (routes + template)
2. Add Bootstrap to templates for clean design
3. Test all integrations
4. Deploy to AWS
5. Create first admin account
6. Perform initial data sync
7. Train admins on usage

## Support

Contact: [Your Contact Info]
