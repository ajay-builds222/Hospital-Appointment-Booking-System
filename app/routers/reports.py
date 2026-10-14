from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Appointment, Consultation, Department, Doctor, User
from app.routers.auth import require_roles

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    today = date.today()
    rows = db.query(Appointment.status, func.count(Appointment.id)).filter(Appointment.appointment_date == today).group_by(Appointment.status).all()
    counts = {status: count for status, count in rows}
    revenue = db.query(func.coalesce(func.sum(Appointment.consultation_fee), 0)).filter(
        Appointment.appointment_date == today, Appointment.status == "Completed").scalar()
    return {"date": str(today), "total_appointments": sum(counts.values()),
        "checked_in": counts.get("Checked-In", 0), "completed": counts.get("Completed", 0),
        "cancelled": counts.get("Cancelled", 0), "no_shows": counts.get("No-Show", 0),
        "consultation_revenue": float(revenue or 0)}

@router.get("/doctor-performance")
def doctor_performance(start_date: date, end_date: date, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    doctors = db.query(Doctor).all()
    result = []
    for d in doctors:
        q = db.query(Appointment).filter(Appointment.doctor_id == d.id,
            Appointment.appointment_date.between(start_date, end_date))
        total = q.count()
        completed = q.filter(Appointment.status == "Completed").count()
        no_shows = q.filter(Appointment.status == "No-Show").count()
        revenue = q.filter(Appointment.status == "Completed").with_entities(func.coalesce(func.sum(Appointment.consultation_fee), 0)).scalar()
        result.append({"doctor_id": d.id, "doctor_name": d.name, "appointments": total, "completed": completed,
            "no_show_percentage": round(no_shows * 100 / total, 2) if total else 0, "revenue": float(revenue or 0)})
    return result

@router.get("/department-summary")
def department_summary(start_date: date, end_date: date, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    return db.query(Department.name.label("department"), func.count(Appointment.id).label("appointments")).join(
        Doctor, Doctor.department_id == Department.id).join(Appointment, Appointment.doctor_id == Doctor.id).filter(
        Appointment.appointment_date.between(start_date, end_date)).group_by(Department.name).all()

@router.get("/peak-hours")
def peak_hours(start_date: date, end_date: date, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    rows = db.query(func.hour(Appointment.slot_time).label("hour"), func.count(Appointment.id).label("appointments")).filter(
        Appointment.appointment_date.between(start_date, end_date), Appointment.status != "Cancelled").group_by(
        func.hour(Appointment.slot_time)).order_by(func.hour(Appointment.slot_time)).all()
    return [{"hour": int(r.hour), "appointments": r.appointments} for r in rows]

@router.get("/frequent-no-shows")
def frequent_no_shows(db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    since = date.today() - timedelta(days=90)
    rows = db.query(User.id, User.full_name, User.email, func.count(Appointment.id).label("no_shows")).join(
        Appointment, Appointment.patient_id == User.id).filter(Appointment.status == "No-Show",
        Appointment.appointment_date >= since).group_by(User.id, User.full_name, User.email).having(
        func.count(Appointment.id) >= 3).all()
    return [{"patient_id": r.id, "name": r.full_name, "email": r.email, "no_shows": r.no_shows} for r in rows]
