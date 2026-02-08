from datetime import datetime, timedelta
from sqlalchemy import and_
import pytz

from models import db, User, Message, Conversation, SyncLog, Notes
from config import Config


def build_dashboard_context(request, et_tz, date_to_utc_range):
    """
    Builds the full context dict used by dashboard.html.
    Works for both /dashboard and /overall?view=calendar.
    """

    # --- Copy the SAME parameter parsing you already have in dashboard() ---
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

    # Get active users with optional filters
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

    # ---- Notes prefetch logic (same as your dashboard) ----
    user_redcap_ids = [u.redcap_id for u in users if u.redcap_id]

    start_date_str2 = start_date.strftime('%Y-%m-%d')
    end_date_str2 = (end_date + timedelta(days=1)).strftime('%Y-%m-%d')

    notes_in_range = []
    if user_redcap_ids:
        notes_in_range = Notes.query.filter(
            Notes.participant_id.in_(user_redcap_ids),
            Notes.datetime >= start_date_str2,
            Notes.datetime < end_date_str2
        ).all()

    notes_by_participant_date = {}
    for note in notes_in_range:
        if not note.datetime:
            continue
        note_date = note.datetime[:10]
        key = (note.participant_id, note_date)
        if key not in notes_by_participant_date:
            notes_by_participant_date[key] = {'phone': 0, 'email': 0, 'text': 0}

        note_type = (note.note_type or '').lower()
        if 'phone' in note_type or 'call' in note_type:
            notes_by_participant_date[key]['phone'] += 1
        elif 'email' in note_type:
            notes_by_participant_date[key]['email'] += 1
        elif 'text' in note_type or 'sms' in note_type:
            notes_by_participant_date[key]['text'] += 1

    # ---- Build dashboard_data (same as your dashboard) ----
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

        display_firebase_id = user.redcap_firebase_id if user.redcap_firebase_id else user.firebase_id

        user_row = {
            'firebase_id': user.firebase_id,
            'display_firebase_id': display_firebase_id,
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

        for date in date_range:
            date_start_utc, date_end_utc = date_to_utc_range(date)

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

            date_key = date.isoformat()
            comm_key = (user.redcap_id, date_key) if user.redcap_id else None
            comm_data = notes_by_participant_date.get(comm_key, {'phone': 0, 'email': 0, 'text': 0})

            user_row['dates'][date_key] = {
                'count': message_count,
                'has_risky': has_risky,
                'has_unreviewed': has_unreviewed,
                'phone_count': comm_data['phone'],
                'email_count': comm_data['email'],
                'text_count': comm_data['text']
            }

        user_has_risky = any(
            user_row['dates'][d.isoformat()]['has_risky']
            for d in date_range
            if d.isoformat() in user_row['dates']
        )
        user_row['has_any_risky'] = user_has_risky

        needs_attention = False
        if not user.dropped:
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

        total_messages = Message.query.filter_by(user_id=user.id).count()

        days_with_activity = sum(
            1 for d in date_range
            if user_row['dates'].get(d.isoformat(), {}).get('count', 0) > 0
        )
        total_days = len(date_range)

        recent_dates_sorted = sorted(date_range, reverse=True)
        consecutive_inactive_days = 0
        for d in recent_dates_sorted:
            date_key = d.isoformat()
            if user_row['dates'].get(date_key, {}).get('count', 0) == 0:
                consecutive_inactive_days += 1
            else:
                break

        if total_messages == 0:
            utilization_status = 'never_utilized'
        elif consecutive_inactive_days >= 3:
            utilization_status = 'inactive_3plus'
        elif days_with_activity >= (total_days * 0.5):
            utilization_status = 'consistent'
        else:
            utilization_status = 'moderate'

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

    attention_count = sum(1 for u in dashboard_data if u['needs_attention'])

    dashboard_data.sort(key=lambda x: (not x['needs_attention'], not x['has_any_risky'], x['redcap_id']))

    last_sync = SyncLog.query.order_by(SyncLog.created_at.desc()).first()

    # Return exactly what dashboard.html expects
    return dict(
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
        custom_field_labels=all_custom_field_labels,
    )
