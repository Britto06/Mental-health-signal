"""
MongoDB Database Integration for Mental Health Signal.

Provides connections, collection helpers, indexing, and safe logging
for students, predictions, and reminders.
"""

import os
from datetime import datetime, timezone
from typing import Optional
import logging
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

load_dotenv()

logger = logging.getLogger("mental_health_signal.database")

_client = None
_db = None


def get_mongo_client():
    global _client
    if _client is None:
        try:
            uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
            # Set a 3-second server selection timeout to avoid blocking if MongoDB is unreachable
            _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        except Exception as e:
            logger.error(f"Failed to initialize MongoClient: {e}")
            return None
    return _client


def get_db():
    global _db
    if _db is not None:
        return _db
    client = get_mongo_client()
    if client is not None:
        try:
            db_name = os.environ.get("MONGODB_DB_NAME", "mental_health_signal")
            _db = client[db_name]
            return _db
        except Exception as e:
            logger.error(f"Failed to access database: {e}")
    return None


def get_students_collection():
    db = get_db()
    return db["students"] if db is not None else None


def get_predictions_collection():
    db = get_db()
    return db["predictions"] if db is not None else None


def get_reminders_collection():
    db = get_db()
    return db["reminders"] if db is not None else None


def init_mongodb():
    """
    Initializes indexes on MongoDB collections.
    Does not crash if MongoDB is temporarily down.
    """
    try:
        db = get_db()
        if db is None:
            logger.warning("MongoDB unavailable during init_mongodb; indexes skipped.")
            return False

        # 1. students collection indexes
        students = db["students"]
        students.create_index([("student_id", ASCENDING)], unique=True, sparse=True)
        students.create_index([("reminders_enabled", ASCENDING), ("next_reminder_at", ASCENDING)])
        students.create_index([("email", ASCENDING)], sparse=True)
        students.create_index([("phone", ASCENDING)], sparse=True)

        # 2. predictions collection indexes
        predictions = db["predictions"]
        predictions.create_index([("student_id", ASCENDING), ("prediction_date", DESCENDING)])
        predictions.create_index([("prediction_date", DESCENDING)])

        # 3. reminders collection indexes
        reminders = db["reminders"]
        reminders.create_index([("student_id", ASCENDING), ("sent_at", DESCENDING)])
        reminders.create_index([("status", ASCENDING)])

        logger.info("MongoDB indexes verified successfully.")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize MongoDB indexes: {e}")
        return False


def log_prediction_to_db(student_id: str, score: float, factors: Optional[list] = None, inputs: Optional[dict] = None, model_version: str = "random_forest_v1") -> bool:
    """
    Saves a prediction document to the predictions collection.
    Gracefully catches any database errors so prediction API remains 100% available.
    """
    try:
        col = get_predictions_collection()
        if col is None:
            logger.warning("Predictions collection unavailable; skipping log.")
            return False

        now_utc = datetime.now(timezone.utc)
        doc = {
            "student_id": student_id or "anonymous",
            "mental_health_score": round(float(score), 2),
            "factors": factors or [],
            "inputs": inputs or {},
            "prediction_date": now_utc,
            "prediction_date_iso": now_utc.isoformat(),
            "model_version": model_version,
        }
        col.insert_one(doc)
        logger.info(f"Prediction logged for student {student_id}: score={score}")
        return True
    except PyMongoError as pme:
        logger.warning(f"MongoDB error while logging prediction: {pme}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error while logging prediction: {e}")
        return False


def get_prediction_history(student_id: str, limit: int = 50) -> list:
    """
    Retrieves previous predictions for a student, ordered chronologically.
    Returns list of {"date": "YYYY-MM-DD", "mental_health_score": float, ...}
    """
    try:
        col = get_predictions_collection()
        if col is None:
            return []

        if not isinstance(limit, int):
            limit = 50
        cursor = col.find({"student_id": student_id}).sort([("prediction_date", ASCENDING), ("_id", ASCENDING)]).limit(limit)
        results = []
        for doc in cursor:
            p_date = doc.get("prediction_date")
            if isinstance(p_date, datetime):
                date_str = p_date.strftime("%Y-%m-%d")
            else:
                date_str = str(doc.get("prediction_date_iso", ""))[:10]

            results.append({
                "date": date_str,
                "mental_health_score": float(doc.get("mental_health_score", 0.0)),
                "model_version": doc.get("model_version", "random_forest_v1"),
            })
        return results
    except Exception as e:
        logger.warning(f"Error fetching prediction history for {student_id}: {e}")
        return []
