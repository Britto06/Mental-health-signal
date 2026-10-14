"""
Email Reminder Service for Mental Health Signal.

Sends simple, non-diagnostic check-in reminder emails to students.
Environment variables used:
  SMTP_HOST
  SMTP_PORT
  SMTP_USERNAME or SMTP_USER
  SMTP_PASSWORD or SMTP_PASS
  FROM_EMAIL
  SITE_URL
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("mental_health_signal.email_service")


def _get_email_config():
    return {
        "host": os.environ.get("SMTP_HOST", ""),
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ.get("SMTP_USERNAME") or os.environ.get("SMTP_USER", ""),
        "password": os.environ.get("SMTP_PASSWORD") or os.environ.get("SMTP_PASS", ""),
        "from_email": os.environ.get("FROM_EMAIL") or os.environ.get("SMTP_USERNAME") or os.environ.get("SMTP_USER", ""),
        "site_url": os.environ.get("SITE_URL", "https://mental-health-signal.onrender.com"),
    }


EMAIL_SUBJECT = "Your Mental Health Check-In Reminder"

EMAIL_BODY_TEMPLATE = """Hello,

This is a reminder to complete your scheduled mental health check-in.
Regular check-ins can help you keep track of changes over time.
Please open the application and complete your assessment:
{site_url}

This is an educational predictive tool and is not a medical diagnosis or professional mental-health assessment.
If you no longer want to receive reminders, you can disable them in your preferences.

Regards,
Mental Health Signal
"""


def is_email_configured() -> bool:
    cfg = _get_email_config()
    host = cfg["host"].strip()
    user = cfg["user"].strip()
    pw = cfg["password"].strip()
    if not (host and user and pw):
        return False
    # Check for placeholder values
    if "your@" in user.lower() or "your-16-character" in pw.lower():
        return False
    return True


def send_email_reminder(to_email: str) -> bool:
    """
    Sends a check-in reminder email.
    Returns True if sent successfully, False otherwise.
    Never raises an uncaught exception and never logs passwords.
    """
    if not is_email_configured():
        logger.info(f"[email] SMTP not configured — simulated email sent to {to_email}")
        return False

    cfg = _get_email_config()
    body = EMAIL_BODY_TEMPLATE.format(site_url=cfg["site_url"])
    msg = MIMEText(body)
    msg["Subject"] = EMAIL_SUBJECT
    msg["From"] = cfg["from_email"] or "noreply@mentalhealthsignal.org"
    msg["To"] = to_email

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=10) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(msg["From"], [to_email], msg.as_string())
        logger.info(f"[email] Reminder successfully sent to {to_email}")
        return True
    except Exception as e:
        # Log error message safely without exposing SMTP credentials
        logger.error(f"[email] Failed to send reminder email to {to_email}: {e}")
        return False
