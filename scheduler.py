"""
Sends the weekly check-in message (email OR WhatsApp) to anyone whose
next_send_date is today or earlier, then pushes their next_send_date
7 days forward. Runs once a day, on its own — no one needs to visit
the site for this to fire.

Email requires:     SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL
WhatsApp requires:  TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
Both use:           SITE_URL

Gmail example:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your@gmail.com
  SMTP_PASS=<a 16-character Gmail "app password", not your normal login password>
  FROM_EMAIL=your@gmail.com

Twilio WhatsApp example (sandbox, for testing):
  TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  TWILIO_AUTH_TOKEN=your_auth_token
  TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

If credentials for a channel aren't set, that channel's job still runs but
just prints what it would have sent — nothing fails silently, but nothing
gets delivered either.
"""

import os
import smtplib
from datetime import date, timedelta
from email.mime.text import MIMEText
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

from db import SessionLocal, Reminder

SMTP_HOST: Optional[str] = os.environ.get("SMTP_HOST")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: Optional[str] = os.environ.get("SMTP_USER")
SMTP_PASS: Optional[str] = os.environ.get("SMTP_PASS")
FROM_EMAIL: str = os.environ.get("FROM_EMAIL") or SMTP_USER or ""
SITE_URL: str = os.environ.get("SITE_URL", "https://your-deployed-site.example.com")

TWILIO_ACCOUNT_SID: Optional[str] = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: Optional[str] = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM: Optional[str] = os.environ.get("TWILIO_WHATSAPP_FROM")  # e.g. "whatsapp:+14155238886"


def send_email(to_email: str) -> bool:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS):
        print(f"[reminder] SMTP not configured — would have emailed {to_email}")
        return False

    msg = MIMEText(
        f"Time for your weekly check-in.\n\n"
        f"Take two minutes to read your Mental Health Signal: {SITE_URL}"
    )
    msg["Subject"] = "Your weekly Mental Health Signal check-in"
    from_addr: str = FROM_EMAIL or ""
    msg["From"] = from_addr
    msg["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER or "", SMTP_PASS or "")
            server.sendmail(from_addr, [to_email], msg.as_string())
        print(f"[reminder] emailed {to_email}")
        return True
    except Exception as e:
        print(f"[reminder] failed to email {to_email}: {e}")
        return False


def send_whatsapp(to_number: str) -> bool:
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM):
        print(f"[reminder] Twilio not configured — would have WhatsApp'd {to_number}")
        return False

    try:
        from twilio.rest import Client  # imported lazily so email-only setups don't need it installed
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=to,
            body=f"Time for your weekly check-in. Read your Mental Health Signal: {SITE_URL}",
        )
        print(f"[reminder] WhatsApp sent to {to_number}")
        return True
    except Exception as e:
        print(f"[reminder] failed to WhatsApp {to_number}: {e}")
        return False


def run_daily_check():
    """Checks legacy SQLite reminders (if any exist)."""
    try:
        db = SessionLocal()
        try:
            today = date.today()
            due = db.query(Reminder).filter(Reminder.next_send_date <= today).all()
            for r in due:
                contact = str(r.contact)
                sent = send_whatsapp(contact) if r.channel == "whatsapp" else send_email(contact)
                if sent:
                    r.next_send_date = today + timedelta(days=7)  # type: ignore[assignment]
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[scheduler] SQLite daily check error: {e}")


def run_due_check():
    """Runs periodic check on MongoDB due reminders, plus legacy SQLite reminders."""
    try:
        from services.reminder_service import process_due_reminders
        count = process_due_reminders()
        if count > 0:
            print(f"[scheduler] Processed {count} due reminder(s) from MongoDB")
    except Exception as e:
        print(f"[scheduler] Error during MongoDB reminder check: {e}")

    # Backward compatibility with existing SQLite reminders
    try:
        run_daily_check()
    except Exception as e:
        pass


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Periodic check for MongoDB reminders due now (runs every 60 seconds)
    scheduler.add_job(run_due_check, "interval", seconds=60, id="due_reminders_check")
    # Daily check at 08:00
    scheduler.add_job(run_due_check, "cron", hour=8, minute=0, id="daily_check")
    scheduler.start()
    return scheduler
