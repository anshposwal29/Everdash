from app import app, db
from models import User, Message, Conversation, Notes, REDCapProject, Admin
from datetime import datetime, timedelta

def seed_database():
    with app.app_context():
        print("🌱 Seeding database...")

        # 1. Create ADMIN User (So you can log in!)
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(username='admin', email='admin@example.com')
            admin.set_password('password123')
            admin.is_approved = True
            admin.is_active = True
            db.session.add(admin)
            print("✅ Admin user created (User: admin / Pass: password123)")
        else:
            print("ℹ️ Admin user already exists.")

        # 2. Create Dummy Project
        if not REDCapProject.query.filter_by(project_id='test_project').first():
            project = REDCapProject(
                project_id='test_project',
                name='Demo Study A',
                api_url='http://example.com',
                is_active=True
            )
            db.session.add(project)
        
        db.session.commit()

        # 3. Create Dummy Users
        users = [
            {
                'firebase_id': 'user_123',
                'identifier': 'alice@example.com',
                'redcap_id': '1001',
                'research_assistant': 'Dr. Smith',
                'risk': True
            },
            {
                'firebase_id': 'user_456',
                'identifier': 'bob@example.com',
                'redcap_id': '1002',
                'research_assistant': 'Nurse Joy',
                'risk': False
            }
        ]

        for u_data in users:
            user = User.query.filter_by(firebase_id=u_data['firebase_id']).first()
            if not user:
                user = User(
                    firebase_id=u_data['firebase_id'],
                    identifier=u_data['identifier'],
                    redcap_id=u_data['redcap_id'],
                    research_assistant=u_data['research_assistant'],
                    project_id='test_project',
                    study_start_date=datetime.now().date() - timedelta(days=10)
                )
                db.session.add(user)
                db.session.commit()
                
                # Add Conversations & Messages
                convo = Conversation(
                    firebase_convo_id=f"convo_{user.id}",
                    user_id=user.id,
                    timestamp=datetime.now(),
                    prompt="How are you feeling?"
                )
                db.session.add(convo)
                db.session.commit()

                # Add a normal message
                msg1 = Message(
                    firebase_message_id=f"msg_{user.id}_1",
                    conversation_id=convo.id,
                    user_id=user.id,
                    text="I am feeling okay today.",
                    timestamp=datetime.utcnow(),
                    is_risky=False
                )
                db.session.add(msg1)

                # Add a risky message if flagged
                if u_data['risk']:
                    msg2 = Message(
                        firebase_message_id=f"msg_{user.id}_2",
                        conversation_id=convo.id,
                        user_id=user.id,
                        text="I am feeling very anxious and might hurt myself.",
                        timestamp=datetime.utcnow() - timedelta(days=1),
                        is_risky=True,
                        is_reviewed=False
                    )
                    db.session.add(msg2)
        
        db.session.commit()
        print("✅ Database fully populated!")

if __name__ == "__main__":
    seed_database()