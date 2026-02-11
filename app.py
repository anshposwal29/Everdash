from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Admin, User, Message, Conversation, SyncLog, Notes, PassiveDailySummary
from config import Config
from middleware import require_ip_whitelist, ip_and_admin_required
from services.sync_service import sync_service
from services.twilio_service import twilio_service
import services.email_service as email_service
from datetime import datetime, timedelta, timezone, date
import pytz
import requests
from sqlalchemy import func, and_
from services.overall import get_overall_users
from services.dashboard_context import build_dashboard_context

app = Flask(__name__)
app.config.from_object(Config)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///theradash_dev.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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

@app.route("/overall")
@login_required
def overall():
    view = request.args.get("view", "list")
    sort = request.args.get("sort", "silence")
    order = request.args.get("order", "desc")

    # ---- Risk window (used by Risky Dialogues column + API window_days)
    window = request.args.get("window", "14")
    try:
        window_days = int(window)
    except ValueError:
        window_days = 14
    if window_days not in (3, 7, 14, 30):
        window_days = 14

    # ---- Compliance window (used by "Recent Compliance (Xd)" label + link highlight)
    compliance = request.args.get("compliance", str(window_days))
    try:
        compliance_days = int(compliance)
    except ValueError:
        compliance_days = window_days
    if compliance_days not in (3, 7, 14, 30):
        compliance_days = window_days

    # ---- Calendar view keeps its own context builder
    if view == "calendar":
        ctx = build_dashboard_context(request, et_tz, date_to_utc_range)

        # keep these so your nav + labels still work on calendar page if needed
        ctx.update({
        "window_days": window_days,
        "compliance_days": compliance_days,
        "view": view,
        "sort": sort,
        "order": order,
    })
        return render_template("overall_calendar.html", **ctx)


    # ---- Week view (if you have a separate template)
    if view == "week":
        # If your week view is still server-rendered and expects users, keep it:
    
        return render_template(
            f"overall_{view}.html",
            window_days=window_days,
            compliance_days=compliance_days,  # optional, if you still show it anywhere
            view=view,
            sort=sort,
            order=order,
        )

    # ---- List view (API-driven: don't pass users)
    # still pass window_days/compliance_days because your header + links use them
    return render_template(
        f"overall_{view}.html",
        window_days=window_days,
        compliance_days=compliance_days,  # optional, if you still show it anywhere
        view=view,
        sort=sort,
        order=order,
    )


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
    ctx = build_dashboard_context(request, et_tz, date_to_utc_range)
    return render_template('dashboard.html', **ctx)

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

        # Get conversation info for messages
        conversation_ids = set(msg.conversation_id for msg in messages if msg.conversation_id)
        conversations = {}
        if conversation_ids:
            for conv in Conversation.query.filter(Conversation.id.in_(conversation_ids)).all():
                conversations[conv.id] = {
                    'id': conv.id,
                    'firebase_convo_id': conv.firebase_convo_id,
                    'prompt': conv.prompt
                }

        # Format messages for response
        messages_data = []
        for msg in messages:
            timestamp_et = msg.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)
            conv_info = conversations.get(msg.conversation_id, {})
            messages_data.append({
                'id': msg.id,
                'text': msg.text,
                'timestamp': timestamp_et.strftime('%I:%M %p'),
                'timestamp_date': timestamp_et.strftime('%b %d'),
                'timestamp_full': timestamp_et.strftime('%Y-%m-%d %I:%M:%S %p'),
                'is_risky': msg.is_risky,
                'is_reviewed': msg.is_reviewed,
                'conversation_id': msg.conversation_id,
                'conversation_prompt': conv_info.get('prompt', ''),
                'firebase_convo_id': conv_info.get('firebase_convo_id', '')
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
                datetime=datetime.now(et_tz).strftime('%Y-%m-%dT%H:%M'),
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
    
@app.route("/api/overall")
@login_required
def api_overall():
    window_days = int(request.args.get("window_days", 7))
    sort = request.args.get("sort", "silence")          # silence | recent | risk | days_in_study
    order = request.args.get("order", "desc")           # asc | desc
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    rows = get_overall_users(
        window_days=window_days,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return jsonify({"window_days": window_days, "rows": rows})


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
