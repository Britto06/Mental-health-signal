"""
WhatsApp Reminder Service for Mental Health Signal.

Sends simple, non-diagnostic check-in reminder WhatsApp messages using Twilio.
Environment variables used:
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_WHATSAPP_NUMBER or TWILIO_WHATSAPP_FROM
  SITE_URL
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("mental_health_signal.whatsapp_service")


def _get_env():
    return {
        "sid": os.environ.get("TWILIO_ACCOUNT_SID", ""),
        "token": os.environ.get("TWILIO_AUTH_TOKEN", ""),
        "from_num": os.environ.get("TWILIO_WHATSAPP_NUMBER") or os.environ.get("TWILIO_WHATSAPP_FROM", ""),
        "site_url": os.environ.get("SITE_URL", "https://mental-health-signal.onrender.com"),
    }


WHATSAPP_BODY_TEMPLATE = """Mental Health Signal Reminder
It's time for your scheduled mental health check-in.
Please open the application and complete your assessment:
{site_url}

This is an educational predictive tool and is not a medical diagnosis.
If reminders are no longer needed, you can disable them in your preferences."""


def is_whatsapp_configured() -> bool:
    env = _get_env()
    sid = env["sid"].strip()
    token = env["token"].strip()
    from_num = env["from_num"].strip()

    if not (sid and token and from_num):
        return False
    # Check for unconfigured template / placeholder values
    if "xxxxxxxx" in sid.lower() or "your_" in token.lower() or "placeholder" in token.lower():
        return False
    return True


def format_whatsapp_number(number: str) -> str:
    """Ensure number is formatted with the whatsapp: prefix."""
    if not number:
        return ""
    cleaned = str(number).strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("whatsapp:"):
        return cleaned
    return f"whatsapp:{cleaned}"


def send_whatsapp_reminder(to_number: str) -> bool:
    """
    Sends a WhatsApp check-in reminder message.
    Returns True if sent, False if unconfigured or failed.
    Never exposes auth token or credentials in logs.
    """
    if not to_number:
        logger.warning("[whatsapp] Cannot send reminder: recipient number is empty")
        return False

    if not is_whatsapp_configured():
        logger.info(f"[whatsapp] Twilio not configured — simulated WhatsApp sent to {to_number}")
        return False

    env = _get_env()
    try:
        from twilio.rest import Client
        client = Client(env["sid"], env["token"])
        to_addr = format_whatsapp_number(to_number)
        from_addr = format_whatsapp_number(env["from_num"])

        message_body = WHATSAPP_BODY_TEMPLATE.format(site_url=env["site_url"])
        client.messages.create(
            from_=from_addr,
            to=to_addr,
            body=message_body,
        )
        logger.info(f"[whatsapp] Reminder successfully sent to {to_number}")
        return True
    except Exception as e:
        logger.error(f"[whatsapp] Failed to send WhatsApp reminder to {to_number}: {e}")
        return False
