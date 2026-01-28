#!/usr/bin/env python3
"""
Cron job script for automated data synchronization.
This script can be run every 2 minutes via cron to keep data in sync.

Usage:
    python cron_sync.py

Cron schedule example (every 2 minutes):
    */2 * * * * cd /path/to/theradash && /path/to/python cron_sync.py >> /var/log/theradash_sync.log 2>&1
"""

import sys
import os
from datetime import datetime

# Add the project directory to the path
project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_dir)

# Import app and required services
from app import app
from services.sync_service import sync_service

def main():
    """Run the sync process"""
    print(f"\n{'='*80}")
    print(f"Starting automated sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")

    try:
        # Run sync within Flask app context
        with app.app_context():
            result = sync_service.full_sync()

            if result['success']:
                print(f"\n✓ Sync completed successfully!")
                print(f"  - Users synced: {result['users_synced']}")
                print(f"  - Conversations synced: {result['conversations_synced']}")
                print(f"  - Messages synced: {result['messages_synced']}")
                print(f"  - Alerts sent: {result['alerts_sent']}")
                print(f"  - Duration: {result['duration']:.2f} seconds")
                return 0
            else:
                print(f"\n✗ Sync failed: {result.get('error', 'Unknown error')}")
                return 1

    except Exception as e:
        print(f"\n✗ Error during sync: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        print(f"\n{'='*80}")
        print(f"Sync finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
