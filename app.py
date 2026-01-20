from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Admin, User, Message, Conversation, SyncLog, Notes
from config import Config
from middleware import require_ip_whitelist, ip_and_admin_required
from services.sync_service import sync_service
from services.twilio_service import twilio_service
import services.email_service as email_service
from datetime import datetime, timedelta
import pytz
import requests
from sqlalchemy import func, and_

app = Flask(__name__)
app.config.from_object(Config)

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


@login_manager.user_loader
def load_user(user_id):
    return Admin.query.get(int(user_id))


@app.before_request
def enforce_ip_whitelist():
    """Enforce IP whitelist on all routes"""
    # Skip IP check for static files
    if request.path.startswith('/static/'):
        return

    # Get the real IP address
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()
    else:
        ip_address = request.remote_addr

    allowed_prefix = Config.IP_PREFIX_ALLOWED

    # Check if IP starts with allowed prefix
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

        # Validate registration key
        if registration_key != Config.REGISTRATION_KEY:
            flash('Invalid registration key', 'error')
            return redirect(url_for('register'))

        # Validate passwords match
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('register'))

        # Check if username exists
        if Admin.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        # Check if email exists
        if Admin.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))

        # Create new admin
        admin = Admin(username=username, email=email)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        flash('Registration successful! Your account is pending admin approval. You will be notified once approved.', 'info')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard showing user conversations in a grid - multi-project support"""
    # Get date range from query parameters (default to last 7 days)
    end_date_str = request.args.get('end_date')
    start_date_str = request.args.get('start_date')
    project_filter = request.args.get('project', 'all')
    ra_filter = request.args.get('ra', 'all')
    risk_filter = request.args.get('risk', 'all')  # 'all', 'risky', 'not_risky'
    attention_filter = request.args.get('attention', 'all')  # 'all', 'needs_attention'

    # Default to last 7 days if not specified
    if not end_date_str:
        end_date = datetime.now(et_tz).date()
    else:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    if not start_date_str:
        start_date = end_date - timedelta(days=6)  # 7 days total
    else:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

    # Generate list of dates for columns
    date_range = []
    current_date = start_date
    while current_date <= end_date:
        date_range.append(current_date)
        current_date += timedelta(days=1)

    # Get all configured projects for filter dropdown
    projects = Config.get_all_projects()

    # Get active users with optional project filter
    users_query = User.query.filter_by(is_active=True)
    if project_filter != 'all':
        users_query = users_query.filter_by(project_id=project_filter)
    if ra_filter != 'all':
        users_query = users_query.filter_by(research_assistant=ra_filter)
    users = users_query.order_by(User.firebase_id).all()

    # Get all unique research assistants for filter dropdown
    all_ras = db.session.query(User.research_assistant).filter(
        User.is_active == True,
        User.research_assistant.isnot(None),
        User.research_assistant != ''
    ).distinct().order_by(User.research_assistant).all()
    research_assistants = [ra[0] for ra in all_ras if ra[0]]

    # Collect all unique custom field labels across all projects
    all_custom_field_labels = []
    for project in projects:
        for cf in project.custom_display_fields:
            label = cf.get('label', cf.get('field'))
            if label and label not in all_custom_field_labels:
                all_custom_field_labels.append(label)

    # Pre-fetch all notes for participants in the date range to avoid N+1 queries
    # Get all redcap_ids for current users
    user_redcap_ids = [u.redcap_id for u in users if u.redcap_id]

    # Convert date range to string format for comparison with notes datetime
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')  # Include end date

    # Fetch all notes in date range for these participants
    notes_in_range = []
    if user_redcap_ids:
        notes_in_range = Notes.query.filter(
            Notes.participant_id.in_(user_redcap_ids),
            Notes.datetime >= start_date_str,
            Notes.datetime < end_date_str
        ).all()

    # Organize notes by participant_id and date
    notes_by_participant_date = {}
    for note in notes_in_range:
        if not note.datetime:
            continue
        # Extract date from datetime string (format: YYYY-MM-DDTHH:MM or YYYY-MM-DD HH:MM)
        note_date = note.datetime[:10]  # Get YYYY-MM-DD part
        key = (note.participant_id, note_date)
        if key not in notes_by_participant_date:
            notes_by_participant_date[key] = {'phone': False, 'email': False, 'text': False}

        # Check note type
        note_type = (note.note_type or '').lower()
        if 'phone' in note_type or 'call' in note_type:
            notes_by_participant_date[key]['phone'] = True
        elif 'email' in note_type:
            notes_by_participant_date[key]['email'] = True
        elif 'text' in note_type or 'sms' in note_type:
            notes_by_participant_date[key]['text'] = True

    # Build dashboard data structure
    dashboard_data = []

    for user in users:
        # Get project name for display
        project_name = '-'
        if user.project_id:
            project_config = Config.get_project_by_id(user.project_id)
            if project_config:
                project_name = project_config.name

        # Get custom field values for this user
        custom_field_values = {}
        for cf in user.custom_fields:
            custom_field_values[cf.field_label or cf.field_name] = cf.field_value or '-'

        # Use redcap_firebase_id for display if available, otherwise fall back to firebase_id
        display_firebase_id = user.redcap_firebase_id if user.redcap_firebase_id else user.firebase_id

        user_row = {
            'firebase_id': user.firebase_id,  # Internal ID for links/lookups
            'display_firebase_id': display_firebase_id,  # Firebase ID from REDCap for display
            'redcap_id': user.redcap_id or '-',
            'identifier': user.identifier or '-',
            'research_assistant': user.research_assistant or '-',
            'project_name': project_name,
            'project_id': user.project_id or '-',
            'study_start_date': user.study_start_date.strftime('%Y-%m-%d') if user.study_start_date else '-',
            'study_end_date': user.study_end_date.strftime('%Y-%m-%d') if user.study_end_date else '-',
            'dropped': user.dropped or False,
            'dropped_surveys': user.dropped_surveys or False,
            'custom_fields': custom_field_values,
            'dates': {}
        }

        # For each date, get message count and check for high risk scores
        for date in date_range:
            date_start_utc, date_end_utc = date_to_utc_range(date)

            # Query messages for this user and date
            messages = Message.query.filter(
                and_(
                    Message.user_id == user.id,
                    Message.timestamp >= date_start_utc,
                    Message.timestamp <= date_end_utc
                )
            ).all()

            message_count = len(messages)
            has_risky = any(msg.is_risky for msg in messages)
            has_unreviewed = any(not msg.is_reviewed for msg in messages)

            # Get communication data for this date
            date_key = date.isoformat()
            comm_key = (user.redcap_id, date_key) if user.redcap_id else None
            comm_data = notes_by_participant_date.get(comm_key, {'phone': False, 'email': False, 'text': False})

            user_row['dates'][date_key] = {
                'count': message_count,
                'has_risky': has_risky,
                'has_unreviewed': has_unreviewed,
                'has_phone': comm_data['phone'],
                'has_email': comm_data['email'],
                'has_text': comm_data['text']
            }

        # Check if user has any risky messages in the date range
        user_has_risky = any(
            user_row['dates'][d.isoformat()]['has_risky']
            for d in date_range
            if d.isoformat() in user_row['dates']
        )
        user_row['has_any_risky'] = user_has_risky

        # Check if user needs attention (no messages for 2+ consecutive days from most recent, and not dropped)
        needs_attention = False
        if not user.dropped:
            # Check last 2 days (most recent dates in the range)
            recent_dates = sorted(date_range, reverse=True)[:2]
            consecutive_zero_days = 0
            for d in recent_dates:
                date_key = d.isoformat()
                if date_key in user_row['dates'] and user_row['dates'][date_key]['count'] == 0:
                    consecutive_zero_days += 1
                else:
                    break
            needs_attention = consecutive_zero_days >= 2
        user_row['needs_attention'] = needs_attention

        # Calculate utilization category
        # Check total messages ever sent by this user
        total_messages = Message.query.filter_by(user_id=user.id).count()

        # Count days with activity in the date range
        days_with_activity = sum(1 for d in date_range if user_row['dates'].get(d.isoformat(), {}).get('count', 0) > 0)
        total_days = len(date_range)

        # Count consecutive days without activity from most recent
        recent_dates_sorted = sorted(date_range, reverse=True)
        consecutive_inactive_days = 0
        for d in recent_dates_sorted:
            date_key = d.isoformat()
            if user_row['dates'].get(date_key, {}).get('count', 0) == 0:
                consecutive_inactive_days += 1
            else:
                break

        # Determine utilization category
        if total_messages == 0:
            utilization_status = 'never_utilized'
        elif consecutive_inactive_days >= 3:
            utilization_status = 'inactive_3plus'
        elif days_with_activity >= (total_days * 0.5):  # Active at least 50% of days
            utilization_status = 'consistent'
        else:
            utilization_status = 'moderate'  # Some activity but not consistent

        user_row['utilization_status'] = utilization_status
        user_row['total_messages'] = total_messages
        user_row['days_with_activity'] = days_with_activity
        user_row['consecutive_inactive_days'] = consecutive_inactive_days

        dashboard_data.append(user_row)

    # Apply risk filter
    if risk_filter == 'risky':
        dashboard_data = [u for u in dashboard_data if u['has_any_risky']]
    elif risk_filter == 'not_risky':
        dashboard_data = [u for u in dashboard_data if not u['has_any_risky']]

    # Apply attention filter
    if attention_filter == 'needs_attention':
        dashboard_data = [u for u in dashboard_data if u['needs_attention']]

    # Count users needing attention (for display)
    attention_count = sum(1 for u in dashboard_data if u['needs_attention'])

    # Sort: needs attention first, then risky users, then by redcap_id
    dashboard_data.sort(key=lambda x: (not x['needs_attention'], not x['has_any_risky'], x['redcap_id']))

    # Get last sync info
    last_sync = SyncLog.query.order_by(SyncLog.created_at.desc()).first()

    return render_template('dashboard.html',
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
                         attention_count=attention_count,
                         research_assistants=research_assistants,
                         custom_field_labels=all_custom_field_labels)


@app.route('/api/sync', methods=['POST'])
@login_required
def sync():
    """Trigger a data sync from Firebase"""
    try:
        result = sync_service.full_sync()

        if result['success']:
            return jsonify({
                'success': True,
                'message': f"Sync completed successfully. "
                          f"Users: {result['users_synced']}, "
                          f"Conversations: {result['conversations_synced']}, "
                          f"Messages: {result['messages_synced']}, "
                          f"Alerts: {result['alerts_sent']}",
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f"Sync failed: {result.get('error', 'Unknown error')}"
            }), 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error during sync: {str(e)}"
        }), 500


@app.route('/api/messages/<firebase_id>/<date_str>', methods=['GET'])
@login_required
def get_messages_for_date(firebase_id, date_str):
    """Get messages for a specific user and date"""
    try:
        user = User.query.filter_by(firebase_id=firebase_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Parse date
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_start_utc, date_end_utc = date_to_utc_range(date)

        # Query messages for this user and date
        messages = Message.query.filter(
            and_(
                Message.user_id == user.id,
                Message.timestamp >= date_start_utc,
                Message.timestamp <= date_end_utc
            )
        ).order_by(Message.timestamp.asc()).all()

        # Format messages for response
        messages_data = []
        for msg in messages:
            timestamp_et = msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
            messages_data.append({
                'id': msg.id,
                'text': msg.text,
                'timestamp': timestamp_et.strftime('%I:%M %p'),
                'timestamp_full': timestamp_et.strftime('%Y-%m-%d %I:%M:%S %p'),
                'is_risky': msg.is_risky,
                'is_reviewed': msg.is_reviewed
            })

        return jsonify({
            'success': True,
            'messages': messages_data,
            'user': {
                'firebase_id': user.firebase_id,
                'redcap_id': user.redcap_id or '-',
                'identifier': user.identifier or '-',
                'research_assistant': user.research_assistant or '-'
            },
            'date': date_str
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error fetching messages: {str(e)}"
        }), 500


@app.route('/api/messages/<int:message_id>/mark-reviewed', methods=['POST'])
@login_required
def mark_message_reviewed(message_id):
    """Mark a message as reviewed"""
    try:
        message = Message.query.get_or_404(message_id)
        message.is_reviewed = True
        message.reviewed_by_id = current_user.id
        message.reviewed_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Message marked as reviewed'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error marking message as reviewed: {str(e)}"
        }), 500


@app.route('/api/messages/date/<firebase_id>/<date_str>/mark-reviewed', methods=['POST'])
@login_required
def mark_date_reviewed(firebase_id, date_str):
    """Mark all messages for a specific user and date as reviewed"""
    try:
        user = User.query.filter_by(firebase_id=firebase_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        # Parse date
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        date_start_utc, date_end_utc = date_to_utc_range(date)

        # Update all messages for this user and date
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

        return jsonify({
            'success': True,
            'message': f'{len(messages)} message(s) marked as reviewed',
            'count': len(messages)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error marking messages as reviewed: {str(e)}"
        }), 500


@app.route('/user/<firebase_id>')
@login_required
def user_detail(firebase_id):
    """Show detailed conversation view for a specific user"""
    user = User.query.filter_by(firebase_id=firebase_id).first_or_404()

    # Get date range from query parameters
    end_date_str = request.args.get('end_date')
    start_date_str = request.args.get('start_date')

    if end_date_str and start_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        # Convert dates to UTC range for database query
        date_start_utc, _ = date_to_utc_range(start_date)
        _, date_end_utc = date_to_utc_range(end_date)

        # Get messages in date range with conversation info
        messages = Message.query.filter(
            and_(
                Message.user_id == user.id,
                Message.timestamp >= date_start_utc,
                Message.timestamp <= date_end_utc
            )
        ).order_by(Message.timestamp.desc()).all()
    else:
        # Get all messages with conversation info
        messages = Message.query.filter_by(user_id=user.id).order_by(Message.timestamp.desc()).all()
        start_date = None
        end_date = None

    # Convert timestamps to Eastern Time for display and add conversation info
    conversations_dict = {}
    for message in messages:
        message.timestamp_et = message.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
        # Get conversation info if available
        if message.conversation_id:
            if message.conversation_id not in conversations_dict:
                conv = Conversation.query.get(message.conversation_id)
                if conv:
                    conversations_dict[message.conversation_id] = {
                        'id': conv.id,
                        'firebase_convo_id': conv.firebase_convo_id,
                        'prompt': conv.prompt,
                        'timestamp': conv.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz) if conv.timestamp else None
                    }
            message.conversation_info = conversations_dict.get(message.conversation_id)
        else:
            message.conversation_info = None

    # Calculate utilization stats
    total_messages = len(messages)
    total_conversations = len(conversations_dict)

    # Calculate days with activity
    message_dates = set()
    for msg in messages:
        message_dates.add(msg.timestamp_et.date())
    days_with_activity = len(message_dates)

    # Get first and last message dates
    first_message_date = messages[-1].timestamp_et if messages else None
    last_message_date = messages[0].timestamp_et if messages else None

    user_stats = {
        'total_messages': total_messages,
        'total_conversations': total_conversations,
        'days_with_activity': days_with_activity,
        'first_message_date': first_message_date,
        'last_message_date': last_message_date
    }

    return render_template('user_detail.html',
                         user=user,
                         messages=messages,
                         start_date=start_date,
                         end_date=end_date,
                         user_stats=user_stats)


@app.route('/admin/users')
@login_required
def admin_users():
    """Manage admin users"""
    # Separate admins into categories for better management
    pending_admins = Admin.query.filter_by(is_approved=False, is_active=True).order_by(Admin.created_at.desc()).all()
    rejected_admins = Admin.query.filter_by(is_approved=False, is_active=False).order_by(Admin.created_at.desc()).all()
    active_admins = Admin.query.filter_by(is_approved=True, is_active=True).order_by(Admin.created_at.desc()).all()
    deactivated_admins = Admin.query.filter_by(is_approved=True, is_active=False).order_by(Admin.created_at.desc()).all()

    return render_template('admin_users.html',
                         pending_admins=pending_admins,
                         rejected_admins=rejected_admins,
                         active_admins=active_admins,
                         deactivated_admins=deactivated_admins)


@app.route('/admin/users/<int:admin_id>/toggle', methods=['POST'])
@login_required
def toggle_admin_status(admin_id):
    """Toggle admin user active status"""
    admin = Admin.query.get_or_404(admin_id)

    # Don't allow disabling yourself
    if admin.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot disable your own account'}), 400

    admin.is_active = not admin.is_active
    db.session.commit()

    status = 'activated' if admin.is_active else 'deactivated'
    return jsonify({'success': True, 'message': f'Admin {admin.username} has been {status}'})


@app.route('/admin/users/<int:admin_id>/approve', methods=['POST'])
@login_required
def approve_admin(admin_id):
    """Approve a pending admin user"""
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
    """Reject a pending admin user (marks as rejected, keeps record)"""
    admin = Admin.query.get_or_404(admin_id)

    if admin.is_approved:
        return jsonify({'success': False, 'message': 'Cannot reject an already approved admin'}), 400

    if admin.id == current_user.id:
        return jsonify({'success': False, 'message': 'Cannot reject your own account'}), 400

    # Mark as rejected (is_approved=False, is_active=False) instead of deleting
    admin.is_active = False
    db.session.commit()

    return jsonify({'success': True, 'message': f'Registration for {admin.username} has been rejected'})


@app.route('/settings')
@login_required
def settings():
    """Application settings page"""
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
    """Send a test SMS message to verify Twilio configuration"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')

        if not phone_number:
            return jsonify({
                'success': False,
                'message': 'Phone number is required'
            }), 400

        # Basic phone number validation
        phone_number = phone_number.strip()
        if not phone_number.startswith('+'):
            phone_number = '+1' + phone_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')

        success, message = twilio_service.send_test_message(phone_number)

        return jsonify({
            'success': success,
            'message': message
        }), 200 if success else 500

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error sending test SMS: {str(e)}"
        }), 500


@app.route('/api/notes/<participant_id>', methods=['GET'])
@login_required
def get_notes(participant_id):
    """Get all notes for a participant"""
    try:
        notes = Notes.query.filter_by(participant_id=participant_id).order_by(Notes.datetime.desc()).all()

        notes_data = []
        for note in notes:
            # Get admin username if available
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

        return jsonify({
            'success': True,
            'notes': notes_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error fetching notes: {str(e)}"
        }), 500


@app.route('/api/notes', methods=['POST'])
@login_required
def create_note():
    """Create a new note for a participant"""
    try:
        data = request.get_json()

        if not data.get('participant_id'):
            return jsonify({
                'success': False,
                'message': 'participant_id is required'
            }), 400

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

        return jsonify({
            'success': True,
            'message': 'Note created successfully',
            'note_id': note.note_id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f"Error creating note: {str(e)}"
        }), 500


@app.route('/all-notes')
@login_required
def all_notes():
    """View all notes for all participants"""
    return render_template('all_notes.html')


@app.route('/api/notes/all', methods=['GET'])
@login_required
def get_all_notes():
    """Get all notes for all participants"""
    try:
        notes = Notes.query.order_by(Notes.datetime.desc()).all()

        notes_data = []
        for note in notes:
            # Get admin username if available
            admin_username = None
            if note.admin_id:
                admin = Admin.query.get(note.admin_id)
                if admin:
                    admin_username = admin.username

            # Get participant info from User table
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

        return jsonify({
            'success': True,
            'notes': notes_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error fetching notes: {str(e)}"
        }), 500


@app.route('/api/email/templates', methods=['GET'])
@login_required
def get_email_templates():
    """Get available email templates"""
    try:
        templates = email_service.get_email_templates()
        return jsonify({
            'success': True,
            'templates': templates,
            'from_address': email_service.get_from_address()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error fetching templates: {str(e)}"
        }), 500


@app.route('/api/email/participant/<participant_id>', methods=['GET'])
@login_required
def get_participant_email_info(participant_id):
    """Get participant email info from REDCap for manual email sending"""
    try:
        # Find the user by redcap_id
        user = User.query.filter_by(redcap_id=participant_id).first()
        if not user:
            return jsonify({
                'success': False,
                'message': f'Participant {participant_id} not found in database'
            }), 404

        # Initialize participant data with defaults from local database
        participant_data = {
            'record_id': participant_id,
            'first_name': user.identifier or '',
            'email': '',
            'username': '',
            'password': '',
            'research_assistant': user.research_assistant or ''
        }

        # Get project config
        project_config = Config.get_project_by_id(user.project_id) if user.project_id else None
        if not project_config:
            # Try to get the first available project
            projects = Config.get_all_projects()
            if projects:
                project_config = projects[0]

        # Try to fetch from REDCap if configured
        if project_config and project_config.api_url and project_config.api_token:
            try:
                # Fetch participant data from REDCap
                fields = ['record_id', 'first_name', 'email', 'username', 'password']
                if project_config.ra_field:
                    fields.append(project_config.ra_field)

                data = {
                    'token': project_config.api_token,
                    'content': 'record',
                    'format': 'json',
                    'type': 'flat',
                    'records': participant_id,
                    'fields': ','.join(fields),
                    'returnFormat': 'json'
                }

                if project_config.event_name:
                    data['events'] = project_config.event_name

                response = requests.post(project_config.api_url, data=data, timeout=30)
                response.raise_for_status()
                redcap_data = response.json()

                if redcap_data and len(redcap_data) > 0:
                    entry = redcap_data[0]
                    if entry.get('first_name', '').strip():
                        participant_data['first_name'] = entry.get('first_name', '').strip()
                    if entry.get('email', '').strip():
                        participant_data['email'] = entry.get('email', '').strip()
                    if entry.get('username', '').strip():
                        participant_data['username'] = entry.get('username', '').strip()
                    if entry.get('password', '').strip():
                        participant_data['password'] = entry.get('password', '').strip()
                    if project_config.ra_field and entry.get(project_config.ra_field, '').strip():
                        participant_data['research_assistant'] = entry.get(project_config.ra_field, '').strip()

                # If email_event is configured and we don't have email yet, fetch from that event
                if project_config.email_event and not participant_data['email']:
                    email_data = {
                        'token': project_config.api_token,
                        'content': 'record',
                        'format': 'json',
                        'type': 'flat',
                        'records': participant_id,
                        'fields': 'record_id,email',
                        'events': project_config.email_event.strip(),
                        'returnFormat': 'json'
                    }

                    try:
                        email_response = requests.post(project_config.api_url, data=email_data, timeout=30)
                        email_response.raise_for_status()
                        email_records = email_response.json()

                        if email_records and len(email_records) > 0:
                            email_val = email_records[0].get('email', '').strip()
                            if email_val:
                                participant_data['email'] = email_val
                    except Exception as email_err:
                        # Log but don't fail - email event fetch is optional
                        print(f"Warning: Could not fetch email from event: {email_err}")

            except requests.exceptions.RequestException as redcap_err:
                # Log but don't fail - we can still show the modal with partial data
                print(f"Warning: REDCap fetch failed: {redcap_err}")
            except Exception as redcap_err:
                print(f"Warning: Error processing REDCap data: {redcap_err}")

        # Get last communication sent date
        last_email = Notes.query.filter(
            Notes.participant_id == participant_id,
            Notes.note_type == 'Email'
        ).order_by(Notes.datetime.desc()).first()

        participant_data['last_email_sent'] = last_email.datetime if last_email else None
        participant_data['last_email_by'] = None
        if last_email and last_email.admin_id:
            admin = Admin.query.get(last_email.admin_id)
            if admin:
                participant_data['last_email_by'] = admin.username

        return jsonify({
            'success': True,
            'participant': participant_data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f"Error fetching participant info: {str(e)}"
        }), 500


@app.route('/api/email/preview', methods=['POST'])
@login_required
def preview_email():
    """Preview an email before sending"""
    try:
        data = request.get_json()
        template_id = data.get('template_id')
        first_name = data.get('first_name', 'Participant')
        ra_first_name = data.get('ra_first_name', 'The Research Team')
        username = data.get('username', '')
        password = data.get('password', '')
        custom_message = data.get('custom_message', '')

        # Get RA first name only (first part of full name)
        if ra_first_name and ' ' in ra_first_name:
            ra_first_name = ra_first_name.split()[0]

        # Capitalize first name
        if first_name:
            first_name = first_name.strip()
            if first_name:
                first_name = first_name[0].upper() + first_name[1:] if len(first_name) > 1 else first_name.upper()

        body = email_service.format_email_body(
            template_id,
            first_name,
            ra_first_name,
            username=username,
            password=password,
            custom_message=custom_message
        )

        if not body:
            return jsonify({
                'success': False,
                'message': 'Invalid template'
            }), 400

        subject = email_service.get_template_subject(template_id)

        return jsonify({
            'success': True,
            'subject': subject,
            'body': body,
            'from_address': email_service.get_from_address()
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error generating preview: {str(e)}"
        }), 500


@app.route('/api/email/send', methods=['POST'])
@login_required
def send_manual_email():
    """Send a manual email to a participant"""
    try:
        data = request.get_json()
        participant_id = data.get('participant_id')
        to_email = data.get('to_email')
        subject = data.get('subject')
        body = data.get('body')
        template_id = data.get('template_id', 'custom')

        if not participant_id or not to_email or not subject or not body:
            return jsonify({
                'success': False,
                'message': 'Missing required fields'
            }), 400

        # Send the email
        success, message = email_service.send_email(to_email, subject, body)

        if success:
            # Log to notes table
            # Redact password if present in body
            logged_body = body
            password = data.get('password')
            if password:
                logged_body = body.replace(password, '********')

            template_name = email_service.EMAIL_TEMPLATES.get(template_id, {}).get('name', 'Manual')
            note_reason = f'Manual - {template_name}'

            note = Notes(
                admin_id=current_user.id,
                participant_id=str(participant_id),
                note_type='Email',
                note_reason=note_reason,
                datetime=datetime.now().strftime('%Y-%m-%dT%H:%M'),
                duration='N/A',
                note=f"Subject: {subject}\n\n{logged_body}"
            )
            db.session.add(note)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': 'Email sent successfully and logged to notes'
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 500

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f"Error sending email: {str(e)}"
        }), 500


@app.route('/api/email/last-communication/<participant_id>', methods=['GET'])
@login_required
def get_last_communication(participant_id):
    """Get the last communication sent to a participant"""
    try:
        # Get last email
        last_email = Notes.query.filter(
            Notes.participant_id == participant_id,
            Notes.note_type == 'Email'
        ).order_by(Notes.datetime.desc()).first()

        # Get last communication of any type
        last_any = Notes.query.filter(
            Notes.participant_id == participant_id
        ).order_by(Notes.datetime.desc()).first()

        result = {
            'last_email': None,
            'last_communication': None
        }

        if last_email:
            admin = Admin.query.get(last_email.admin_id) if last_email.admin_id else None
            result['last_email'] = {
                'datetime': last_email.datetime,
                'reason': last_email.note_reason,
                'by': admin.username if admin else 'System'
            }

        if last_any:
            admin = Admin.query.get(last_any.admin_id) if last_any.admin_id else None
            result['last_communication'] = {
                'datetime': last_any.datetime,
                'type': last_any.note_type,
                'reason': last_any.note_reason,
                'by': admin.username if admin else 'System'
            }

        return jsonify({
            'success': True,
            **result
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f"Error fetching communication history: {str(e)}"
        }), 500


@app.errorhandler(403)
def forbidden(e):
    """Handle 403 errors"""
    ip_address = request.remote_addr
    if request.headers.get('X-Forwarded-For'):
        ip_address = request.headers.get('X-Forwarded-For').split(',')[0].strip()

    return render_template('403.html', ip_address=ip_address), 403


@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors"""
    return render_template('404.html'), 404


def init_db():
    """Initialize database and create tables"""
    with app.app_context():
        db.create_all()
        print("Database initialized successfully")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
