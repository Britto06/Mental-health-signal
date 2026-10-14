"""
Mental Health Signal API.

Run locally:      uvicorn api:app --reload
Deploy on Render:  build command  -> pip install -r requirements.txt
                    start command -> uvicorn api:app --host 0.0.0.0 --port $PORT

Requires pipeline.pkl in the same folder (produced by train_model.py).
Once this is deployed, set API_BASE_URL in the React site to this service's URL.
"""

from datetime import date, timedelta
from contextlib import asynccontextmanager
from typing import Optional, Literal
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, EmailStr
import joblib
import pandas as pd

from db import init_db, SessionLocal, Reminder
from scheduler import start_scheduler
from database import init_mongodb, log_prediction_to_db, get_prediction_history
from services.reminder_service import (
    upsert_preferences,
    get_preferences,
    disable_reminders,
    send_test_reminder,
    record_assessment_completed,
    SUPPORTED_INTERVALS,
)

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_db()
    init_mongodb()
    start_scheduler()  # runs periodic and daily reminder checks in the background
    yield


app = FastAPI(title="Mental Health Signal API", lifespan=lifespan)

# Tighten allow_origins to your actual frontend domain before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    model = joblib.load("pipeline.pkl")
except FileNotFoundError:
    model = None  # /predict will return a clear error until you run train_model.py


FEATURE_LABELS = {
    "num__screen_time": "High screen time",
    "skewed__phone_unlocks": "Frequent phone unlocks",
    "num__study_hours": "Study hours",
    "num__activity": "Low physical activity",
    "num__sleep": "Short sleep",
    "ord__stress": "Stress level",
}


class ReadingInput(BaseModel):
    age: int = Field(ge=10, le=100)
    gender: str
    academicLevel: str
    platform: str
    purpose: str
    screenTime: float = Field(ge=0, le=24)
    phoneUnlocks: int = Field(ge=0, le=500)
    studyHours: float = Field(ge=0, le=24)
    activity: float = Field(ge=0, le=24)
    sleep: float = Field(ge=0, le=24)
    stress: str
    studentId: Optional[str] = Field(default=None, description="Optional student identification for history tracking")


class ReminderPreferenceInput(BaseModel):
    student_id: str = Field(..., min_length=1, description="Unique student identification")
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    reminder_channel: Literal["email", "whatsapp", "both"] = "email"
    reminder_interval_days: int = Field(default=7, description="1=Daily, 2=Every 2 days, 7=Weekly")
    reminders_enabled: bool = True


class ReminderPreferenceUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    reminder_channel: Optional[Literal["email", "whatsapp", "both"]] = None
    reminder_interval_days: Optional[int] = Field(default=None, description="1=Daily, 2=Every 2 days, 7=Weekly")
    reminders_enabled: Optional[bool] = None


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


class SubscribeInput(BaseModel):
    contact: str  # email address if channel="email", phone number (e.g. +919876543210) if "whatsapp"
    channel: Literal["email", "whatsapp"] = "email"


@app.post("/subscribe")
def subscribe(payload: SubscribeInput):
    """Save or renew a weekly-reminder subscription. The actual sending
    happens later, in the background job in scheduler.py — this endpoint
    just records "message this contact again in 7 days"."""
    if payload.channel == "email" and "@" not in payload.contact:
        raise HTTPException(status_code=400, detail="That doesn't look like a valid email address.")
    if payload.channel == "whatsapp" and len(payload.contact.strip()) < 8:
        raise HTTPException(status_code=400, detail="That doesn't look like a valid phone number.")

    # Save to MongoDB
    try:
        upsert_preferences(
            student_id=payload.contact,
            email=payload.contact if payload.channel == "email" else None,
            phone=payload.contact if payload.channel == "whatsapp" else None,
            reminder_channel=payload.channel,
            reminder_interval_days=7,
            reminders_enabled=True,
        )
    except Exception as e:
        pass

    # Save to legacy SQLite
    db = SessionLocal()
    try:
        next_date = date.today() + timedelta(days=7)
        existing = db.query(Reminder).filter(Reminder.contact == payload.contact).first()
        if existing:
            existing.next_send_date = next_date  # type: ignore[assignment]
            existing.channel = str(payload.channel)  # type: ignore[assignment]
        else:
            db.add(Reminder(contact=payload.contact, channel=str(payload.channel), next_send_date=next_date))
        db.commit()
        return {"status": "subscribed", "channel": payload.channel, "next_send_date": str(next_date)}
    finally:
        db.close()


@app.post("/predict")
def predict(payload: ReadingInput, student_id: Optional[str] = None):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not trained yet — run train_model.py first.")

    row = pd.DataFrame([{
        "age": payload.age,
        "gender": payload.gender,
        "academic_level": payload.academicLevel,
        "platform": payload.platform,
        "purpose": payload.purpose,
        "screen_time": payload.screenTime,
        "phone_unlocks": payload.phoneUnlocks,
        "study_hours": payload.studyHours,
        "activity": payload.activity,
        "sleep": payload.sleep,
        "stress": payload.stress,
    }])

    score = float(model.predict(row)[0])
    score = max(0.0, min(10.0, score))

    # Approximate "why" using the forest's overall feature importances,
    # scaled to look like the contribution bars on the frontend.
    rf = model.named_steps["rf"]
    try:
        feature_names = model.named_steps["preprocess"].get_feature_names_out()
    except Exception:
        feature_names = [f"num__{k}" for k in FEATURE_LABELS.keys()]
    importances = rf.feature_importances_
    ranked = importances.argsort()[::-1]

    factors = []
    seen_labels = set()
    for i in ranked:
        name = feature_names[i]
        label = next((v for k, v in FEATURE_LABELS.items() if k in name), None)
        if label and label not in seen_labels:
            factors.append({"label": label, "value": round(float(importances[i]) * 10, 2)})
            seen_labels.add(label)
        if len(factors) == 3:
            break

    # Save prediction history to MongoDB (gracefully catches database errors)
    sid = student_id or payload.studentId or "anonymous"
    try:
        inputs_dict = {
            "age": payload.age,
            "gender": payload.gender,
            "academicLevel": payload.academicLevel,
            "platform": payload.platform,
            "purpose": payload.purpose,
            "screenTime": payload.screenTime,
            "phoneUnlocks": payload.phoneUnlocks,
            "studyHours": payload.studyHours,
            "activity": payload.activity,
            "sleep": payload.sleep,
            "stress": payload.stress,
        }
        log_prediction_to_db(
            student_id=sid,
            score=round(score, 2),
            factors=factors,
            inputs=inputs_dict,
            model_version="random_forest_v1",
        )
        if sid != "anonymous":
            record_assessment_completed(sid)
    except Exception as e:
        # DB failure must never break prediction response
        pass

    return {"score": round(score, 2), "factors": factors}


# =========================================================================
# Reminder Preferences & History API Endpoints
# =========================================================================

@app.post("/reminders/preferences")
def create_reminder_preferences(payload: ReminderPreferenceInput):
    """
    Sets or updates reminder preferences for a student.
    Supported intervals: 1 (Daily), 2 (Every 2 days), 7 (Weekly).
    """
    if payload.reminder_interval_days not in SUPPORTED_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reminder interval: {payload.reminder_interval_days}. Supported intervals are 1 (Daily), 2 (Every 2 days), and 7 (Weekly)."
        )

    try:
        result = upsert_preferences(
            student_id=payload.student_id,
            email=str(payload.email) if payload.email is not None else None,
            phone=payload.phone,
            reminder_channel=payload.reminder_channel,
            reminder_interval_days=payload.reminder_interval_days,
            reminders_enabled=payload.reminders_enabled,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to save reminder preferences.")


@app.get("/reminders/preferences/{student_id}")
def get_reminder_preferences(student_id: str):
    """
    Retrieves stored reminder preferences for a student.
    """
    prefs = get_preferences(student_id)
    if not prefs:
        raise HTTPException(status_code=404, detail=f"No reminder preferences found for student {student_id}.")
    return prefs


@app.put("/reminders/preferences/{student_id}")
def update_reminder_preferences(student_id: str, payload: ReminderPreferenceUpdate):
    """
    Updates existing reminder preferences for a student.
    """
    existing = get_preferences(student_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")

    interval = payload.reminder_interval_days if payload.reminder_interval_days is not None else existing["reminder_interval_days"]
    if interval not in SUPPORTED_INTERVALS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid reminder interval: {interval}. Supported intervals are 1, 2, and 7."
        )

    channel = payload.reminder_channel if payload.reminder_channel is not None else existing["reminder_channel"]
    email = str(payload.email) if payload.email is not None else existing.get("email")
    phone = payload.phone if payload.phone is not None else existing.get("phone")
    enabled = payload.reminders_enabled if payload.reminders_enabled is not None else existing.get("reminders_enabled", True)

    try:
        result = upsert_preferences(
            student_id=student_id,
            email=email,
            phone=phone,
            reminder_channel=channel,
            reminder_interval_days=interval,
            reminders_enabled=enabled,
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update reminder preferences.")


@app.post("/reminders/disable/{student_id}")
def disable_student_reminders_endpoint(student_id: str):
    """
    Disables reminders for the specified student.
    """
    success = disable_reminders(student_id)
    if not success:
        # Check if student exists
        existing = get_preferences(student_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found.")
    return {"status": "disabled", "student_id": student_id, "reminders_enabled": False}


@app.post("/reminders/test/{student_id}")
def test_reminder_endpoint(student_id: str):
    """
    Triggers an immediate test reminder for testing without waiting for schedule.
    """
    try:
        result = send_test_reminder(student_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test reminder: {e}")


@app.get("/predictions/history/{student_id}")
def get_student_history_endpoint(student_id: str, limit: int = 50):
    """
    Returns historical prediction records for a student ordered chronologically.
    Example:
    [
        {"date": "2026-10-05", "mental_health_score": 7.2},
        {"date": "2026-10-12", "mental_health_score": 6.8}
    ]
    """
    history = get_prediction_history(student_id, limit=limit)
    return history
