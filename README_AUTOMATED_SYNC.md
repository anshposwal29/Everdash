# Automated Sync Feature

## Overview

Your TheraChat dashboard now supports **automatic data synchronization** via a cron job that runs every 2 minutes. This ensures critical messages are never missed, even if study personnel don't manually click the "Refresh" button.

## Key Features

✓ **Automatic Updates**: Data syncs every 2 minutes without manual intervention
✓ **Real-time Alerts**: High-risk messages trigger SMS alerts immediately
✓ **Manual Refresh**: The "Refresh" button still works for instant updates
✓ **Last Sync Display**: Dashboard shows when data was last updated
✓ **Comprehensive Logging**: All sync activity is logged for audit trails

## Quick Start

### 1. Install the Cron Job

Run the automated setup script:

```bash
cd /Users/mvh24011/theradash
./setup_cron.sh
```

This will:
- Configure the cron job to run every 2 minutes
- Create necessary directories
- Test the sync to ensure it works
- Show you helpful monitoring commands

### 2. Verify Installation

Check that everything is working:

```bash
./check_cron_status.sh
```

### 3. Monitor Activity

View real-time sync logs:

```bash
tail -f logs/cron_sync.log
```

## How It Works

```
┌─────────────────────┐
│   Cron Job          │  Runs every 2 minutes
│   (Every 2 min)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   cron_sync.py      │  Executes sync process
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   sync_service      │  Syncs data from Firebase
│   - Users           │
│   - Conversations   │
│   - Messages        │
│   - Risk alerts     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Database          │  Updates local SQLite
│   - SyncLog         │  Records timestamp
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│   Dashboard         │  Shows "Last Sync"
└─────────────────────┘
```

## Files Created

| File | Purpose |
|------|---------|
| `cron_sync.py` | Main sync script executed by cron |
| `setup_cron.sh` | Automated installer for cron job |
| `check_cron_status.sh` | Status checker and diagnostics |
| `CRON_SETUP.md` | Detailed setup documentation |
| `CRON_QUICKSTART.txt` | Quick reference card |
| `logs/cron_sync.log` | Sync activity logs |

## Important Notes

### The "Refresh" Button Still Works

- Users can still manually click "Refresh" for immediate updates
- Manual refreshes and automatic syncs both update the "Last Sync" timestamp
- Manual refreshes are useful when you want instant feedback

### Incremental Syncing

The sync is intelligent and efficient:
- **First sync**: Fetches all data
- **Subsequent syncs**: Only fetches new messages since last sync
- **Result**: Fast execution and low Firebase API costs

### Risk Alert System

When a high-risk message (score > 0.7) is detected:
1. Message is synced to database
2. SMS alert is sent to configured admin numbers
3. Alert is logged in the database
4. Dashboard highlights the message in red

## Configuration

The cron job timing can be adjusted by editing your crontab:

```bash
crontab -e
```

Current schedule (every 2 minutes):
```
*/2 * * * * cd /path/to/theradash && /path/to/python cron_sync.py >> logs/cron_sync.log 2>&1
```

Alternative schedules:
- Every minute: `* * * * *`
- Every 5 minutes: `*/5 * * * *`
- Every 10 minutes: `*/10 * * * *`

## Monitoring & Troubleshooting

### Check Status
```bash
./check_cron_status.sh
```

### View Recent Syncs
```bash
tail -50 logs/cron_sync.log
```

### View Live Logs
```bash
tail -f logs/cron_sync.log
```

### Test Manually
```bash
./venv/bin/python cron_sync.py
```

### Common Issues

**Issue**: Cron job not running
**Solution**: Check if cron service is active: `crontab -l`

**Issue**: Firebase credentials error
**Solution**: Ensure `.env` has `FIREBASE_CREDENTIALS_PATH` set correctly

**Issue**: Permission denied
**Solution**: Make script executable: `chmod +x cron_sync.py`

## Uninstalling

To remove the automatic sync:

```bash
crontab -e
```

Delete the line containing `cron_sync.py` and save.

Or use this one-liner:
```bash
crontab -l | grep -v "cron_sync.py" | crontab -
```

## Production Considerations

For production deployments:

1. **Use systemd** instead of cron (more reliable)
2. **Set up monitoring** with services like Datadog, New Relic, or UptimeRobot
3. **Configure log rotation** to prevent log files from growing too large
4. **Use a dedicated user** for running the sync (not root)
5. **Set up alerts** if syncs fail or take too long
6. **Consider load balancing** if you have multiple app servers

See `CRON_SETUP.md` for production deployment details.

## Support

If you encounter any issues:

1. Check the logs: `tail -100 logs/cron_sync.log`
2. Run the status checker: `./check_cron_status.sh`
3. Test manually: `./venv/bin/python cron_sync.py`
4. Verify `.env` configuration
5. Check Firebase credentials and network connectivity

## Summary

You now have:
- ✓ Automatic syncing every 2 minutes
- ✓ Manual refresh button still functional
- ✓ Real-time risk alerts
- ✓ Comprehensive logging
- ✓ Easy monitoring and troubleshooting tools

The "Last Sync" timestamp on your dashboard will now update automatically every 2 minutes, ensuring you never miss important messages!
