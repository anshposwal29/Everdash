#!/usr/bin/env python3
"""
Run this script to add timestamps to all messages in mock_database.json
Usage: python add_timestamps_to_mock.py
"""

import json
from datetime import datetime, timedelta

# Read the current data
with open('mock_database.json', 'r') as f:
    data = json.load(f)

print(f"Processing {len(data['participants'])} participants...")

# Add timestamps to all messages in all conversations
for user in data['participants']:
    if 'conversations' not in user:
        print(f"  {user['user_id']}: No conversations")
        continue
    
    # Start from now and work backwards for each conversation
    conv_time = datetime.now()
    
    for conv_idx, conv in enumerate(user['conversations']):
        conv_time = conv_time - timedelta(hours=conv_idx * 3)
        
        if 'messages' not in conv:
            continue
            
        for msg_idx, msg in enumerate(conv['messages']):
            msg_time = conv_time - timedelta(minutes=msg_idx * 2)
            # Add timestamp as ISO string
            msg['timestamp'] = msg_time.isoformat()
    
    print(f"  {user['user_id']}: Added timestamps to {len(user['conversations'])} conversation(s)")

# Save it back
with open('mock_database.json', 'w') as f:
    json.dump(data, f, indent=2)

print("\n✅ Successfully added timestamps to all messages in mock_database.json")
print("Now restart your Flask app and try again!")

