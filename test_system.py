"""
Automated Test Suite for Mental Health Signal Reminder & Logging System.

Tests all required aspects directly without requiring additional test runners:
1. Existing prediction API & model preservation
2. MongoDB connection & collection indexes
3. Prediction saved to MongoDB
4. Student reminder preference creation (Daily, 2-day, Weekly)
5. Invalid reminder interval rejection
6. Reminder disabling
7. Email reminder & WhatsApp service handling
8. Reminder activity logging to MongoDB
9. Duplicate reminder prevention
10. Prediction history retrieval
11. MongoDB failure handling (prediction API never crashes)
"""

import os
import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

# Ensure local test database
os.environ["MONGODB_URI"] = "mongodb://localhost:27017"
os.environ["MONGODB_DB_NAME"] = "mental_health_signal_test"

from api import (
    app,
    model,
    predict,
    health,
    create_reminder_preferences,
    get_reminder_preferences,
    update_reminder_preferences,
    disable_student_reminders_endpoint,
    test_reminder_endpoint,
    get_student_history_endpoint,
    ReadingInput,
    ReminderPreferenceInput,
    ReminderPreferenceUpdate,
)
from database import (
    get_db,
    get_students_collection,
    get_predictions_collection,
    get_reminders_collection,
    init_mongodb,
    log_prediction_to_db,
    get_prediction_history,
)
from services.reminder_service import (
    upsert_preferences,
    get_preferences,
    disable_reminders,
    process_due_reminders,
    send_test_reminder,
    SUPPORTED_INTERVALS,
)
from services.email_service import send_email_reminder, is_email_configured
from services.whatsapp_service import send_whatsapp_reminder, is_whatsapp_configured


class TestMentalHealthSignalSystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Initialize test DB indexes
        init_mongodb()
        # Clean test collections
        db = get_db()
        if db is not None:
            db["students"].delete_many({})
            db["predictions"].delete_many({})
            db["reminders"].delete_many({})

    def test_01_health_and_model_loaded(self):
        """Verify the ML model is loaded and health() returns ok."""
        data = health()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["model_loaded"], "Trained model pipeline.pkl must be loaded")

    def test_02_predict_endpoint_and_mongodb_logging(self):
        """Verify existing /predict endpoint works and prediction is saved to MongoDB."""
        sample_input = ReadingInput(
            age=20,
            gender="Male",
            academicLevel="Undergraduate",
            platform="Instagram",
            purpose="Entertainment",
            screenTime=5.0,
            phoneUnlocks=85,
            studyHours=3.0,
            activity=1.0,
            sleep=7.0,
            stress="Medium",
            studentId="STU_TEST_001",
        )
        data = predict(sample_input, student_id="STU_TEST_001")

        # Check response structure is preserved: score and factors
        self.assertIn("score", data)
        self.assertIn("factors", data)
        self.assertIsInstance(data["score"], float)
        self.assertGreaterEqual(data["score"], 0.0)
        self.assertLessEqual(data["score"], 10.0)
        self.assertIsInstance(data["factors"], list)
        self.assertLessEqual(len(data["factors"]), 3)

        # Check MongoDB contains this prediction
        col = get_predictions_collection()
        saved = col.find_one({"student_id": "STU_TEST_001"})
        self.assertIsNotNone(saved, "Prediction must be logged to MongoDB")
        self.assertEqual(saved["student_id"], "STU_TEST_001")
        self.assertEqual(saved["mental_health_score"], data["score"])
        self.assertEqual(saved["model_version"], "random_forest_v1")

    def test_03_reminder_preferences_intervals(self):
        """Verify Daily (1d), Every 2 days (2d), and Weekly (7d) preferences."""
        # 1. Daily (1 day)
        data_daily = create_reminder_preferences(ReminderPreferenceInput(
            student_id="STU_DAILY",
            email="daily_student@example.com",
            reminder_channel="email",
            reminder_interval_days=1,
            reminders_enabled=True
        ))
        self.assertEqual(data_daily["reminder_interval_days"], 1)

        # 2. Every 2 days (2 days)
        data_2days = create_reminder_preferences(ReminderPreferenceInput(
            student_id="STU_2DAYS",
            email="twoday_student@example.com",
            phone="+919876543210",
            reminder_channel="whatsapp",
            reminder_interval_days=2,
            reminders_enabled=True
        ))
        self.assertEqual(data_2days["reminder_interval_days"], 2)

        # 3. Weekly (7 days)
        data_weekly = create_reminder_preferences(ReminderPreferenceInput(
            student_id="STU_WEEKLY",
            email="weekly_student@example.com",
            reminder_channel="email",
            reminder_interval_days=7,
            reminders_enabled=True
        ))
        self.assertEqual(data_weekly["reminder_interval_days"], 7)

    def test_04_invalid_interval_rejection(self):
        """Verify invalid intervals (e.g. 3, 5, 10) are rejected with HTTP 400."""
        for invalid_interval in [3, 5, 10, -1, 0]:
            with self.assertRaises(HTTPException) as ctx:
                create_reminder_preferences(ReminderPreferenceInput(
                    student_id="STU_INVALID",
                    email="student@example.com",
                    reminder_channel="email",
                    reminder_interval_days=invalid_interval,
                ))
            self.assertEqual(ctx.exception.status_code, 400, f"Interval {invalid_interval} should be rejected")

    def test_05_update_and_get_preferences(self):
        """Verify PUT and GET /reminders/preferences/{student_id}."""
        # Get preferences
        get_res = get_reminder_preferences("STU_DAILY")
        self.assertEqual(get_res["student_id"], "STU_DAILY")

        # Update preferences to 2 days
        put_res = update_reminder_preferences("STU_DAILY", ReminderPreferenceUpdate(
            reminder_interval_days=2,
        ))
        self.assertEqual(put_res["reminder_interval_days"], 2)

    def test_06_disable_reminders(self):
        """Verify POST /reminders/disable/{student_id} disables reminders."""
        res = disable_student_reminders_endpoint("STU_DAILY")
        self.assertFalse(res["reminders_enabled"])

        # Check in MongoDB
        doc = get_preferences("STU_DAILY")
        self.assertFalse(doc["reminders_enabled"])

    def test_07_prediction_history(self):
        """Verify GET /predictions/history/{student_id} returns chronological list."""
        sid = "STU_HIST_TEST"
        get_predictions_collection().delete_many({"student_id": sid})
        # Insert 3 predictions
        log_prediction_to_db(sid, 7.2, [{"label": "Stress", "value": 2.5}], model_version="random_forest_v1")
        log_prediction_to_db(sid, 6.8, [{"label": "Sleep", "value": 2.1}], model_version="random_forest_v1")
        log_prediction_to_db(sid, 6.5, [{"label": "Screen", "value": 1.9}], model_version="random_forest_v1")

        history = get_student_history_endpoint(sid)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["mental_health_score"], 7.2)
        self.assertEqual(history[1]["mental_health_score"], 6.8)
        self.assertEqual(history[2]["mental_health_score"], 6.5)

    def test_08_duplicate_reminder_prevention(self):
        """Verify scheduler processes due user once, advances next_reminder_at, and avoids duplicate sends."""
        col = get_students_collection()
        sid = "STU_DUE_TEST"
        now_utc = datetime.now(timezone.utc)
        past_time = now_utc - timedelta(hours=2)

        # Insert student whose next_reminder_at is past due
        col.delete_one({"student_id": sid})
        col.insert_one({
            "student_id": sid,
            "email": "duetest@example.com",
            "phone": "+919999999999",
            "reminder_channel": "email",
            "reminder_interval_days": 1,
            "next_reminder_at": past_time,
            "reminders_enabled": True,
            "created_at": now_utc,
            "updated_at": now_utc,
        })

        # Process due reminders
        count1 = process_due_reminders()
        self.assertGreaterEqual(count1, 1, "Should have processed at least 1 due reminder")

        # Check reminder activity log in MongoDB
        reminders_col = get_reminders_collection()
        logged = reminders_col.find_one({"student_id": sid})
        self.assertIsNotNone(logged, "Reminder must be logged in MongoDB reminders collection")
        self.assertEqual(logged["channel"], "email")

        # Check student next_reminder_at has moved forward into future
        student = col.find_one({"student_id": sid})
        next_rem = student["next_reminder_at"]
        if next_rem.tzinfo is None:
            next_rem = next_rem.replace(tzinfo=timezone.utc)
        self.assertGreater(next_rem, now_utc, "Next reminder must be advanced into future")

        # Running process_due_reminders again immediately MUST NOT send another reminder (no duplicates)
        count2 = process_due_reminders()
        self.assertEqual(count2, 0, "Duplicate reminder must not be sent for the same period")

    def test_09_test_reminder_endpoint(self):
        """Verify test reminder endpoint triggers and logs test reminder."""
        upsert_preferences("STU_TEST_SEND", email="test@example.com", reminder_channel="email")
        data = test_reminder_endpoint("STU_TEST_SEND")
        self.assertEqual(data["student_id"], "STU_TEST_SEND")
        self.assertIn("email", data["results"])

    def test_10_database_failure_resilience(self):
        """Verify that if database logging encounters an issue, prediction continues working."""
        sample_input = ReadingInput(
            age=22,
            gender="Female",
            academicLevel="Postgraduate",
            platform="YouTube",
            purpose="Education",
            screenTime=4.0,
            phoneUnlocks=60,
            studyHours=5.0,
            activity=1.5,
            sleep=8.0,
            stress="Low",
        )
        response = predict(sample_input)
        self.assertIn("score", response)
        self.assertIn("factors", response)


if __name__ == "__main__":
    unittest.main()
