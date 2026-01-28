"""
Email Service for Theradash

This module provides manual email sending functionality for RAs to communicate
with study participants. It uses Microsoft Graph API (OAuth2) for sending emails.
"""

import os
import re
import msal
import requests
import json
from datetime import datetime

# OAuth2 settings (same as auto_compliance_email.py)
CLIENT_ID = '9d05976b-2ab6-4415-84a0-6d9c077babb6'
TENANT_ID = '995b0936-48d6-40e5-a31e-bf689ec9446f'
AUTHORITY = f'https://login.microsoftonline.com/{TENANT_ID}'
SCOPES = ['https://graph.microsoft.com/Mail.Send']
CACHE_FILE = 'token_cache.bin'

# Email templates for manual sending
EMAIL_TEMPLATES = {
    'great_job': {
        'name': 'Great Job',
        'subject': 'Great Job with Therabot!',
        'description': 'Positive feedback for consistent daily engagement',
        'body': """\
Hello {first_name},<br><br>
It's {ra_first_name} from the Dartmouth Therabot Team. I wanted to reach out and let you know that you've been doing a great job interacting with Therabot consistently! We really appreciate your dedication to the study.<br><br>
Keep up the excellent work! Your engagement helps us better understand how Therabot can support mental health, and we're grateful for your participation.<br><br>
If you have any questions or feedback about your experience, please don't hesitate to reach out to us at (603) 646-7015 or therabot@dartmouth.edu.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""
    },
    'needs_improvement': {
        'name': 'Needs Improvement',
        'subject': 'Therabot Study Team Checking In',
        'description': 'Reminder for participants who have missed 2-3 days',
        'body': """\
Hello {first_name},<br><br>
It's {ra_first_name} getting in touch from the Dartmouth Therabot Team. I've noticed that you haven't been interacting much with Therabot over the past few days. We ask that you please interact with the Therabot app for at least five minutes each day.<br><br>
Regular interaction with Therabot is an important part of the study, and we want to make sure you're getting the most out of your participation. If there's anything preventing you from using the app, or if you're experiencing any technical issues, please let us know and we'll be happy to help.<br><br>
If you need any assistance, please don't hesitate to reach out to us at (603) 646-7015 or therabot@dartmouth.edu.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""
    },
    'never_logged_in': {
        'name': 'Never Logged In',
        'subject': 'Therabot App - Getting Started',
        'description': 'Welcome email with login credentials for participants who haven\'t logged in yet',
        'body': """\
Hello {first_name},<br><br>
It's {ra_first_name} getting in touch from the Dartmouth Therabot Team. We noticed that you haven't logged into the Therabot app yet. We wanted to reach out to make sure you have everything you need to get started.<br><br>
<strong>Your Login Credentials:</strong><br>
Username: {username}<br>
Password: {password}<br><br>
<strong>Download Instructions:</strong><br>
Please look for an email sent from Firebase that includes a link to download the app.<br><br>
<strong>For iPhone/iPad Users - Additional Steps:</strong><br>
After downloading the app, you will need to trust the developer certificate:<br>
<ol>
<li>Open <strong>Settings</strong> on your iPhone</li>
<li>Go to <strong>General > VPN & Device Management</strong></li>
<li>Under "Enterprise App," tap <strong>Dartmouth College</strong></li>
<li>Tap <strong>Trust "Dartmouth College"</strong> and confirm by tapping Trust</li>
<li>You may need to restart your phone after this step</li>
</ol>
<br>
Once you've downloaded the app, please log in using the credentials above and start interacting with Therabot. We ask that you please interact with the Therabot app for at least five minutes each day.<br><br>
If you need any assistance or have trouble logging in, please don't hesitate to reach out to us at (603) 646-7015 or therabot@dartmouth.edu.<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""
    },
    'custom': {
        'name': 'Custom Email',
        'subject': 'Message from Therabot Study Team',
        'description': 'Write a custom email message',
        'body': """\
Hello {first_name},<br><br>
{custom_message}<br><br>
Thank you so much,<br>
{ra_first_name}<br>
Mental Health Therabot Study Team<br>
(603) 646-7015 (call or text!)<br>
therabot@dartmouth.edu<br><br>
Our Lab's Website: https://geiselmed.dartmouth.edu/jacobsonlab/
"""
    }
}

# Email from address
EMAIL_FROM_ADDRESS = os.environ.get('EMAIL_FROM_ADDRESS', 'therabot@dartmouth.edu')


def get_access_token():
    """Handles the OAuth2 token acquisition and caching."""
    cache = msal.SerializableTokenCache()
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            cache.deserialize(f.read())

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache
    )

    # Try to get token silently from cache
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # If no valid token in cache, return None (need to re-authenticate)
    if not result:
        return None

    # Save the cache if it changed
    if cache.has_state_changed:
        with open(CACHE_FILE, "w") as f:
            f.write(cache.serialize())

    if "access_token" in result:
        return result['access_token']
    return None


def send_email(to_email, subject, html_body):
    """Send email via Microsoft Graph API."""
    try:
        token = get_access_token()
        if not token:
            return False, "OAuth token not available. Please run auto_compliance_email.py to authenticate first."

        endpoint = "https://graph.microsoft.com/v1.0/me/sendMail"

        email_data = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to_email
                        }
                    }
                ]
            },
            "saveToSentItems": "true"
        }

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        response = requests.post(endpoint, headers=headers, json=email_data)

        if response.status_code == 202:
            return True, "Email sent successfully"
        else:
            return False, f"Graph API Error {response.status_code}: {response.text}"

    except Exception as e:
        return False, f"Failed to send email: {str(e)}"


def get_email_templates():
    """Return available email templates."""
    templates = []
    for key, template in EMAIL_TEMPLATES.items():
        templates.append({
            'id': key,
            'name': template['name'],
            'subject': template['subject'],
            'description': template['description']
        })
    return templates


def get_template_body(template_id):
    """Get the body of a specific template."""
    if template_id in EMAIL_TEMPLATES:
        return EMAIL_TEMPLATES[template_id]['body']
    return None


def get_template_subject(template_id):
    """Get the subject of a specific template."""
    if template_id in EMAIL_TEMPLATES:
        return EMAIL_TEMPLATES[template_id]['subject']
    return None


def format_email_body(template_id, first_name, ra_first_name, username=None, password=None, custom_message=None):
    """Format the email body with the given parameters."""
    body = get_template_body(template_id)
    if not body:
        return None

    # Replace placeholders
    body = body.replace('{first_name}', first_name or 'Participant')
    body = body.replace('{ra_first_name}', ra_first_name or 'The Research Team')

    if username:
        body = body.replace('{username}', username)
    if password:
        body = body.replace('{password}', password)
    if custom_message:
        body = body.replace('{custom_message}', custom_message)

    return body


def get_from_address():
    """Get the email from address."""
    return EMAIL_FROM_ADDRESS
