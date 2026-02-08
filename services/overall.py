from datetime import datetime, timedelta
from models import db, User, Message, Conversation


def _utc_now():
    # Your DB timestamps are effectively naive UTC in this project
    return datetime.utcnow()


def compute_user_risk(user_id):
    since = datetime.utcnow() - timedelta(days=14)

    risky_count = (
        db.session.query(Message)
        .filter(
            Message.user_id == user_id,
            Message.is_risky == True,
            Message.timestamp >= since
        )
        .count()
    )

    if risky_count >= 2:
        return "high"
    elif risky_count == 1:
        return "medium"
    else:
        return "normal"

def compute_risky_count(user_id, window_days):
    cutoff = _utc_now() - timedelta(days=window_days)

    # If your Message.timestamp is stored naive in DB, compare with naive cutoff
    cutoff_naive = cutoff.replace(tzinfo=None)

    return (
        Message.query
        .filter(Message.user_id == user_id)
        .filter(Message.timestamp >= cutoff_naive)
        .filter(Message.is_risky.is_(True))
        .count()
    )

def get_overall_users(window_days=14):
    users = User.query.all()
    rows = []

    for u in users:
        # Study duration
        days_in_study = None
        if u.study_start_date:
            days_in_study = (datetime.utcnow().date() - u.study_start_date).days

        # Last conversation
        last_convo = (
            u.conversations
            .order_by(Conversation.timestamp.desc())
            .first()
        )

        last_dialogue_relative = "—"
        last_dialogue_status = "closed"

        if last_convo:
            delta = datetime.utcnow() - last_convo.timestamp
            hours = int(delta.total_seconds() / 3600)
            last_dialogue_relative = f"{hours}h ago" if hours < 24 else f"{hours//24}d ago"
            last_dialogue_status = "active" if hours < 24 else "closed"

        # Risk
        risky_count = compute_risky_count(u.id, window_days)

        rows.append({
            "id": u.identifier or u.redcap_id or u.firebase_id[:6],
            "days_in_study": days_in_study,
            "last_dialogue_relative": last_dialogue_relative,
            "last_dialogue_status": last_dialogue_status,
            "risky_count": risky_count,
            "status": "needs review", #FIX THIS

            # placeholder for now — we’ll wire real compliance later
            "compliance_7d": {
                "ema": "good",
                "location": "partial",
                "battery": "good",
                "accel": "good",
                "gyro": "good",
            },
        })

    return rows

