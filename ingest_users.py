import sys
import requests
import datetime
from sqlalchemy.dialects.postgresql import insert
from config import Config
from database import get_db
from schema import User, REDCapProject, UserCustomField
from utils import to_tz_aware_datetime

def fetch_redcap_data(project_config):
    """
    Directly fetch data from REDCap API using requests.
    Decoupled from the old service classes for stability.
    """
    print(f"   -> Connecting to REDCap Project: {project_config.name}...")
    
    # 1. Build Field List
    fields = [
        project_config.firebase_id_field,
        project_config.ra_field,
        'record_id',
        'username',
        'dropped',
        'dropped_surveys'
    ]
    
    # Add dates if configured
    if project_config.study_start_date_field:
        fields.append(project_config.study_start_date_field)
    if project_config.study_end_date_field:
        fields.append(project_config.study_end_date_field)
        
    # Add custom fields
    for cf in project_config.custom_display_fields:
        if cf.get('field'):
            fields.append(cf.get('field'))
            
    payload = {
        'token': project_config.api_token,
        'content': 'record',
        'format': 'json',
        'type': 'flat',
        'fields': ','.join(fields),
        'filterLogic': project_config.filter_logic,
        'returnFormat': 'json'
    }
    
    if project_config.event_name:
        payload['events'] = project_config.event_name

    try:
        resp = requests.post(project_config.api_url, data=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        print(f"   -> Fetched {len(data)} records.")
        return data
    except Exception as e:
        print(f"   ❌ Error fetching REDCap data: {e}")
        return []

def parse_date(date_str):
    """Helper to parse REDCap YYYY-MM-DD dates"""
    if not date_str: return None
    try:
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None

def parse_bool(val):
    """Helper to parse REDCap booleans (1/0/yes/no)"""
    if isinstance(val, str):
        return val.lower() in ['1', 'yes', 'true', 'checked']
    return bool(val)

def run_user_ingest():
    print(f"\n=== Starting User Ingest (Active Pipeline) ===")
    print(f"Time: {datetime.datetime.now()}")
    
    db = next(get_db())
    projects = Config.get_all_projects()
    
    total_users_touched = 0
    
    try:
        for proj in projects:
            print(f"\nProcessing Project: {proj.id}")
            
            # 1. Sync Project Definition
            existing_proj = db.query(REDCapProject).filter_by(project_id=proj.id).first()
            if not existing_proj:
                new_proj = REDCapProject(
                    project_id=proj.id,
                    name=proj.name,
                    api_url=proj.api_url
                )
                db.add(new_proj)
                db.commit()
            
            # 2. Fetch Data
            records = fetch_redcap_data(proj)
            
            # 3. Process Records
            for r in records:
                # Extract Keys
                record_id = r.get('record_id')
                raw_firebase_id = r.get(proj.firebase_id_field, '').strip()
                username = r.get('username', '').strip()
                
                # Determine Identity
                # Logic: If no firebase_id in REDCap, create a placeholder ID so we can still track them
                final_firebase_id = raw_firebase_id
                if not final_firebase_id:
                    final_firebase_id = f"redcap_{proj.id}_{record_id}"
                
                # Check if user exists
                user = db.query(User).filter_by(firebase_id=final_firebase_id).first()
                
                if not user:
                    user = User(firebase_id=final_firebase_id)
                    db.add(user)
                
                # Update Core Fields
                user.project_id = proj.id
                user.redcap_id = str(record_id)
                user.redcap_firebase_id = raw_firebase_id  # Store what was actually in the box
                
                # Only update identifier if it's missing or generic
                if not user.identifier or user.identifier == '-':
                    user.identifier = username or '-'
                
                user.research_assistant = r.get(proj.ra_field, '')
                
                # Update Dates
                if proj.study_start_date_field:
                    user.study_start_date = parse_date(r.get(proj.study_start_date_field))
                if proj.study_end_date_field:
                    user.study_end_date = parse_date(r.get(proj.study_end_date_field))
                    
                # Update Status
                user.dropped = parse_bool(r.get('dropped'))
                user.dropped_surveys = parse_bool(r.get('dropped_surveys'))
                
                # Mark as active and synced
                user.is_active = True
                user.last_synced = datetime.datetime.utcnow()
                
                # Flush to ensure User has an ID for custom fields
                db.flush()
                
                # 4. Process Custom Fields
                for cf_config in proj.custom_display_fields:
                    f_name = cf_config.get('field')
                    f_label = cf_config.get('label', f_name)
                    f_val = r.get(f_name)
                    
                    if f_name:
                        # Check if custom field exists
                        custom_field = db.query(UserCustomField).filter_by(
                            user_id=user.id, 
                            field_name=f_name
                        ).first()
                        
                        if not custom_field:
                            custom_field = UserCustomField(
                                user_id=user.id,
                                field_name=f_name
                            )
                            db.add(custom_field)
                        
                        custom_field.field_label = f_label
                        custom_field.field_value = str(f_val) if f_val else ''
                        custom_field.last_updated = datetime.datetime.utcnow()
                
                total_users_touched += 1
            
            # Commit after each project
            db.commit()
            print(f"   ✓ Synced {len(records)} users for project {proj.id}")

    except Exception as e:
        print(f"\n❌ Critical Error in User Ingest: {e}")
        db.rollback()
    finally:
        db.close()
        print(f"\n=== Ingest Complete. Touched {total_users_touched} users. ===\n")

if __name__ == "__main__":
    run_user_ingest()

    