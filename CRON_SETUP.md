# Automated Sync Setup Guide

This guide explains how to set up automatic data synchronization using a cron job.

## Overview

The system now supports automatic syncing every 2 minutes using a cron job. This ensures that:
- New messages are synced even if no one clicks the "Refresh" button
- Important high-risk messages are detected quickly
- Study personnel can respond promptly to critical situations
- The "Last Sync" timestamp is always up-to-date

## Files

- `cron_sync.py` - The main Python script that performs the sync
- `setup_cron.sh` - Automated setup script to install the cron job
- `logs/cron_sync.log` - Log file where sync output is stored

## Quick Setup

### Option 1: Automated Setup (Recommended)

Run the setup script which will automatically configure everything:

```bash
cd /Users/mvh24011/theradash
./setup_cron.sh
```

This script will:
1. Detect your Python virtual environment
2. Create the necessary log directory
3. Install the cron job to run every 2 minutes
4. Test the sync to ensure it works
5. Display helpful commands for monitoring

### Option 2: Manual Setup

1. **Make the sync script executable:**
   ```bash
   chmod +x /Users/mvh24011/theradash/cron_sync.py
   ```

2. **Create logs directory:**
   ```bash
   mkdir -p /Users/mvh24011/theradash/logs
   ```

3. **Test the script manually:**
   ```bash
   cd /Users/mvh24011/theradash
   ./venv/bin/python cron_sync.py
   ```

4. **Edit your crontab:**
   ```bash
   crontab -e
   ```

5. **Add this line (adjust paths as needed):**
   ```
   */2 * * * * cd /Users/mvh24011/theradash && /Users/mvh24011/theradash/venv/bin/python /Users/mvh24011/theradash/cron_sync.py >> /Users/mvh24011/theradash/logs/cron_sync.log 2>&1
   ```

## Cron Schedule Explanation

```
*/2 * * * *
│   │ │ │ │
│   │ │ │ └─── Day of week (0-7, Sunday=0 or 7)
│   │ │ └───── Month (1-12)
│   │ └─────── Day of month (1-31)
│   └───────── Hour (0-23)
└─────────── Minute (*/2 = every 2 minutes)
```

### Other Schedule Options

If you want different timing, here are some examples:

- Every minute: `* * * * *`
- Every 5 minutes: `*/5 * * * *`
- Every 10 minutes: `*/10 * * * *`
- Every hour: `0 * * * *`

## Monitoring

### View Real-Time Logs

```bash
tail -f /Users/mvh24011/theradash/logs/cron_sync.log
```

### View Current Cron Jobs

```bash
crontab -l
```

### Check Recent Syncs

```bash
tail -50 /Users/mvh24011/theradash/logs/cron_sync.log
```

### Test Manually

```bash
cd /Users/mvh24011/theradash
./venv/bin/python cron_sync.py
```

## Troubleshooting

### Cron Job Not Running

1. **Check if cron service is running:**
   ```bash
   # On macOS
   sudo launchctl list | grep cron

   # On Linux
   sudo systemctl status cron
   ```

2. **Verify cron job is installed:**
   ```bash
   crontab -l
   ```

3. **Check system logs:**
   ```bash
   # On macOS
   tail -f /var/log/system.log | grep cron

   # On Linux
   tail -f /var/log/syslog | grep CRON
   ```

### Firebase Credentials Error

If you see: `Your default credentials were not found`

Make sure your `.env` file has:
```
FIREBASE_CREDENTIALS_PATH=/path/to/your/firebase-credentials.json
```

### Permission Denied

If the script fails with permission errors:
```bash
chmod +x /Users/mvh24011/theradash/cron_sync.py
chmod +x /Users/mvh24011/theradash/venv/bin/python
```

### Virtual Environment Not Found

If you get `venv/bin/python: No such file or directory`:

1. Activate your virtual environment:
   ```bash
   cd /Users/mvh24011/theradash
   source venv/bin/activate
   ```

2. Or use system Python:
   ```bash
   which python3
   ```
   Then update the cron job to use that path.

## Removing the Cron Job

To stop automatic syncing:

```bash
crontab -e
```

Then delete the line containing `cron_sync.py` and save.

Or remove all cron jobs:
```bash
crontab -r
```

## How It Works

1. **Cron triggers** - Every 2 minutes, cron runs the `cron_sync.py` script
2. **Sync executes** - The script calls `sync_service.full_sync()` which:
   - Syncs users from REDCap/Firebase
   - Fetches new conversations
   - Fetches new messages since last sync
   - Checks risk scores and sends alerts if needed
3. **Database updates** - The sync log table is updated with the timestamp
4. **Dashboard shows** - The "Last Sync" timestamp on the dashboard reflects the latest sync
5. **Logs stored** - All output is appended to `logs/cron_sync.log`

## Log Rotation

To prevent logs from growing too large, consider setting up log rotation:

```bash
# Create logrotate config
sudo nano /etc/logrotate.d/theradash
```

Add this content:
```
/Users/mvh24011/theradash/logs/cron_sync.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
```

## Production Deployment

For production servers, consider:

1. **Using a service manager** like systemd instead of cron
2. **Setting up monitoring** with tools like Datadog or New Relic
3. **Configuring alerts** if syncs fail
4. **Using a dedicated user** for running the sync
5. **Storing logs** in `/var/log/` instead of project directory

## Example Systemd Service (Alternative to Cron)

For more robust production deployments, create `/etc/systemd/system/theradash-sync.service`:

```ini
[Unit]
Description=TheraChat Sync Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/theradash
ExecStart=/var/www/theradash/venv/bin/python /var/www/theradash/cron_sync.py
Restart=on-failure
RestartSec=120

[Install]
WantedBy=multi-user.target
```

And a timer `/etc/systemd/system/theradash-sync.timer`:

```ini
[Unit]
Description=Run TheraChat sync every 2 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=2min
Unit=theradash-sync.service

[Install]
WantedBy=timers.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable theradash-sync.timer
sudo systemctl start theradash-sync.timer
```

## Support

If you encounter issues, check:
1. The log file: `logs/cron_sync.log`
2. Your `.env` file configuration
3. Database permissions
4. Firebase credentials
5. Network connectivity
