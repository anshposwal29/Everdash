from datetime import datetime, timedelta, date
from sqlalchemy import func, case, desc, asc
from models import db, User, Message, PassiveDailySummary

GOOD_HOURS = 12.0

def _passive_bucket(col):
    good = func.sum(case((col >= GOOD_HOURS, 1), else_=0))
    partial = func.sum(case(((col > 0) & (col < GOOD_HOURS), 1), else_=0))
    missing = func.sum(case((col == 0, 1), else_=0))
    return good, partial, missing

def get_overall_users(window_days=14, sort="silence", order="desc", limit=50, offset=0):
    now = datetime.utcnow()
    today = date.today()
    window_start_date = today - timedelta(days=window_days - 1)
    window_start_dt = now - timedelta(days=window_days)

    # Base users page
    users_q = User.query

    # --- Last dialogue per user (max Message.timestamp)
    last_dialogue_subq = (
        db.session.query(
            Message.user_id.label("user_id"),
            func.max(Message.timestamp).label("last_dialogue_at"),
        )
        .group_by(Message.user_id)
        .subquery()
    )

    # --- Risky count in window
    risky_subq = (
        db.session.query(
            Message.user_id.label("user_id"),
            func.sum(case((Message.is_risky == True, 1), else_=0)).label("risky_count"),
        )
        .filter(Message.timestamp >= window_start_dt)
        .group_by(Message.user_id)
        .subquery()
    )

    # --- Passive compliance buckets (counts of days good/partial/missing) in window
    loc_g, loc_p, loc_m = _passive_bucket(PassiveDailySummary.loc_hours)
    bat_g, bat_p, bat_m = _passive_bucket(PassiveDailySummary.bat_hours)
    acc_g, acc_p, acc_m = _passive_bucket(PassiveDailySummary.acc_hours)
    gyr_g, gyr_p, gyr_m = _passive_bucket(PassiveDailySummary.gyr_hours)

    passive_subq = (
        db.session.query(
            PassiveDailySummary.user_id.label("user_id"),
            func.count(PassiveDailySummary.day).label("days_observed"),
            loc_g.label("loc_good"), loc_p.label("loc_partial"), loc_m.label("loc_missing"),
            bat_g.label("bat_good"), bat_p.label("bat_partial"), bat_m.label("bat_missing"),
            acc_g.label("acc_good"), acc_p.label("acc_partial"), acc_m.label("acc_missing"),
            gyr_g.label("gyr_good"), gyr_p.label("gyr_partial"), gyr_m.label("gyr_missing"),
        )
        .filter(PassiveDailySummary.day >= window_start_date, PassiveDailySummary.day <= today)
        .group_by(PassiveDailySummary.user_id)
        .subquery()
    )

    # Join everything onto users
    q = (
        users_q
        .outerjoin(last_dialogue_subq, last_dialogue_subq.c.user_id == User.id)
        .outerjoin(risky_subq, risky_subq.c.user_id == User.id)
        .outerjoin(passive_subq, passive_subq.c.user_id == User.id)
        .with_entities(
            User,
            last_dialogue_subq.c.last_dialogue_at,
            risky_subq.c.risky_count,
            passive_subq.c.days_observed,
            passive_subq.c.loc_good, passive_subq.c.loc_partial, passive_subq.c.loc_missing,
            passive_subq.c.bat_good, passive_subq.c.bat_partial, passive_subq.c.bat_missing,
            passive_subq.c.acc_good, passive_subq.c.acc_partial, passive_subq.c.acc_missing,
            passive_subq.c.gyr_good, passive_subq.c.gyr_partial, passive_subq.c.gyr_missing,
        )
    )

    # Sorting in SQL (performance-safe)
    direction = desc if order == "desc" else asc

    # Sorting in SQL (performance-safe)
    if sort == "silence":
        # longest silence first => oldest last_dialogue_at first
        q = q.order_by(asc(last_dialogue_subq.c.last_dialogue_at).nullslast())

    elif sort == "recent":
        # most recent dialogue first => newest last_dialogue_at first
        q = q.order_by(desc(last_dialogue_subq.c.last_dialogue_at).nullslast())

    elif sort in ("risk", "risky"):
        q = q.order_by(desc(func.coalesce(risky_subq.c.risky_count, 0)))

    elif sort == "days":
        # most days in study last --> most recent study_start_date first
        q = q.order_by(desc(User.study_start_date).nullslast())

    else:
        q = q.order_by(User.id.asc())


    q = q.limit(limit).offset(offset)

    rows = []
    for (user,
         last_dialogue_at,
         risky_count,
         days_observed,
         loc_good, loc_partial, loc_missing,
         bat_good, bat_partial, bat_missing,
         acc_good, acc_partial, acc_missing,
         gyr_good, gyr_partial, gyr_missing) in q.all():

        days_in_study = (today - user.study_start_date).days if user.study_start_date else None
        silence_days = (now - last_dialogue_at).days if last_dialogue_at else None

        rows.append({
            "user_id": user.id,
            "redcap_id": user.redcap_id,
            "identifier": user.identifier,
            "days_in_study": days_in_study,
            "last_dialogue_at": last_dialogue_at.isoformat() + "Z" if last_dialogue_at else None,
            "silence_days": silence_days,
            "risky_count": int(risky_count or 0),
            "passive_compliance": {
                "window_days": window_days,
                "days_observed": int(days_observed or 0),
                "loc": {"good_days": int(loc_good or 0), "partial_days": int(loc_partial or 0), "missing_days": int(loc_missing or 0)},
                "bat": {"good_days": int(bat_good or 0), "partial_days": int(bat_partial or 0), "missing_days": int(bat_missing or 0)},
                "acc": {"good_days": int(acc_good or 0), "partial_days": int(acc_partial or 0), "missing_days": int(acc_missing or 0)},
                "gyr": {"good_days": int(gyr_good or 0), "partial_days": int(gyr_partial or 0), "missing_days": int(gyr_missing or 0)},
            },
            "symptom_radar": int(user.symptom_radar or 5),
            "utilization_status": getattr(user, "utilization_status", None),
            "dropped": bool(getattr(user, "dropped", False)),
        })

    return rows
