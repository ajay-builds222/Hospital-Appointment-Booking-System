from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Appointment, Doctor, DoctorLeave, Schedule, User
from app.routers.auth import current_user, require_roles
from app.schemas.schemas import LeaveIn, ScheduleIn

router = APIRouter(tags=["Schedules and Leaves"])

def can_manage(user: User, doctor_id: int, db: Session):
    if user.role == "admin": return
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id, Doctor.user_id == user.id).first()
    if user.role != "doctor" or not doctor: raise HTTPException(403, "Cannot manage this doctor's schedule")

@router.post("/doctors/{doctor_id}/schedules", status_code=201)
def add_schedule(doctor_id: int, data: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    can_manage(user, doctor_id, db)
    if data.end_time <= data.start_time: raise HTTPException(422, "End time must follow start time")
    if (data.break_start is None) != (data.break_end is None): raise HTTPException(422, "Provide both break times")
    if data.break_start and not (data.start_time <= data.break_start < data.break_end <= data.end_time):
        raise HTTPException(422, "Break must be inside working hours")
    schedules = db.query(Schedule).filter(Schedule.doctor_id == doctor_id, Schedule.day_of_week == data.day_of_week).all()
    for s in schedules:
        if data.start_time < s.end_time and s.start_time < data.end_time:
            raise HTTPException(409, "Schedule overlaps an existing schedule")
    item = Schedule(doctor_id=doctor_id, **data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.get("/doctors/{doctor_id}/schedules")
def get_schedules(doctor_id: int, db: Session = Depends(get_db)):
    return db.query(Schedule).filter(Schedule.doctor_id == doctor_id).all()

@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, data: ScheduleIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Schedule, schedule_id)
    if not item: raise HTTPException(404, "Schedule not found")
    can_manage(user, item.doctor_id, db)
    if data.end_time <= data.start_time: raise HTTPException(422, "End time must follow start time")
    item.day_of_week = data.day_of_week
    item.start_time, item.end_time = data.start_time, data.end_time
    item.break_start, item.break_end = data.break_start, data.break_end
    db.commit(); db.refresh(item)
    return item

@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Schedule, schedule_id)
    if not item: raise HTTPException(404, "Schedule not found")
    can_manage(user, item.doctor_id, db)
    db.delete(item); db.commit()
    return {"message": "Schedule deleted"}

@router.post("/doctors/{doctor_id}/leaves", status_code=201)
def add_leave(doctor_id: int, data: LeaveIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    can_manage(user, doctor_id, db)
    if not db.get(Doctor, doctor_id): raise HTTPException(404, "Doctor not found")
    leave = DoctorLeave(doctor_id=doctor_id, **data.model_dump())
    db.add(leave)
    appts = db.query(Appointment).filter(Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == data.leave_date, Appointment.status == "Booked").all()
    for a in appts:
        a.status = "Cancelled"
    db.commit()
    return {"leave": leave, "cancelled_appointments": len(appts)}

@router.get("/doctors/{doctor_id}/leaves")
def get_leaves(doctor_id: int, db: Session = Depends(get_db)):
    return db.query(DoctorLeave).filter(DoctorLeave.doctor_id == doctor_id).all()

@router.get("/doctors/{doctor_id}/available-slots")
def available_slots(doctor_id: int, date: date, db: Session = Depends(get_db)):
    doctor = db.get(Doctor, doctor_id)
    if not doctor or not doctor.is_active: raise HTTPException(404, "Doctor not found")
    if date < datetime.now().date(): return {"date": str(date), "slots": []}
    if db.query(DoctorLeave).filter_by(doctor_id=doctor_id, leave_date=date).first():
        return {"date": str(date), "slots": []}
    schedules = db.query(Schedule).filter_by(doctor_id=doctor_id, day_of_week=date.weekday()).all()
    booked = {a.slot_time for a in db.query(Appointment).filter_by(doctor_id=doctor_id, appointment_date=date)
              .filter(Appointment.status.in_(["Booked", "Checked-In", "In Consultation"])).all()}
    slots = []
    for s in schedules:
        t = datetime.combine(date, s.start_time)
        end = datetime.combine(date, s.end_time)
        while t + timedelta(minutes=doctor.slot_duration_minutes) <= end:
            slot_end = t + timedelta(minutes=doctor.slot_duration_minutes)
            overlaps_break = s.break_start and t.time() < s.break_end and s.break_start < slot_end.time()
            if not overlaps_break and t.time() not in booked and t > datetime.now():
                slots.append(t.strftime("%H:%M:%S"))
            t += timedelta(minutes=doctor.slot_duration_minutes)
    return {"date": str(date), "slots": sorted(set(slots))}
