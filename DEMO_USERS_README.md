# Demo Users Management

This document explains how to add demo internal users to Firebase Authentication.

## Script: `add_demo_users.py`

### Features

- Creates users in Firebase Authentication with format: `demo-internal-XXX@test.com`
- Automatically generates secure random passwords (excluding confusing characters: I, l, O, 0)
- User documents in Firestore will be created automatically on first login
- Auto-detects the next available user number
- Displays all credentials at the end for easy copying
- **Exports credentials to CSV file** for distribution to research assistants and internal testers

### Prerequisites

1. Ensure Firebase credentials are configured in `.env`:
   ```
   FIREBASE_CREDENTIALS_PATH=/path/to/your/firebase-credentials.json
   ```

2. Virtual environment should be activated:
   ```bash
   source venv/bin/activate
   ```

### Usage

#### Basic Usage

Create 5 demo users (auto-numbering from next available, CSV created automatically):
```bash
python add_demo_users.py --count 5
```

#### Specify Starting Number

Create 10 users starting from demo-internal-001:
```bash
python add_demo_users.py --count 10 --start 1
```

Create 5 users starting from demo-internal-050:
```bash
python add_demo_users.py --count 5 --start 50
```

#### Custom Password Length

Create 3 users with 16-character passwords:
```bash
python add_demo_users.py --count 3 --password-length 16
```

#### CSV File Options

Create users with custom CSV filename:
```bash
python add_demo_users.py --count 5 --csv internal_testers_batch1.csv
```

Create users without generating CSV file:
```bash
python add_demo_users.py --count 5 --no-csv
```

### Options

- `--count`: **(Required)** Number of users to create
- `--start`: Starting user number (default: auto-detect next available)
- `--password-length`: Length of generated passwords (default: 12, minimum: 6)
- `--csv`: Custom filename for CSV export (default: `demo_users_YYYYMMDD_HHMMSS.csv`)
- `--no-csv`: Skip creating CSV file (by default, CSV is always created)

### Output

The script will:
1. Show progress for each user creation
2. Display a summary of successes and failures
3. Print a table with all credentials (email, password, UID)

**Example output:**
```
Creating 3 demo users...

--------------------------------------------------------------------------------
✓ Created Firebase Auth user: demo-internal-001@test.com (UID: abc123...)

✓ Created Firebase Auth user: demo-internal-002@test.com (UID: def456...)

✓ Created Firebase Auth user: demo-internal-003@test.com (UID: ghi789...)

--------------------------------------------------------------------------------

Summary:
  Successfully created: 3 users
  Failed: 0 users


================================================================================
CREDENTIALS FOR CREATED USERS
================================================================================

Email                                    Password             UID
--------------------------------------------------------------------------------
demo-internal-001@test.com               a8Kd3FnP9mQr         abc123...
demo-internal-002@test.com               7Wt5YvBx2NpH         def456...
demo-internal-003@test.com               6Rj4MzCk8GsD         ghi789...

⚠️  IMPORTANT: Save these credentials securely!
   Passwords cannot be retrieved later.
================================================================================

================================================================================
CSV FILE CREATED
================================================================================
✓ Credentials saved to: demo_users_20241024_143022.csv
  Total users in file: 3

  This file can be used by research assistants to
  distribute credentials to internal testers via email.
================================================================================
```

### Password Characteristics

Generated passwords:
- Use alphanumeric characters only
- Exclude confusing characters: `I`, `l`, `O`, `0`
- Default length: 12 characters
- Character set: `ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789`

### CSV Export Format

By default, the script creates a CSV file with the following columns:
- `email`: User's email address (demo-internal-XXX@test.com)
- `password`: Generated password
- `uid`: Firebase Authentication UID
- `display_name`: Formatted display name (Demo User XXX)

**Example CSV:**
```csv
email,password,uid,display_name
demo-internal-001@test.com,a8Kd3FnP9mQr,abc123xyz,Demo User 001
demo-internal-002@test.com,7Wt5YvBx2NpH,def456uvw,Demo User 002
demo-internal-003@test.com,6Rj4MzCk8GsD,ghi789rst,Demo User 003
```

This CSV can be:
- Imported into email clients for mail merge
- Shared with research assistants for distribution
- Used to track issued credentials
- Imported into spreadsheet tools for management

### Firestore User Documents

User documents in Firestore will be created automatically when each user logs in for the first time. This ensures the user document structure matches your app's authentication flow.

### Important Notes

⚠️ **Security Warning**:
- Save the credentials immediately after creation
- Passwords cannot be retrieved later from Firebase
- Consider storing credentials in a secure password manager

⚠️ **User Numbers**:
- User numbers are formatted with 3 digits (001, 002, etc.)
- Maximum user number: 999
- The script will auto-detect existing users to avoid conflicts

### Troubleshooting

**Error: "Firebase credentials not found"**
- Check that `FIREBASE_CREDENTIALS_PATH` is set in `.env`
- Verify the credentials file exists at the specified path

**Error: "Email already exists"**
- A user with that email already exists in Firebase Auth
- Use `--start` parameter to skip to a different number range

**Error: "Permission denied"**
- Your Firebase credentials may not have sufficient permissions
- Ensure the service account has "Firebase Authentication Admin" role

### Examples

#### Create first batch of users
```bash
python add_demo_users.py --count 20 --start 1
```

#### Add more users later
```bash
python add_demo_users.py --count 10
# Auto-detects next available number (21 in this case)
```

#### Create users for specific test range
```bash
python add_demo_users.py --count 5 --start 100
# Creates demo-internal-100 through demo-internal-104
```

#### Create users with custom CSV name for specific batch
```bash
python add_demo_users.py --count 10 --start 1 --csv ra_team_alpha.csv
# Creates 10 users and saves to ra_team_alpha.csv for RA distribution
```
