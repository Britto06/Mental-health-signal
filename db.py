from sqlalchemy import create_engine, Column, Integer, String, Date
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import date

DATABASE_URL = "sqlite:///./reminders.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    contact = Column(String, unique=True, index=True, nullable=False)  # email address OR phone number
    channel = Column(String, nullable=False, default="email")  # "email" | "whatsapp"
    next_send_date = Column(Date, nullable=False)
    created_at = Column(Date, default=date.today)


def init_db():
    Base.metadata.create_all(bind=engine)
