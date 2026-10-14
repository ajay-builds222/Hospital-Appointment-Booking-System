import logging
from datetime import date, datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import joinedload
from app.database import SessionLocal
from app.models.models import Appointment, Consultation
from app.services.email_service import send_email

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def send_reminders():
    db = SessionLocal()
    try:
        now = datetime.now()
        end = now + timedelta(hours=24)
        rows = db.query(Appointment).options(joinedload(Appointment.patient), joinedload(Appointment.doctor)).filter(
            Appointment.status == "Booked", Appointment.reminder_sent.is_(False),
            Appointment.appointment_date >= now.date(),
            Appointment.appointment_date <= end.date()
        ).all()
        for appt in rows:
            send_email(appt.patient.email, "Appointment reminder",
                       f"Reminder: {appt.appointment_number} with Dr. {appt.doctor.name} on {appt.appointment_date} at {appt.slot_time}.")
            appt.reminder_sent = True
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Reminder job failed")
    finally:
        db.close()

def mark_no_shows():
    db = SessionLocal()
    try:
        cutoff = datetime.now() - timedelta(minutes=30)
        rows = db.query(Appointment).filter(
            Appointment.status == "Booked",
            Appointment.appointment_date < cutoff.date()
        ).all()
        for appt in rows:
            appt.status = "No-Show"
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No-show job failed")
    finally:
        db.close()

def send_followups():
    db = SessionLocal()
    try:
        tomorrow = date.today() + timedelta(days=1)
        rows = db.query(Consultation).options(joinedload(Consultation.appointment).joinedload(Appointment.patient)).filter(
            Consultation.follow_up_date == tomorrow).all()
        for consult in rows:
            send_email(consult.appointment.patient.email, "Follow-up reminder",
                       f"Your follow-up date is {tomorrow}.")
    except Exception:
        logger.exception("Follow-up job failed")
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(send_reminders, "interval", hours=1, id="reminders", replace_existing=True)
        scheduler.add_job(mark_no_shows, "interval", minutes=15, id="no_shows", replace_existing=True)
        scheduler.add_job(send_followups, "cron", hour=8, minute=0, id="followups", replace_existing=True)
        scheduler.start()

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
