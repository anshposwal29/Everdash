from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message as EmailMessage
from models import db, Admin, User, Message, Conversation, SyncLog, Notes, PassiveData
from config import Config
from middleware import require_ip_whitelist, ip_and_admin_required
from services.sync_service import sync_service
from services.twilio_service import twilio_service
import services.email_service as email_service
from datetime import datetime, timedelta
import pytz
import requests
from sqlalchemy import func, and_
from database import get_db
from services.sensor_service import fetch_sensor_data_external
from sqlalchemy import func, case, desc
from datetime import timedelta, datetime
import pytz
from models import db, Admin, User, Message, Conversation, SyncLog, Notes, PassiveDailySummary
from api_client import fetch_all_participants



app = Flask(__name__)
app.config.from_object(Config)


@app.route('/test_routes')
def test_routes():
    output = []
    for rule in app.url_map.iter_rules():
        output.append(f"{rule.endpoint}: {rule}")
    return "<br>".join(output)

# Initialize 'mail' tool for sending 2FA code
mail = Mail(app)

@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    from datetime import datetime
    
    # 1. SAFETY CHECK: If date is missing/None, return a placeholder
    if not date:
        return 'N/A'
    
    # 2. If it's a string, parse it first
    if isinstance(date, str):
        try:
            # Handle standard ISO format
            date = datetime.fromisoformat(date.replace('Z', '+00:00'))
        except ValueError:
            # Fallback if the string format is unexpected
            return date
    
    # 3. Format the date object
    if fmt:
        return date.strftime(fmt)
    else:
        return date.strftime('%Y-%m-%d')
    

        
# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Timezone
et_tz = pytz.timezone(Config.TIMEZONE)


def date_to_utc_range(date_obj, tz=et_tz):
    """
    Convert a date to UTC datetime range for database queries.
    Returns (start_utc, end_utc) as naive datetimes in UTC.
    """
    date_start = tz.localize(datetime.combine(date_obj, datetime.min.time()))
    date_end = tz.localize(datetime.combine(date_obj, datetime.max.time()))
    start_utc = date_start.astimezone(pytz.utc).replace(tzinfo=None)
    end_utc = date_end.astimezone(pytz.utc).replace(tzinfo=None)
    return start_utc, end_utc


def process_conversations(messages):
    """
    Groups a flat list of message objects into conversation dictionaries 
    and calculates completion percentages for the V2 UI.
    """
    if not messages:
        return []

    sorted_msgs = sorted(messages, key=lambda x: x.timestamp)
    conversations = []
    current_conv = None
    GAP_THRESHOLD = timedelta(hours=2)

    for msg in sorted_msgs:
        msg_timestamp_et = msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
        setattr(msg, 'timestamp_et', msg_timestamp_et)
        msg_time = msg.timestamp
        
        if current_conv is None or (msg_time - current_conv['last_msg_time'] > GAP_THRESHOLD):
            if current_conv:
                conversations.append(current_conv)
            
            current_conv = {
                'id': len(conversations) + 1,
                'messages': [],
                'start_time': msg_timestamp_et,
                'last_msg_time': msg_time,
                'prompt': "General Conversation", 
                'trigger_type': 'user_initiated',
                'trigger_display': 'User Initiated', 
                'has_risk': False,
                'completion_pct': 0  # Initialized here
            }

            if msg.conversation_id:
                try:
                    linked_conv = Conversation.query.get(msg.conversation_id)
                    if linked_conv:
                        current_conv['prompt'] = linked_conv.prompt
                        current_conv['trigger_type'] = linked_conv.trigger_type or 'user_initiated'
                        if linked_conv.trigger_type == 'passive_sensing':
                            current_conv['trigger_display'] = 'Passive Sensing'
                except:
                    pass
        
        current_conv['messages'].append(msg)
        current_conv['last_msg_time'] = msg_time
        if msg.is_risky:
            current_conv['has_risk'] = True

    if current_conv:
        conversations.append(current_conv)
def process_conversations(messages):
    """
    Groups a flat list of message objects into conversation dictionaries 
    and calculates completion percentages for the V2 UI.
    """
    if not messages:
        return []

    sorted_msgs = sorted(messages, key=lambda x: x.timestamp)
    conversations = []
    current_conv = None
    GAP_THRESHOLD = timedelta(hours=2)

    for msg in sorted_msgs:
        msg_timestamp_et = msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
        setattr(msg, 'timestamp_et', msg_timestamp_et)
        msg_time = msg.timestamp
        
        if current_conv is None or (msg_time - current_conv['last_msg_time'] > GAP_THRESHOLD):
            if current_conv:
                conversations.append(current_conv)
            
            current_conv = {
                'id': len(conversations) + 1,
                'messages': [],
                'start_time': msg_timestamp_et,
                'last_msg_time': msg_time,
                'prompt': "General Conversation", 
                'trigger_type': 'user_initiated',
                'trigger_display': 'User Initiated', 
                'has_risk': False,
                'completion_pct': 0  # <--- Fix: Initialize the key here
            }

            if msg.conversation_id:
                try:
                    linked_conv = Conversation.query.get(msg.conversation_id)
                    if linked_conv:
                        current_conv['prompt'] = linked_conv.prompt
                        current_conv['trigger_type'] = linked_conv.trigger_type or 'user_initiated'
                        if linked_conv.trigger_type == 'passive_sensing':
                            current_conv['trigger_display'] = 'Passive Sensing'
                except:
                    pass
        
        current_conv['messages'].append(msg)
        current_conv['last_msg_time'] = msg_time
        if msg.is_risky:
            current_conv['has_risk'] = True

    if current_conv:
        conversations.append(current_conv)

    # Final Polish & Completion Calculation
    for conv in conversations:
        last_utc = conv['last_msg_time']
        conv['last_activity_et'] = last_utc.replace(tzinfo=pytz.utc).astimezone(et_tz)
        
        # Logic: If it's a bot-triggered nudge, calculate progress based on 4 messages
        if conv['trigger_type'] in ['passive_sensing', 'bot']:
            msg_count = len(conv['messages'])
            conv['completion_pct'] = min(100, int((msg_count / 4) * 100))
        else:
            # User-initiated chats are marked as 100% complete
            conv['completion_pct'] = 100
        
    return sorted(conversations, key=lambda x: x['last_activity_et'], reverse=True)

@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


def get_overall_users(window_days=14, sort='silence', order='desc', limit=50, offset=0):
    """
    Generates summary statistics for the 'Overall - List View'
    """
    # 1. Setup Time Window
    now = datetime.now(et_tz)
    cutoff_date = now - timedelta(days=window_days)
    cutoff_date_naive = cutoff_date.replace(tzinfo=None) # For DB comparison

    # 2. Base Query
    users = User.query.filter_by(dropped=False).all()
    
    rows = []
    
    for u in users:
        # --- A. Calculate Silence (Days since last message) ---
        last_msg = Message.query.filter(
            Message.user_id == u.id,
            Message.text.isnot(None) 
        ).order_by(Message.timestamp.desc()).first()
        
        silence_days = None
        if last_msg:
            # Ensure timezone awareness for subtraction
            msg_tz = last_msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
            delta = now - msg_tz
            silence_days = delta.days
        
        # --- B. Calculate Risk (Count in window) ---
        risky_count = Message.query.filter(
            Message.user_id == u.id,
            Message.is_risky == True,
            Message.timestamp >= cutoff_date_naive
        ).count()

        # --- C. Passive Data Compliance (Good Days in window) ---
        passive_stats = {
            'loc': {'good_days': 0},
            'bat': {'good_days': 0},
            'acc': {'good_days': 0},
            'gyr': {'good_days': 0}
        }
        
        # This will be empty until the new table fills up, which is fine!
        summaries = PassiveDailySummary.query.filter(
            PassiveDailySummary.user_id == u.id,
            PassiveDailySummary.day >= cutoff_date.date()
        ).all()

        for s in summaries:
            if s.loc_hours > 0: passive_stats['loc']['good_days'] += 1
            if s.bat_hours > 0: passive_stats['bat']['good_days'] += 1
            if s.acc_hours > 0: passive_stats['acc']['good_days'] += 1
            if s.gyr_hours > 0: passive_stats['gyr']['good_days'] += 1

        # --- D. Build Row ---
        rows.append({
            'user_id': u.id,
            'redcap_id': u.redcap_id,
            'identifier': u.identifier,
            'days_in_study': (now.date() - u.study_start_date).days if u.study_start_date else 0,
            'silence_days': silence_days,
            'risky_count': risky_count,
            'symptom_radar': u.symptom_radar,
            'passive_compliance': passive_stats,
            'dropped': u.dropped,
            'utilization_status': 'Active'
        })

    # 3. Sorting Logic
    reverse = (order == 'desc')
    if sort == 'silence':
        # Sort by silence (None counts as infinity)
        rows.sort(key=lambda x: x['silence_days'] if x['silence_days'] is not None else 9999, reverse=reverse)
    elif sort == 'risk':
        rows.sort(key=lambda x: x['risky_count'], reverse=reverse)
    elif sort == 'days':
        rows.sort(key=lambda x: x['days_in_study'], reverse=reverse)
    elif sort == 'recent':
        rows.sort(key=lambda x: x['silence_days'] if x['silence_days'] is not None else 9999, reverse=not reverse)

    return rows


def get_overall_users(window_days=14, sort='silence', order='desc'):
    """Helper to calculate stats for the List View"""
    now = datetime.now(et_tz)
    cutoff_date = now - timedelta(days=window_days)
    cutoff_date_naive = cutoff_date.replace(tzinfo=None)

    users = User.query.filter_by(dropped=False).all()
    rows = []

    for u in users:
        # 1. Silence
        last_msg = Message.query.filter(
            Message.user_id == u.id,
            Message.text.isnot(None)
        ).order_by(Message.timestamp.desc()).first()
        
        silence_days = None
        if last_msg:
            msg_tz = last_msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
            silence_days = (now - msg_tz).days
        
        # 2. Risk
        risky_count = Message.query.filter(
            Message.user_id == u.id,
            Message.is_risky == True,
            Message.timestamp >= cutoff_date_naive
        ).count()

        # 3. Passive Data (Green Dots)
        passive_stats = {'loc': 0, 'bat': 0, 'acc': 0, 'gyr': 0}
        summaries = PassiveDailySummary.query.filter(
            PassiveDailySummary.user_id == u.id,
            PassiveDailySummary.day >= cutoff_date.date()
        ).all()
        
        for s in summaries:
            if s.loc_hours > 0: passive_stats['loc'] += 1
            if s.bat_hours > 0: passive_stats['bat'] += 1
            if s.acc_hours > 0: passive_stats['acc'] += 1
            if s.gyr_hours > 0: passive_stats['gyr'] += 1

        rows.append({
            'user_id': u.id,
            'redcap_id': u.redcap_id,
            'identifier': u.identifier,
            'days_in_study': (now.date() - u.study_start_date).days if u.study_start_date else 0,
            'silence_days': silence_days,
            'risky_count': risky_count,
            'symptom_radar': getattr(u, 'symptom_radar', 5), # Fallback to 5 if field missing
            'passive_compliance': {k: {'good_days': v} for k, v in passive_stats.items()},
            'dropped': u.dropped
        })

    # Sort
    reverse = (order == 'desc')
    if sort == 'silence':
        rows.sort(key=lambda x: x['silence_days'] if x['silence_days'] is not None else 9999, reverse=reverse)
    elif sort == 'risk':
        rows.sort(key=lambda x: x['risky_count'], reverse=reverse)
    elif sort == 'days':
        rows.sort(key=lambda x: x['days_in_study'], reverse=reverse)
    
    return rows



@app.before_request
def enforce_ip_whitelist():
    """Enforce IP whitelist on all routes"""
    if request.path.startswith('/static/'):
        return

    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip_address = request.remote_addr

    if ip_address == '127.0.0.1':
        return

    allowed_prefix = Config.IP_PREFIX_ALLOWED
    if not ip_address.startswith(allowed_prefix):
        return render_template('403.html', ip_address=ip_address), 403


@app.route('/')
@login_required
def index():
    """Redirect to dashboard"""
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        admin = Admin.query.filter_by(username=username).first()

        if admin and admin.check_password(password):
            if not admin.is_approved:
                flash('Your account is pending approval. An administrator will review your registration.', 'info')
                return redirect(url_for('login'))

            if not admin.is_active:
                flash('Your account has been deactivated. Contact an administrator.', 'error')
                return redirect(url_for('login'))

            login_user(admin)
            admin.last_login = datetime.utcnow()
            db.session.commit()

            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Logout admin"""
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Admin registration page"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        registration_key = request.form.get('registration_key')

        if registration_key != Config.REGISTRATION_KEY:
            flash('Invalid registration key', 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))

        if Admin.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        if Admin.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        admin = Admin(username=username, email=email)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        flash('Registration successful! Pending admin approval.', 'info')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    # --- 1. CONFIGURATION ---
    view = request.args.get('view', 'calendar')
    window_days = int(request.args.get('window', 14))
    sort = request.args.get('sort', 'silence')
    order = request.args.get('order', 'desc')

    # --- 2. FETCH MASTER DATA (API ONLY) ---
    # We rely on the Mock API for the participant list and status
    try:
        api_participants = fetch_all_participants()
    except Exception as e:
        print(f"Error fetching API participants: {e}")
        api_participants = []

    # --- 3. GLOBAL METRICS ---
    # Count how many users have the "Needs Attention" flag active
    attention_count = 0
    for p in api_participants:
        results = p.get('decision_engine_results', {})
        if results.get('needs_attention') is True:
            attention_count += 1

    # --- 4. LIST VIEW ---
    if view == 'list':

        participants = api_participants.copy()

        if sort == 'recent':
            participants.sort(
                key=lambda u: u.get('last_message_at') or '',
                reverse=(order == 'desc')
            )

        elif sort == 'silence':
            participants.sort(
                key=lambda u: u.get('decision_engine_results', {}).get('silence_days', 0),
                reverse=(order == 'desc')
            )

        elif sort == 'risk':
            participants.sort(
                key=lambda u: u.get('decision_engine_results', {}).get('risky_count', 0),
                reverse=(order == 'desc')
            )

        elif sort == 'days':
            participants.sort(
                key=lambda u: u.get('days_in_study', 0),
                reverse=(order == 'asc')
            )

        return render_template(
            'overall_list.html',
            view=view,
            participants=participants,
            window_days=window_days,
            sort=sort,
            order=order,
            attention_count=attention_count
        )

    # --- 5. WEEK VIEW ---
    elif view == 'week':
        return render_template('overall_week.html', 
                               view=view, 
                               window_days=window_days,
                               attention_count=attention_count)

    # --- 6. CALENDAR VIEW ---
    
    # A. Date Logic
    end_date_str = request.args.get('end_date')
    start_date_str = request.args.get('start_date')

    if not end_date_str:
        end_date = datetime.now(et_tz).date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    if not start_date_str:
        start_date = end_date - timedelta(days=6)
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

    date_range = []
    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date)
        current_date += timedelta(days=1)

    # B. Filter API Data
    ra_filter = request.args.get('ra', 'all')
    risk_filter = request.args.get('risk', 'all')
    attention_filter = request.args.get('attention', 'all')
    project_filter = request.args.get('project', 'all') 

    filtered_users = api_participants

    # Filter by Research Assistant
    if ra_filter != 'all':
        filtered_users = [u for u in filtered_users if u.get('research_assistant') == ra_filter]
    
    # Filter by Risk (Risk Score > 0 OR Risky Count > 0)
    if risk_filter == 'risky':
        filtered_users = [u for u in filtered_users if 
                          u.get('decision_engine_results', {}).get('risky_count', 0) > 0 or 
                          u.get('decision_engine_results', {}).get('risk_score', 0) > 0]

    # Filter by Needs Attention
    if attention_filter == 'needs_attention':
        filtered_users = [u for u in filtered_users if u.get('decision_engine_results', {}).get('needs_attention') is True]

    # C. Dynamic Dropdown Options
    research_assistants = sorted(list(set([u.get('research_assistant') for u in api_participants if u.get('research_assistant')])))
    projects = Config.get_all_projects() # Keep SQL for project definitions if needed

    # D. Build Grid Data
    dashboard_data = []

    for user in filtered_users:
        # CRITICAL: Map API 'user_id' -> Template 'firebase_id'
        # This ensures the link {{ url_for('user_detail', firebase_id=...) }} works.
        print(f"DEBUG LOOP: Raw User ID from JSON: {user.get('user_id')}")
        user_row = {
            'firebase_id': user.get('user_id'), 
            'redcap_id': user.get('redcap_id', '-'),
            'identifier': user.get('identifier', '-'),
            'research_assistant': user.get('research_assistant', '-'),
            'project_name': '-', 
            'dropped': user.get('dropped', False),
            'needs_attention': user.get('decision_engine_results', {}).get('needs_attention', False),
            'dates': {}
        }
        print(f"DEBUG LOOP: Resulting user_row ID: {user_row['firebase_id']}")
        
        conversations = user.get('conversations', [])
        
        for date in date_range:
            d_key = date.isoformat() # This produces "2026-02-21"
            
            msgs_for_day = []
            has_risky = False
            has_unreviewed = False
            
            for conv in conversations:
                for m in conv.get('messages', []):
                    # 1. Grab the timestamp
                    m_timestamp = m.get('timestamp', '')
                    
                    # 2. Split at the 'T' to get only "2026-02-21"
                    m_date = m_timestamp.split('T')[0] if 'T' in m_timestamp else ""

                    # 3. Compare to the current calendar column
                    if m_date == d_key:
                        msgs_for_day.append(m)
                        
                        # --- RISK & REVIEW LOGIC ---
                        txt = m.get('text', '').lower()
                        if any(word in txt for word in ['overwhelmed', 'stop', 'die', 'hurt']):
                            has_risky = True
                        if m.get('speaker') == 'Participant':
                            has_unreviewed = True 

            # 4. Save to user_row
            user_row['dates'][d_key] = {
                'count': len(msgs_for_day),
                'has_risky': has_risky,
                'has_unreviewed': has_unreviewed,
                'phone_count': 0, 
                'email_count': 0,
                'text_count': 0
            }
            
        dashboard_data.append(user_row)

    # E. Last Sync Time (Optional)
    last_sync = SyncLog.query.order_by(SyncLog.created_at.desc()).first()

    return render_template('overall_calendar.html',
                         view=view,
                         dashboard_data=dashboard_data,
                         date_range=date_range,
                         start_date=start_date,
                         end_date=end_date,
                         last_sync=last_sync,
                         projects=projects,
                         project_filter=project_filter,
                         ra_filter=ra_filter,
                         risk_filter=risk_filter,
                         attention_filter=attention_filter,
                         research_assistants=research_assistants,
                         attention_count=attention_count)



@app.route('/api/sync', methods=['POST'])
@login_required
def sync():
    """Trigger a data sync from Firebase"""
    try:
        result = sync_service.full_sync()
        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Sync completed. Users: {result['users_synced']}, Messages: {result['messages_synced']}",
                'data': result
            })
        else:
            return jsonify({'success': False, 'message': f"Sync failed: {result.get('error')}"}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error: {str(e)}"}), 500


@app.route('/api/messages/<firebase_id>/<date_str>', methods=['GET'])
@login_required
def get_messages_for_date(firebase_id, date_str):
    """Get messages for a specific user and date"""
    print(f"\nMESSAGE REQUEST RECEIVED!")
    print(f"Target User: {firebase_id}")
    print(f"Target Date: {date_str}")
    try:
        all_users = fetch_all_participants()
        # all_users = User.query.all()
        print(f"DEBUG: I see {len(all_users)} users in the DB.")
        print(f"DEBUG: Looking for ID: [{firebase_id}]")
        
        user_data = next((u for u in all_users if str(u.get('user_id')) == str(firebase_id)), None)
        #user = User.query.filter_by(firebase_id=firebase_id).first()

        if not user_data:
            print(f"DEBUG: Could not find {firebase_id} in the participant list.")
            return jsonify({'success': False, 'message': f'User {firebase_id} not found'}), 404
    
        
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        """
        date_start_utc, date_end_utc = date_to_utc_range(date)

        messages = Message.query.filter(
            and_(
                Message.user_id == user.id,
                Message.timestamp >= date_start_utc,
                Message.timestamp <= date_end_utc
            )
        ).order_by(Message.timestamp.asc()).all()

        conversation_ids = set(msg.conversation_id for msg in messages if msg.conversation_id)
        conversations = {}
        if conversation_ids:
            for conv in Conversation.query.filter(Conversation.id.in_(conversation_ids)).all():
                conversations[conv.id] = {
                    'id': conv.id,
                    'firebase_convo_id': conv.firebase_convo_id,
                    'prompt': conv.prompt
                }

        messages_data = []
        for msg in messages:
            timestamp_et = msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
            conv_info = conversations.get(msg.conversation_id, {})
            messages_data.append({
                'id': msg.id,
                'text': msg.text,
                'speaker': msg.speaker,
                'timestamp': timestamp_et.strftime('%I:%M %p'),
                'is_risky': msg.is_risky,
                'is_reviewed': msg.is_reviewed,
                'conversation_prompt': conv_info.get('prompt', '')
            })

        return jsonify({
            'success': True,
            'messages': messages_data,
            'user': {'firebase_id': user.firebase_id, 'redcap_id': user.redcap_id},
            'date': date_str
        })
        """

        messages_data = []
        
        # Loop through conversations in the JSON/Dict object
        i = 1
        for conv in user_data.get('conversations', []):
            #c_id = conv.get('id') or conv.get('conversation_id')
            c_id = i
            i += 1
            current_prompt = conv.get('prompt', 'New Conversation')

            for m in conv.get('messages', []):
                m_timestamp = m.get('timestamp', '')
                # Convert string to a real datetime object
                dt_obj = datetime.fromisoformat(m_timestamp)
                
                # Extract just the date (2026-02-21)
                m_date = dt_obj.date().isoformat() 
                
                # Format the time beautifully (05:50 PM)
                m_time = dt_obj.strftime('%I:%M %p')

                text = m.get('text', '')
                is_risky = any(word in text.lower() for word in ['overwhelmed', 'stop', 'die', 'hurt', 'suicide', 'harm'])

                if m_date == date_str:
                    # Format for the frontend
                    messages_data.append({
                        'prompt': current_prompt,
                        'conversation_id': c_id,
                        'id': m.get('id'),
                        'speaker': m.get('speaker'),
                        'text': m.get('text'),
                        'timestamp': m_time,
                        'is_risky': is_risky,
                        'is_reviewed': m.get('is_reviewed', False)
                    })

        return jsonify({
            'success': True,
            'messages': messages_data,
            'user': {'redcap_id': user_data.get('redcap_id'), 'identifier': user_data.get('identifier')},
            'date': date_str
        })

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/<int:message_id>/mark-reviewed', methods=['POST'])
@login_required
def mark_message_reviewed(message_id):
    try:
        message = Message.query.get_or_404(message_id)
        message.is_reviewed = True
        message.reviewed_by_id = current_user.id
        message.reviewed_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True, 'message': 'Message marked as reviewed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/messages/date/<firebase_id>/<date_str>/mark-reviewed', methods=['POST'])
@login_required
def mark_date_reviewed(firebase_id, date_str):
    try:
        user = User.query.filter_by(firebase_id=firebase_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_start_utc, date_end_utc = date_to_utc_range(date)

        messages = Message.query.filter(
            and_(
                Message.user_id == user.id,
                Message.timestamp >= date_start_utc,
                Message.timestamp <= date_end_utc
            )
        ).all()

        for msg in messages:
            msg.is_reviewed = True
            msg.reviewed_by_id = current_user.id
            msg.reviewed_at = datetime.utcnow()

        db.session.commit()
        return jsonify({'success': True, 'message': 'Messages marked as reviewed'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# REPLACE the existing user_detail route in your app.py with this fixed version

# REPLACE the user_detail route in your app.py with this CORRECTED version

# ===================================================================
# FINAL FIXED VERSION - Replace your user_detail route with this
# ===================================================================

# NUCLEAR OPTION - If Jinja2 is converting your objects to dicts, 
# let's do it ourselves CORRECTLY

# Replace your entire conversations processing with this version that 
# creates plain dicts instead of custom objects:

@app.route('/user/<firebase_id>')
@login_required
def user_detail(firebase_id):
    """
    User detail page - processes mock API data into the format expected by the template
    """

    # --- 1. FETCH DATA FROM MOCK API ---
    try:
        all_users = fetch_all_participants()
    except Exception as e:
        print(f"API Error: {e}")
        all_users = []
    
    # Find the user
    user_data = next((u for u in all_users if str(u.get('user_id')) == str(firebase_id)), None)
    #user_data = next((u for u in all_users if u['user_id'] == firebase_id), None)
    
    if not user_data:
        flash(f"User {firebase_id} not found.", "warning")
        return redirect(url_for('dashboard'))

    # --- 2. PROCESS CONVERSATIONS AS PLAIN DICTS ---
    conversations = []
    raw_conversations = user_data.get('conversations', [])
    
    for idx, conv in enumerate(raw_conversations):
        processed_messages = []
        
        conv_base_time = datetime.now(et_tz) - timedelta(days=idx)

        for msg_idx, msg in enumerate(conv.get('messages', [])):
            # 1. Determine the correct time for this specific message
            msg_time = datetime.fromisoformat(msg['timestamp'])
            
            text = msg.get('text', '')
            is_risky = any(word in text.lower() for word in ['overwhelmed', 'stop', 'die', 'hurt', 'suicide', 'harm'])
            
            # 2. Build the dictionary
            msg_dict = {
                'text': text,
                'timestamp': msg_time,
                'timestamp_et': msg_time,
                'is_risky': is_risky,
                'speaker': msg.get('speaker', 'Participant')
            }
            processed_messages.append(msg_dict)

        # SECOND: Sort the messages for this conversation chronologically
        processed_messages.sort(key=lambda x: x['timestamp'])

        # THIRD: Now we can safely identify the "last" activity
        if processed_messages:
            last_activity = processed_messages[-1]['timestamp']
        else:
            last_activity = conv_base_time
        
        # Determine trigger type and completion
        trigger_type = conv.get('initiated_by', 'user_initiated')
        if trigger_type == 'bot':
            trigger_type = 'passive_sensing'
        
        # Calculate completion percentage
        msg_count = len(processed_messages)
        if trigger_type in ['passive_sensing', 'bot']:
            completion_pct = min(100, int((msg_count / 4) * 100))
        else:
            completion_pct = 100
        
        # Check if any message is risky
        has_risk = any(msg['is_risky'] for msg in processed_messages)
        
        # Create conversation DICT
        conv_dict = {
            'id': idx + 1,
            'prompt': conv.get('prompt', 'General Conversation'),
            'trigger_type': trigger_type,
            'trigger_display': 'Bot Nudge' if trigger_type in ['passive_sensing', 'bot'] else 'User Initiated',
            'messages': processed_messages,
            'last_activity_et': last_activity,
            'completion_pct': completion_pct,
            'has_risk': has_risk,
            'status': conv.get('status', 'completed')
        }
        
        conversations.append(conv_dict)
        print(f"DEBUG: conv_dict has {len(conv_dict['messages'])} messages")
        if conv_dict['messages']:
            print(f"DEBUG: First message keys: {conv_dict['messages'][0].keys()}")
            print(f"DEBUG: First message has timestamp: {'timestamp' in conv_dict['messages'][0]}")
    
    # Sort by most recent first
    conversations.sort(key=lambda x: x['last_activity_et'], reverse=True)

    # --- 3. CALCULATE USER STATS ---
    total_msgs = sum(len(c['messages']) for c in conversations)
    last_msg_date = conversations[0]['last_activity_et'] if conversations else None
    
    # Count days with activity (last 30 days)
    days_with_activity = 0
    if conversations:
        unique_dates = set()
        for conv in conversations:
            for msg in conv['messages']:
                unique_dates.add(msg['timestamp_et'].date())
        days_with_activity = len(unique_dates)

    # Calculate average conversation completion
    total_pct = 0
    total_convs = 0
    for conv in conversations:
        total_convs += 1
        total_pct += conv['completion_pct'] 

    if conversations:
        conversation_completion = round(total_pct / len(conversations))
    else:
        conversation_completion = 0
    
    user_stats = {
        'last_message_date': last_msg_date,
        'total_messages': total_msgs,
        'days_in_study': user_data.get('days_in_study', 0),
        'days_with_activity': days_with_activity,
        'total_conversations': total_convs,
        'conversation_completion': conversation_completion
    }

    # --- 4. ADD COMPATIBILITY FIELDS ---
    user_data['firebase_id'] = user_data['user_id']
    user_data['is_active'] = not user_data.get('dropped', False)
    user_data['id'] = user_data.get('redcap_id', firebase_id)

    return render_template('user_detail.html', 
                           user=user_data, 
                           user_stats=user_stats,
                           conversations=conversations)



@app.route('/admin/users')
@login_required
def admin_users():
    pending_admins = Admin.query.filter_by(is_approved=False, is_active=True).all()
    rejected_admins = Admin.query.filter_by(is_approved=False, is_active=False).all()
    active_admins = Admin.query.filter_by(is_approved=True, is_active=True).all()
    deactivated_admins = Admin.query.filter_by(is_approved=True, is_active=False).all()

    return render_template('admin_users.html',
                         pending_admins=pending_admins,
                         rejected_admins=rejected_admins,
                         active_admins=active_admins,
                         deactivated_admins=deactivated_admins)


@app.route('/admin/users/<int:admin_id>/toggle', methods=['POST'])
@login_required
def toggle_admin_status(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot disable your own account'}), 400
    admin.is_active = not admin.is_active
    db.session.commit()
    status = 'activated' if admin.is_active else 'deactivated'
    return jsonify({'success': True, 'message': f'Admin {admin.username} has been {status}'})


@app.route('/admin/users/<int:admin_id>/approve', methods=['POST'])
@login_required
def approve_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    if admin.is_approved:
        return jsonify({'success': False, 'message': 'Admin is already approved'}), 400
    admin.is_approved = True
    admin.is_active = True
    db.session.commit()
    return jsonify({'success': True, 'message': f'Admin {admin.username} has been approved'})


@app.route('/admin/users/<int:admin_id>/reject', methods=['POST'])
@login_required
def reject_admin(admin_id):
    admin = Admin.query.get_or_404(admin_id)
    if admin.is_approved:
        return jsonify({'success': False, 'message': 'Cannot reject an already approved admin'}), 400
    if admin.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot reject your own account'}), 400
    admin.is_active = False
    db.session.commit()
    return jsonify({'success': True, 'message': f'Registration for {admin.username} has been rejected'})


@app.route('/settings')
@login_required
def settings():
    last_sync = SyncLog.query.order_by(SyncLog.created_at.desc()).first()
    settings_data = {
        'ip_prefix': Config.IP_PREFIX_ALLOWED,
        'redcap_configured': bool(Config.get_all_projects()),
        'twilio_configured': bool(Config.TWILIO_ACCOUNT_SID and Config.TWILIO_AUTH_TOKEN),
        'firebase_configured': bool(Config.FIREBASE_CREDENTIALS_PATH),
        'admin_numbers': Config.TWILIO_ADMIN_NUMBERS,
        'last_sync': last_sync
    }
    return render_template('settings.html', settings=settings_data)


@app.route('/api/test-sms', methods=['POST'])
@login_required
def test_sms():
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        if not phone_number:
            return jsonify({'success': False, 'message': 'Phone number is required'}), 400
        phone_number = phone_number.strip()
        if not phone_number.startswith('+'):
            phone_number = '+1' + phone_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        success, message = twilio_service.send_test_message(phone_number)
        return jsonify({'success': success, 'message': message}), 200 if success else 500
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error sending test SMS: {str(e)}"}), 500


@app.route('/api/notes/<participant_id>', methods=['GET'])
@login_required
def get_notes(participant_id):
    try:
        notes = Notes.query.filter_by(participant_id=participant_id).order_by(Notes.datetime.desc()).all()
        notes_data = []
        for note in notes:
            admin_username = None
            if note.admin_id:
                admin = Admin.query.get(note.admin_id)
                if admin:
                    admin_username = admin.username
            notes_data.append({
                'note_id': note.note_id,
                'admin_id': note.admin_id,
                'admin_username': admin_username,
                'participant_id': note.participant_id,
                'note_type': note.note_type,
                'note_reason': note.note_reason,
                'datetime': note.datetime,
                'duration': note.duration,
                'note': note.note
            })
        return jsonify({'success': True, 'notes': notes_data})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error fetching notes: {str(e)}"}), 500


@app.route('/api/notes', methods=['POST'])
@login_required
def create_note():
    try:
        data = request.get_json()
        if not data.get('participant_id'):
            return jsonify({'success': False, 'message': 'participant_id is required'}), 400
        note = Notes(
            admin_id=current_user.id,
            participant_id=data.get('participant_id'),
            note_type=data.get('note_type'),
            note_reason=data.get('note_reason'),
            datetime=data.get('datetime'),
            duration=data.get('duration'),
            note=data.get('note')
        )
        db.session.add(note)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Note created successfully', 'note_id': note.note_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Error creating note: {str(e)}"}), 500


@app.route('/all-notes')
@login_required
def all_notes():
    return render_template('all_notes.html')


@app.route('/api/notes/all', methods=['GET'])
@login_required
def get_all_notes():
    try:
        notes = Notes.query.order_by(Notes.datetime.desc()).all()
        notes_data = []
        for note in notes:
            admin_username = None
            if note.admin_id:
                admin = Admin.query.get(note.admin_id)
                if admin:
                    admin_username = admin.username
            participant_identifier = None
            user = User.query.filter_by(redcap_id=note.participant_id).first()
            if user:
                participant_identifier = user.identifier
            notes_data.append({
                'note_id': note.note_id,
                'admin_id': note.admin_id,
                'admin_username': admin_username,
                'participant_id': note.participant_id,
                'participant_identifier': participant_identifier,
                'note_type': note.note_type,
                'note_reason': note.note_reason,
                'datetime': note.datetime,
                'duration': note.duration,
                'note': note.note
            })
        return jsonify({'success': True, 'notes': notes_data})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error fetching notes: {str(e)}"}), 500


@app.route('/api/email/templates', methods=['GET'])
@login_required
def get_email_templates():
    try:
        templates = email_service.get_email_templates()
        return jsonify({'success': True, 'templates': templates, 'from_address': email_service.get_from_address()})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error fetching templates: {str(e)}"}), 500


@app.route('/api/email/participant/<participant_id>', methods=['GET'])
@login_required
def get_participant_email_info(participant_id):
    try:
        user = User.query.filter_by(redcap_id=participant_id).first()
        if not user:
            return jsonify({'success': False, 'message': f'Participant {participant_id} not found'}), 404

        participant_data = {
            'record_id': participant_id,
            'first_name': user.identifier or '',
            'email': '',
            'username': '',
            'password': '',
            'research_assistant': user.research_assistant or ''
        }

        project_config = Config.get_project_by_id(user.project_id) if user.project_id else None
        if not project_config:
            projects = Config.get_all_projects()
            if projects:
                project_config = projects[0]

        if project_config and project_config.api_url and project_config.api_token:
            try:
                fields = ['record_id', 'first_name', 'email', 'username', 'password']
                if project_config.ra_field:
                    fields.append(project_config.ra_field)
                
                data = {
                    'token': project_config.api_token, 'content': 'record', 'format': 'json', 
                    'type': 'flat', 'records': participant_id, 'fields': ','.join(fields), 'returnFormat': 'json'
                }
                if project_config.event_name:
                    data['events'] = project_config.event_name

                response = requests.post(project_config.api_url, data=data, timeout=30)
                response.raise_for_status()
                redcap_data = response.json()

                if redcap_data and len(redcap_data) > 0:
                    entry = redcap_data[0]
                    if entry.get('first_name', '').strip(): participant_data['first_name'] = entry.get('first_name', '').strip()
                    if entry.get('email', '').strip(): participant_data['email'] = entry.get('email', '').strip()
                    if entry.get('username', '').strip(): participant_data['username'] = entry.get('username', '').strip()
                    if entry.get('password', '').strip(): participant_data['password'] = entry.get('password', '').strip()
                    if project_config.ra_field and entry.get(project_config.ra_field, '').strip():
                        participant_data['research_assistant'] = entry.get(project_config.ra_field, '').strip()

                if project_config.email_event and not participant_data['email']:
                    email_data = {
                        'token': project_config.api_token, 'content': 'record', 'format': 'json',
                        'type': 'flat', 'records': participant_id, 'fields': 'record_id,email',
                        'events': project_config.email_event.strip(), 'returnFormat': 'json'
                    }
                    try:
                        email_response = requests.post(project_config.api_url, data=email_data, timeout=30)
                        email_response.raise_for_status()
                        email_records = email_response.json()
                        if email_records and len(email_records) > 0:
                            email_val = email_records[0].get('email', '').strip()
                            if email_val: participant_data['email'] = email_val
                    except Exception:
                        pass
            except Exception:
                pass

        last_email = Notes.query.filter(Notes.participant_id == participant_id, Notes.note_type == 'Email').order_by(Notes.datetime.desc()).first()
        participant_data['last_email_sent'] = last_email.datetime if last_email else None
        participant_data['last_email_by'] = None
        if last_email and last_email.admin_id:
            admin = Admin.query.get(last_email.admin_id)
            if admin: participant_data['last_email_by'] = admin.username

        return jsonify({'success': True, 'participant': participant_data})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error: {str(e)}"}), 500


@app.route('/api/email/preview', methods=['POST'])
@login_required
def preview_email():
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        first_name = data.get('first_name', 'Participant')
        ra_first_name = data.get('ra_first_name', 'The Research Team')
        username = data.get('username', '')
        password = data.get('password', '')
        custom_message = data.get('custom_message', '')

        if ra_first_name and ' ' in ra_first_name:
            ra_first_name = ra_first_name.split()[0]
        if first_name:
            first_name = first_name.strip()
            if first_name:
                first_name = first_name[0].upper() + first_name[1:] if len(first_name) > 1 else first_name.upper()

        body = email_service.format_email_body(template_id, first_name, ra_first_name, username=username, password=password, custom_message=custom_message)
        if not body:
            return jsonify({'success': False, 'message': 'Invalid template'}), 400
        
        subject = email_service.get_template_subject(template_id)
        return jsonify({'success': True, 'subject': subject, 'body': body, 'from_address': email_service.get_from_address()})
    except Exception as e:
        return jsonify({'success': False, 'message': f"Error: {str(e)}"}), 500


@app.route('/api/email/send', methods=['POST'])
@login_required
def send_manual_email():
    try:
        data = request.get_json()
        participant_id = data.get('participant_id')
        to_email = data.get('to_email')
        subject = data.get('subject')
        body = data.get('body')
        template_id = data.get('template_id', 'custom')

        if not participant_id or not to_email or not subject or not body:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        success, message = email_service.send_email(to_email, subject, body)
        if success:
            logged_body = body
            password = data.get('password')
            if password:
                logged_body = body.replace(password, '********')

            template_name = email_service.EMAIL_TEMPLATES.get(template_id, {}).get('name', 'Manual')
            note_reason = f'Manual - {template_name}'
            note = Notes(
                admin_id=current_user.id, participant_id=str(participant_id), note_type='Email',
                note_reason=note_reason, datetime=datetime.now(et_tz).strftime('%Y-%m-%dT%H:%M'),
                duration='N/A', note=f"Subject: {subject}\n\n{logged_body}"
            )
            db.session.add(note)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Email sent and logged'})
        else:
            return jsonify({'success': False, 'message': message}), 500
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Error: {str(e)}"}), 500


@app.route('/api/email/last-communication/<participant_id>', methods=['GET'])
@login_required
def get_last_communication(participant_id):
    try:
        last_email = Notes.query.filter(Notes.participant_id == participant_id, Notes.note_type == 'Email').order_by(Notes.datetime.desc()).first()
        last_any = Notes.query.filter(Notes.participant_id == participant_id).order_by(Notes.datetime.desc()).first()
        
        result = {'last_email': None, 'last_communication': None}
        if last_email:
            admin = Admin.query.get(last_email.admin_id) if last_email.admin_id else None
            result['last_email'] = {'datetime': last_email.datetime, 'reason': last_email.note_reason, 'by': admin.username if admin else 'System'}
        if last_any:
            admin = Admin.query.get(last_any.admin_id) if last_any.admin_id else None
            result['last_communication'] = {'datetime': last_any.datetime, 'type': last_any.note_type, 'reason': last_any.note_reason, 'by': admin.username if admin else 'System'}
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.errorhandler(403)
def forbidden(e):
    ip_address = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return render_template('403.html', ip_address=ip_address), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


def init_db():
    with app.app_context():
        db.create_all()
        print("Database initialized successfully")

# ADD this new route to your app.py to serve passive data to the charts

@app.route('/api/participant/<user_id>/passive-data')
@login_required
def get_participant_passive_data(user_id):
    """
    Serve passive sensor data from mock API to the frontend charts
    """
    from datetime import datetime
    
    metric = request.args.get('metric', 'steps')
    time_range = request.args.get('range', '30d')
    
    print(f"Metric: {metric}, Range: {time_range}")
    
    # Parse time range
    if time_range == '3d':
        days = 3
    elif time_range == '7d':
        days = 7
    else:
        days = 30
    
    try:
        # Fetch from mock API
        response = requests.get('http://127.0.0.1:5001/api/v1/all_users', 
                               headers={'X-API-KEY': 'sk_everdash_test_123'},
                               timeout=5)
        
        if response.status_code != 200:
            print(f"ERROR: Mock API returned {response.status_code}")
            return jsonify({'error': 'Failed to fetch data'}), 500
        
        data = response.json()
        user = next((p for p in data['participants'] if p['user_id'] == user_id), None)
        
        if not user:
            print(f"ERROR: User {user_id} not found")
            return jsonify({'error': 'User not found'}), 404
        
        print(f"✅ User found: {user.get('identifier', 'Unknown')}")
        
        history = user.get('passive_data_history', {})
        dates = sorted(history.keys())[-days:]
        
        labels = []
        values = []
        events = []
        
        print(f"Processing {len(dates)} days of data...")
        
        for date_str in dates:
            day_data = history[date_str]
            q = day_data.get('quantitative', {})
            
            # Format label
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            labels.append(date_obj.strftime('%m/%d'))
            
            # Extract value based on metric
            if metric == 'steps':
                val = q.get('watch_activity', {}).get('steps', 0)
            elif metric == 'heart_rate_avg':
                val = q.get('watch_heart_rate', {}).get('avg_bpm', 0)
            elif metric == 'sleep_minutes':
                val = q.get('watch_sleep', {}).get('minutes_total', 0)
            elif metric == 'screen_time_minutes':
                val = q.get('phone_screen_time', {}).get('minutes', 0)
            elif metric == 'battery_drain':
                battery = q.get('phone_battery', [])
                val = (100 - min(battery)) if battery else 0
            elif metric == 'canvas_activity':
                val = day_data.get('campus', {}).get('canvas_logs', {}).get('files_viewed', 0)
            elif metric == 'library_hours':
                locations = day_data.get('campus', {}).get('wireless_locations', [])
                library_mins = sum(loc['duration_mins'] for loc in locations if 'library' in loc.get('building', '').lower())
                val = round(library_mins / 60, 1)
            else:
                val = 0
            
            values.append(val)
        
        print(f"✅ Processed {len(values)} data points")
        print(f"Date range: {labels[0]} to {labels[-1]}")
        
        # ========================================
        # GENERATE EVENTS FOR CHART OVERLAY
        # ========================================
        
        print(f"\n========== EVENT GENERATION ==========")
        
        conversations = user.get('conversations', [])
        print(f"Found {len(conversations)} conversations in user data")
        
        if len(conversations) == 0:
            print("⚠️  WARNING: No conversations found!")
            print(f"User keys available: {list(user.keys())}")
        
        for idx, conv in enumerate(conversations):
            print(f"\n--- Conversation {idx + 1} ---")
            
            messages = conv.get('messages', [])
            print(f"  Messages: {len(messages)}")
            
            if not messages:
                print("  ❌ SKIP: No messages")
                continue
            
            first_msg = messages[0]
            
            if 'timestamp' not in first_msg:
                print("  ❌ SKIP: No timestamp")
                continue
            
            try:
                conv_time = datetime.fromisoformat(first_msg['timestamp'])
                conv_date_str = conv_time.strftime('%Y-%m-%d')  # Full date format
                conv_date_label = conv_time.strftime('%m/%d')   # Chart label format
                
                print(f"  Conversation date: {conv_date_label} ({conv_date_str})")
                print(f"  Chart range: {labels[0]} to {labels[-1]}")
                
                # NEW LOGIC: If conversation date not in chart range, check if we can add it
                if conv_date_label not in labels:
                    # Check if this date exists in the passive data history
                    if conv_date_str in history:
                        print(f"  ℹ️  Date not in chart range, but exists in history - extending range")
                        
                        # Add this date to the chart
                        day_data = history[conv_date_str]
                        q = day_data.get('quantitative', {})
                        
                        # Extract the metric value
                        if metric == 'steps':
                            val = q.get('watch_activity', {}).get('steps', 0)
                        elif metric == 'heart_rate_avg':
                            val = q.get('watch_heart_rate', {}).get('avg_bpm', 0)
                        elif metric == 'sleep_minutes':
                            val = q.get('watch_sleep', {}).get('minutes_total', 0)
                        elif metric == 'screen_time_minutes':
                            val = q.get('phone_screen_time', {}).get('minutes', 0)
                        elif metric == 'battery_drain':
                            battery = q.get('phone_battery', [])
                            val = (100 - min(battery)) if battery else 0
                        elif metric == 'canvas_activity':
                            val = day_data.get('campus', {}).get('canvas_logs', {}).get('files_viewed', 0)
                        elif metric == 'library_hours':
                            locations = day_data.get('campus', {}).get('wireless_locations', [])
                            library_mins = sum(loc['duration_mins'] for loc in locations if 'library' in loc.get('building', '').lower())
                            val = round(library_mins / 60, 1)
                        else:
                            val = 0
                        
                        # Add to chart data
                        labels.append(conv_date_label)
                        values.append(val)
                        
                        print(f"  ✅ Extended chart to include {conv_date_label} with value {val}")
                    else:
                        print(f"  ❌ SKIP: {conv_date_label} not in passive history")
                        continue

                    
                print(f"  ✅ Date {conv_date_label} IS in range!")
                
                day_index = labels.index(conv_date_label)
                metric_value = values[day_index]
                
                initiated_by = conv.get('initiated_by', 'user')
                if initiated_by == 'bot':
                    event_type = 'bot'
                    event_details = 'Bot check-in conversation'
                else:
                    event_type = 'user'
                    event_details = 'User initiated conversation'
                
                time_str = conv_time.strftime('%I:%M %p')
                event_details = f"{event_details} at {time_str}"
                
                event = {
                    'x': conv_date_label,
                    'y': metric_value,
                    'type': event_type,
                    'details': event_details
                }
                
                events.append(event)
                print(f"  ✅ SUCCESS: Created event at ({conv_date_label}, {metric_value})")
                
            except Exception as e:
                print(f"  ❌ ERROR: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\n========== FINAL RESULT ==========")
        print(f"Total events created: {len(events)}")
        if events:
            for e in events:
                print(f"  • {e['type']} on {e['x']} at y={e['y']}: {e['details']}")
        print(f"==================================\n")
        
        return jsonify({
            'metric': metric,
            'labels': labels,
            'values': values,
            'events': events
        })
        
    except Exception as e:
        print(f"❌ EXCEPTION in passive data endpoint: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


    

@app.route('/api/sensor_data')
@login_required
def get_sensor_data_api():
    """
    The Chart.js in user_detail.html calls this to get the numbers.
    """
    # 1. Get parameters from the URL
    user_id = request.args.get('user_id') # e.g. 'user_001'
    metric = request.args.get('metric', 'steps')
    days = int(request.args.get('days', 30))
    
    # 2. Calculate dates
    end_date = datetime.now(et_tz).date()
    start_date = end_date - timedelta(days=days)
    
    # 3. FETCH FROM YOUR NEW SERVICE
    # This calls the function that you tested in debug_data.py
    values = fetch_sensor_data_external(user_id, metric, start_date, end_date, "sk_everdash_test_123")
    
    # 4. Return the list of numbers so the chart can draw
    return jsonify({'labels': [], 'values': values})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5002)




