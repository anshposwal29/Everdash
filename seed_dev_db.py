import random
from datetime import datetime, timedelta, date
from app import app
from models import db, User, Conversation, Message, PassiveDailySummary, REDCapProject

def seed():
    random.seed(7)
    today = date.today()

    with app.app_context():
        # Start clean (dev only)
        db.drop_all()
        db.create_all()

        # Create a fake project (since User.project_id FK points to redcap_projects.project_id)
        project = REDCapProject(
            project_id="DEV_PROJECT",
            name="Dev Project",
            api_url="https://example.com/redcap/api"
        )
        db.session.add(project)
        db.session.commit()

        users = []
        for i in range(1, 21):
            u = User(
                firebase_id=f"dev_firebase_{i:03d}",
                redcap_firebase_id=f"RCAP_FB_{i:03d}",
                redcap_id=f"P{i:03d}",
                identifier=f"participant{i:03d}@example.com",
                research_assistant=random.choice(["RA_Ana", "RA_Caio", "RA_Joao"]),
                is_active=True,
                project_id=project.project_id,
                study_start_date=today - timedelta(days=random.randint(5, 120)),
                symptom_radar=random.randint(1, 10),
            )
            db.session.add(u)
            users.append(u)
        db.session.commit()

        # Create conversations + messages (5 dialogues per user)
        for u in users:
            for c in range(5):
                # Spread conversations over last 35 days
                start_dt = datetime.utcnow() - timedelta(days=random.randint(0, 35), hours=random.randint(0, 23))
                conv = Conversation(
                    firebase_convo_id=f"dev_convo_{u.redcap_id}_{c}",
                    user_id=u.id,
                    prompt="(dev) prompt",
                    timestamp=start_dt,
                )
                db.session.add(conv)
                db.session.flush()  # get conv.id

                # Dialogue = alternating Evie/user messages
                # We'll do 8 messages (Evie starts, then user, etc.)
                t = start_dt
                sender = "evie"
                for m in range(8):
                    t = t + timedelta(minutes=random.randint(2, 45))

                    # risk only on user messages
                    is_risky = (sender == "user") and (random.random() < 0.12)

                    msg = Message(
                        firebase_message_id=f"dev_msg_{u.redcap_id}_{c}_{m}",
                        conversation_id=conv.id,
                        user_id=u.id,
                        text=f"(dev) {sender} message {m}",
                        timestamp=t,
                        is_risky=is_risky,
                    )
                    db.session.add(msg)
                    sender = "user" if sender == "evie" else "evie"

        # Passive sensing daily summary for last 30 days
        def gen_hours():
            r = random.random()
            if r < 0.15:
                return 0.0          # missing
            if r < 0.35:
                return random.uniform(1.0, 11.5)  # partial
            return random.uniform(12.0, 24.0)     # good

        for u in users:
            for d in range(0, 30):
                day = today - timedelta(days=d)
                row = PassiveDailySummary(
                    user_id=u.id,
                    day=day,
                    loc_hours=gen_hours(),
                    bat_hours=gen_hours(),
                    acc_hours=gen_hours(),
                    gyr_hours=gen_hours(),
                )
                db.session.add(row)

        db.session.commit()
        print("Seeded dev DB with 20 users, dialogues, and passive data.")

if __name__ == "__main__":
    seed()
