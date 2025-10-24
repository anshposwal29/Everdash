from twilio.rest import Client
from config import Config
from datetime import datetime
import pytz


class TwilioService:
    """Service for sending SMS alerts via Twilio"""

    def __init__(self):
        self.account_sid = Config.TWILIO_ACCOUNT_SID
        self.auth_token = Config.TWILIO_AUTH_TOKEN
        self.from_number = Config.TWILIO_FROM_NUMBER
        self.admin_numbers = Config.TWILIO_ADMIN_NUMBERS
        self.client = None

        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)

    def send_risk_alert(self, user_firebase_id, risk_score, message_text):
        """
        Send SMS alert to study admins about high-risk message.
        """
        if not self.client or not self.admin_numbers:
            print("Warning: Twilio not configured or no admin numbers specified")
            return False

        # Get Eastern Time for the alert
        et_tz = pytz.timezone(Config.TIMEZONE)
        timestamp_et = datetime.now(et_tz).strftime('%Y-%m-%d %I:%M:%S %p %Z')

        # Construct alert message
        alert_text = (
            f"THERABOT ALERT\n"
            f"High-risk message detected!\n\n"
            f"User: {user_firebase_id}\n"
            f"Risk Score: {risk_score:.2f}\n"
            f"Time: {timestamp_et}\n\n"
            f"Message preview: {message_text[:100]}..."
        )

        success_count = 0
        failed_numbers = []

        # Send to each admin number
        for admin_number in self.admin_numbers:
            if not admin_number or admin_number.strip() == '':
                continue

            try:
                message = self.client.messages.create(
                    body=alert_text,
                    from_=self.from_number,
                    to=admin_number.strip()
                )
                print(f"Alert sent to {admin_number}: {message.sid}")
                success_count += 1
            except Exception as e:
                print(f"Failed to send alert to {admin_number}: {e}")
                failed_numbers.append(admin_number)

        if failed_numbers:
            print(f"Failed to send alerts to: {', '.join(failed_numbers)}")

        return success_count > 0

    def send_test_message(self, to_number):
        """Send a test message to verify Twilio configuration"""
        if not self.client:
            return False, "Twilio client not initialized"

        try:
            message = self.client.messages.create(
                body="This is a test message from Theradash. Your Twilio integration is working!",
                from_=self.from_number,
                to=to_number
            )
            return True, f"Test message sent successfully. SID: {message.sid}"
        except Exception as e:
            return False, f"Failed to send test message: {str(e)}"


# Singleton instance
twilio_service = TwilioService()
