from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, Admin, User, Message, Conversation, SyncLog
from config import Config
from middleware import require_ip_whitelist, ip_and_admin_required
from services.sync_service import sync_service
from services.twilio_service import twilio_service
from datetime import datetime, timedelta
import pytz
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

            user_row['dates'][date.isoformat()] = {
                'count': message_count,
                'has_risky': has_risky,
                'has_unreviewed': has_unreviewed
            }

        # Check if user has any risky messages in the date range
        user_has_risky = any(
            user_row['dates'][d.isoformat()]['has_risky']
            for d in date_range
            if d.isoformat() in user_row['dates']
        )
        user_row['has_any_risky'] = user_has_risky

        dashboard_data.append(user_row)

    # Apply risk filter
    if risk_filter == 'risky':
        dashboard_data = [u for u in dashboard_data if u['has_any_risky']]
    elif risk_filter == 'not_risky':
        dashboard_data = [u for u in dashboard_data if not u['has_any_risky']]

    # Sort: risky users first by default, then by redcap_id
    dashboard_data.sort(key=lambda x: (not x['has_any_risky'], x['redcap_id']))

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

        # Get messages in date range
        messages = Message.query.filter(
            and_(
                Message.user_id == user.id,
                Message.timestamp >= date_start_utc,
                Message.timestamp <= date_end_utc
            )
        ).order_by(Message.timestamp.desc()).all()
    else:
        # Get all messages
        messages = Message.query.filter_by(user_id=user.id).order_by(Message.timestamp.desc()).all()
        start_date = None
        end_date = None

    # Convert timestamps to Eastern Time for display
    for message in messages:
        message.timestamp_et = message.timestamp.replace(tzinfo=pytz.utc).astimezone(et_tz)

    return render_template('user_detail.html',
                         user=user,
                         messages=messages,
                         start_date=start_date,
                         end_date=end_date)


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
