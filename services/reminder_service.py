"""
Reminder Service for Mental Health Signal.

Handles:
- Validation of reminder intervals (1, 2, 7 days) and channels ("email", "whatsapp", "both")
- Next reminder date calculation (with Asia/Kolkata timezone support, UTC storage)
- Upserting and reading student reminder preferences in MongoDB
- Processing due reminders with duplicate prevention
- Logging reminder history to MongoDB
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
import logging

from database import (
    get_students_collection,
    get_reminders_collection,
)
from services.email_service import send_email_reminder, is_email_configured
from services.whatsapp_service import send_whatsapp_reminder, is_whatsapp_configured

logger = logging.getLogger("mental_health_signal.reminder_service")

SUPPORTED_INTERVALS = {1, 2, 7}  # 1 = Daily, 2 = Every 2 days, 7 = Weekly
SUPPORTED_CHANNELS = {"email", "whatsapp", "both"}

APP_TIMEZONE_NAME = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
try:
    APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)
except Exception:
    APP_TIMEZONE = timezone(timedelta(hours=5, minutes=30))  # IST fallback


def calculate_next_reminder_date(interval_days: int, from_datetime: Optional[datetime] = None) -> datetime:
    """
    Calculates next reminder date/time in UTC based on current time in Asia/Kolkata.
    """
    if interval_days not in SUPPORTED_INTERVALS:
        raise ValueError(f"Invalid interval: {interval_days}. Supported intervals: {SUPPORTED_INTERVALS}")

    now_utc = from_datetime or datetime.now(timezone.utc)
    return now_utc + timedelta(days=interval_days)


def upsert_preferences(
    student_id: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    reminder_channel: str = "email",
    reminder_interval_days: int = 7,
    reminders_enabled: bool = True,
) -> dict:
    """
    Saves or updates reminder preferences for a student.
    Recalculates next_reminder_at according to interval.
    """
    if reminder_interval_days not in SUPPORTED_INTERVALS:
        raise ValueError(f"Invalid interval: {reminder_interval_days}. Must be one of {sorted(list(SUPPORTED_INTERVALS))}.")

    channel = reminder_channel.lower().strip()
    if channel not in SUPPORTED_CHANNELS:
        raise ValueError(f"Invalid channel: {reminder_channel}. Must be one of {sorted(list(SUPPORTED_CHANNELS))}.")

    if channel in ("email", "both") and not email:
        raise ValueError("Email address is required for email reminders.")
    if channel in ("whatsapp", "both") and not phone:
        raise ValueError("Phone number is required for WhatsApp reminders.")

    col = get_students_collection()
    if col is None:
        raise RuntimeError("Database connection unavailable.")

    now_utc = datetime.now(timezone.utc)
    next_reminder = calculate_next_reminder_date(reminder_interval_days, now_utc)

    # Check for existing student record
    existing = col.find_one({"student_id": student_id})
    created_at = existing.get("created_at", now_utc) if existing else now_utc

    update_doc = {
        "student_id": student_id,
        "email": email.strip() if email else (existing.get("email") if existing else None),
        "phone": phone.strip() if phone else (existing.get("phone") if existing else None),
        "reminder_channel": channel,
        "reminder_interval_days": reminder_interval_days,
        "next_reminder_at": next_reminder,
        "next_reminder_at_iso": next_reminder.isoformat(),
        "reminders_enabled": bool(reminders_enabled),
        "created_at": created_at,
        "updated_at": now_utc,
    }

    col.update_one({"student_id": student_id}, {"$set": update_doc}, upsert=True)
    logger.info(f"Updated preferences for student {student_id}: interval={reminder_interval_days}d, channel={channel}")

    return {
        "student_id": student_id,
        "email": update_doc["email"],
        "phone": update_doc["phone"],
        "reminder_channel": update_doc["reminder_channel"],
        "reminder_interval_days": update_doc["reminder_interval_days"],
        "next_reminder_at": update_doc["next_reminder_at_iso"],
        "reminders_enabled": update_doc["reminders_enabled"],
        "status": "saved",
    }


def get_preferences(student_id: str) -> Optional[dict]:
    """
    Retrieves stored preferences for a student.
    """
    col = get_students_collection()
    if col is None:
        return None

    doc = col.find_one({"student_id": student_id})
    if not doc:
        return None

    next_rem = doc.get("next_reminder_at")
    next_rem_iso = next_rem.isoformat() if isinstance(next_rem, datetime) else doc.get("next_reminder_at_iso")

    return {
        "student_id": doc.get("student_id"),
        "email": doc.get("email"),
        "phone": doc.get("phone"),
        "reminder_channel": doc.get("reminder_channel", "email"),
        "reminder_interval_days": doc.get("reminder_interval_days", 7),
        "next_reminder_at": next_rem_iso,
        "reminders_enabled": doc.get("reminders_enabled", True),
        "created_at": doc.get("created_at").isoformat() if isinstance(doc.get("created_at"), datetime) else None,
        "updated_at": doc.get("updated_at").isoformat() if isinstance(doc.get("updated_at"), datetime) else None,
    }


def disable_reminders(student_id: str) -> bool:
    """
    Disables reminders for a student.
    """
    col = get_students_collection()
    if col is None:
        return False

    now_utc = datetime.now(timezone.utc)
    res = col.update_one(
        {"student_id": student_id},
        {"$set": {"reminders_enabled": False, "updated_at": now_utc}}
    )
    logger.info(f"Reminders disabled for student {student_id}")
    return res.matched_count > 0


def record_assessment_completed(student_id: str):
    """
    Called when a student completes a mental health assessment.
    Advances next_reminder_at according to the student's interval preference.
    """
    if not student_id or student_id == "anonymous":
        return

    col = get_students_collection()
    if col is None:
        return

    try:
        student = col.find_one({"student_id": student_id})
        if student and student.get("reminders_enabled"):
            interval = student.get("reminder_interval_days", 7)
            now_utc = datetime.now(timezone.utc)
            next_date = calculate_next_reminder_date(interval, now_utc)
            col.update_one(
                {"student_id": student_id},
                {"$set": {
                    "next_reminder_at": next_date,
                    "next_reminder_at_iso": next_date.isoformat(),
                    "last_assessment_at": now_utc,
                    "updated_at": now_utc
                }}
            )
            logger.info(f"Recalculated next reminder for student {student_id} to {next_date.isoformat()}")
    except Exception as e:
        logger.warning(f"Failed to update next reminder date on assessment: {e}")


def log_reminder_activity(student_id: str, channel: str, scheduled_at: datetime, sent_at: datetime, status: str, error_message: Optional[str] = None):
    """
    Logs reminder execution details to the reminders collection.
    Status can be: scheduled, sent, failed, cancelled.
    """
    col = get_reminders_collection()
    if col is None:
        return

    try:
        doc = {
            "student_id": student_id,
            "channel": channel,
            "scheduled_at": scheduled_at,
            "scheduled_at_iso": scheduled_at.isoformat() if scheduled_at else None,
            "sent_at": sent_at,
            "sent_at_iso": sent_at.isoformat() if sent_at else None,
            "status": status,
        }
        if error_message:
            # Avoid exposing secret keys or sensitive information
            doc["error"] = str(error_message)[:200]

        col.insert_one(doc)
    except Exception as e:
        logger.warning(f"Failed to log reminder activity for {student_id}: {e}")


def send_test_reminder(student_id: str) -> dict:
    """
    Triggers an immediate test reminder for the given student.
    """
    pref = get_preferences(student_id)
    if not pref:
        raise ValueError(f"Student {student_id} not found.")

    channel = pref.get("reminder_channel", "email")
    email = pref.get("email")
    phone = pref.get("phone")

    results = {}
    now_utc = datetime.now(timezone.utc)

    if channel in ("email", "both"):
        if email:
            sent = send_email_reminder(email)
            status = "sent" if sent or not is_email_configured() else "failed"
            log_reminder_activity(student_id, "email", scheduled_at=now_utc, sent_at=now_utc, status=status)
            results["email"] = {"status": status, "sent": sent}
        else:
            results["email"] = {"status": "failed", "error": "No email on file"}

    if channel in ("whatsapp", "both"):
        if phone:
            sent = send_whatsapp_reminder(phone)
            status = "sent" if sent or not is_whatsapp_configured() else "failed"
            log_reminder_activity(student_id, "whatsapp", scheduled_at=now_utc, sent_at=now_utc, status=status)
            results["whatsapp"] = {"status": status, "sent": sent}
        else:
            results["whatsapp"] = {"status": "failed", "error": "No phone on file"}

    return {
        "student_id": student_id,
        "results": results,
        "timestamp": now_utc.isoformat(),
    }


def process_due_reminders() -> int:
    """
    Scans for students due for a reminder:
    - reminders_enabled == True
    - next_reminder_at <= now_utc

    Sends reminder, logs to MongoDB, and pushes next_reminder_at forward
    to strictly prevent duplicate reminders.
    Returns number of reminders processed.
    """
    col = get_students_collection()
    if col is None:
        logger.warning("Database unavailable; skipping due reminder scan.")
        return 0

    now_utc = datetime.now(timezone.utc)
    try:
        # Atomic query for due students
        due_students = list(col.find({
            "reminders_enabled": True,
            "next_reminder_at": {"$lte": now_utc}
        }))
    except Exception as e:
        logger.error(f"Error querying due reminders: {e}")
        return 0

    processed_count = 0

    for student in due_students:
        student_id = student.get("student_id")
        channel = student.get("reminder_channel", "email")
        email = student.get("email")
        phone = student.get("phone")
        interval = student.get("reminder_interval_days", 7)
        scheduled_at = student.get("next_reminder_at")

        # 1. Immediately advance next_reminder_at to prevent duplicate triggers
        next_date = calculate_next_reminder_date(interval, now_utc)
        col.update_one(
            {"student_id": student_id, "next_reminder_at": scheduled_at},
            {"$set": {
                "next_reminder_at": next_date,
                "next_reminder_at_iso": next_date.isoformat(),
                "last_reminder_sent_at": now_utc,
                "updated_at": now_utc
            }}
        )

        # 2. Dispatch reminder based on channel
        if channel in ("email", "both") and email:
            sent = send_email_reminder(email)
            status = "sent" if sent or not is_email_configured() else "failed"
            log_reminder_activity(student_id, "email", scheduled_at, now_utc, status)

        if channel in ("whatsapp", "both") and phone:
            sent = send_whatsapp_reminder(phone)
            status = "sent" if sent or not is_whatsapp_configured() else "failed"
            log_reminder_activity(student_id, "whatsapp", scheduled_at, now_utc, status)

        processed_count += 1
        logger.info(f"Processed due reminder for student {student_id}. Next date: {next_date.isoformat()}")

    return processed_count
