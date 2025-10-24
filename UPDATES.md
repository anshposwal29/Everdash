# Theradash Updates

## Latest Updates (2025)

### REDCap Integration Improvements

#### 1. Configurable REDCap Filter Logic
- **Issue**: The filter logic was hardcoded and pulling in all participants instead of only those who completed the first interview.
- **Solution**:
  - Updated filter logic to use: `[interview_1_arm_1][first_interview_updated_complete]="2"`
  - Made REDCap form name and field names configurable via environment variables

#### 2. Configurable REDCap Form and Fields
Added new environment variables in `.env`:
```
REDCAP_FILTER_LOGIC=[interview_1_arm_1][first_interview_updated_complete]="2"
REDCAP_FORM_NAME=clinical_trial_monitoring
REDCAP_FIREBASE_ID_FIELD=firebase_id
REDCAP_RA_FIELD=ra
```

This makes it easy to:
- Change which form to pull data from
- Specify which field contains the Firebase ID
- Specify which field contains the Research Assistant assignment

#### 3. Handle Participants Without Firebase Data
- **Issue**: Participants without Firebase IDs were not showing up in the dashboard
- **Solution**:
  - Participants matching the REDCap filter are now included even without Firebase IDs
  - These participants show "0" or "-" for messages (since they have no Firebase data)
  - REDCap ID is displayed for all participants

#### 4. Research Assistant (RA) Assignment Display
- Added `research_assistant` field to User model
- Dashboard now displays:
  - REDCap ID (instead of Firebase ID) as the primary identifier
  - Research Assistant assignment in a separate column
- Data syncs from the configurable `ra` field in REDCap's `clinical_trial_monitoring` form

### Dashboard Enhancements

#### 5. Interactive Day Cell View
- **Feature**: Click on any day cell with messages to view conversation details
- Shows:
  - All messages for that user on that date
  - Message timestamps in Eastern Time
  - Risk scores
  - Review status for each message

#### 6. Message Review Tracking
- **Feature**: Mark messages as reviewed
- When viewing a day's messages, you can:
  - See which messages have been reviewed
  - Mark all messages for that day as reviewed with one click
- Review tracking includes:
  - Reviewer ID (which admin reviewed it)
  - Review timestamp

#### 7. Visual Indicators for Unreviewed Messages
- **Feature**: Days with unread/unreviewed messages are clearly marked
- Visual indicators:
  - Orange warning badge (⚠) on cells with unreviewed messages
  - Orange border around unreviewed message cells
  - All unreviewed cells stand out for easy identification

## Database Changes

### New Column in `users` Table
- `research_assistant` (VARCHAR(100)) - stores the RA assigned to each participant

### New Columns in `messages` Table (already existed)
- `is_reviewed` (BOOLEAN) - whether the message has been reviewed
- `reviewed_by_id` (INTEGER) - ID of admin who reviewed it
- `reviewed_at` (DATETIME) - when it was reviewed

## Migration Instructions

If you have an existing database, run the migration script:

```bash
python migrate_add_ra_field.py
```

This will add the `research_assistant` column to your `users` table.

## Configuration Updates

Update your `.env` file with the new REDCap configuration:

```
REDCAP_FILTER_LOGIC=[interview_1_arm_1][first_interview_updated_complete]="2"
REDCAP_FORM_NAME=clinical_trial_monitoring
REDCAP_FIREBASE_ID_FIELD=firebase_id
REDCAP_RA_FIELD=ra
```

## How to Use

1. **Sync Data**: Click "Refresh Data" to sync from REDCap and Firebase
2. **View Messages**: Click on any colored cell to see that day's messages
3. **Review Messages**: In the modal, click "Mark All as Reviewed" after checking messages
4. **Track Unreviewed**: Look for the orange ⚠ badge to find unreviewed messages

## Technical Details

### API Endpoints Added
- `GET /api/messages/<firebase_id>/<date_str>` - Get messages for specific user and date
- `POST /api/messages/<message_id>/mark-reviewed` - Mark single message as reviewed
- `POST /api/messages/date/<firebase_id>/<date_str>/mark-reviewed` - Mark all messages for a date as reviewed

### Files Modified
- `config.py` - Added new REDCap configuration variables
- `models.py` - Added `research_assistant` field to User model
- `app.py` - Added API endpoints and updated dashboard route
- `services/redcap_service.py` - Updated to use configurable fields and filter logic
- `services/sync_service.py` - Updated participant sync to use new fields
- `templates/dashboard.html` - Added modal, click handlers, and visual indicators
- `static/css/style.css` - Added modal and unreviewed message styling
- `.env` - Added new configuration variables

### Files Created
- `migrate_add_ra_field.py` - Database migration script
- `UPDATES.md` - This documentation file
