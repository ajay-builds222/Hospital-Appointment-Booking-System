
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import (
    Appointment,
    AppointmentHistory,
    Doctor,
    DoctorLeave,
    Schedule,
    User,
)
from app.routers.auth import current_user, require_roles
from app.schemas.schemas import AppointmentIn, RescheduleIn
from app.services.email_service import send_email

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def normalize_slot(slot):
    """
    Normalize an incoming time to a timezone-naive time.

    Appointment slots and doctor schedules are stored as local wall-clock
    times. The API may receive a time containing a timezone suffix such as Z.
    """
    if slot.tzinfo is not None:
        return slot.replace(tzinfo=None)
    return slot


def history(db, appt, old, new, actor):
    db.add(
        AppointmentHistory(
            appointment_id=appt.id,
            old_status=old,
            new_status=new,
            changed_by=actor.id,
        )
    )


def validate_slot(
    db,
    patient_id,
    doctor_id,
    day,
    slot,
    ignore_id=None,
):
    # Normalize before constructing datetimes or comparing schedule times.
    slot = normalize_slot(slot)

    now = datetime.now()
    start = datetime.combine(day, slot)

    if start <= now:
        raise HTTPException(
            status_code=400,
            detail="Appointments must be in the future",
        )

    if start > now + timedelta(days=30):
        raise HTTPException(
            status_code=400,
            detail="Appointments can be booked at most 30 days ahead",
        )

    doctor = db.get(Doctor, doctor_id)

    if not doctor or not doctor.is_active:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found",
        )

    # Check whether the doctor is on leave.
    leave = (
        db.query(DoctorLeave)
        .filter_by(doctor_id=doctor_id, leave_date=day)
        .first()
    )

    if leave:
        raise HTTPException(
            status_code=409,
            detail="Doctor is on leave",
        )

    # Check the doctor's working schedule for this weekday.
    schedule = (
        db.query(Schedule)
        .filter_by(
            doctor_id=doctor_id,
            day_of_week=day.weekday(),
        )
        .all()
    )

    valid = False

    end = (
        datetime.combine(day, slot)
        + timedelta(minutes=doctor.slot_duration_minutes)
    ).time()

    for schedule_item in schedule:
        if not (
            schedule_item.start_time <= slot
            and end <= schedule_item.end_time
        ):
            continue

        # Reject slots that overlap a configured break.
        break_start = schedule_item.break_start
        break_end = schedule_item.break_end

        if (
            break_start is not None
            and break_end is not None
            and slot < break_end
            and break_start < end
        ):
            continue

        valid = True
        break

    if not valid:
        raise HTTPException(
            status_code=400,
            detail="Slot is outside schedule or during break",
        )

    # Prevent another active appointment for the same doctor and slot.
    doctor_query = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == day,
        Appointment.slot_time == slot,
        Appointment.status.in_(
            ["Booked", "Checked-In", "In Consultation"]
        ),
    )

    if ignore_id is not None:
        doctor_query = doctor_query.filter(
            Appointment.id != ignore_id
        )

    if doctor_query.first():
        raise HTTPException(
            status_code=409,
            detail="Slot already booked",
        )

    # Prevent the patient from booking overlapping appointments.
    patient_query = db.query(Appointment).filter(
        Appointment.patient_id == patient_id,
        Appointment.appointment_date == day,
        Appointment.status.in_(
            ["Booked", "Checked-In", "In Consultation"]
        ),
    )

    if ignore_id is not None:
        patient_query = patient_query.filter(
            Appointment.id != ignore_id
        )

    if patient_query.filter(
        Appointment.slot_time == slot
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Patient already has an appointment at this time",
        )

    if patient_query.filter(
        Appointment.doctor_id == doctor_id
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Patient may book only one appointment per doctor per day",
        )

    return doctor


@router.post("", status_code=201)
def book(
    data: AppointmentIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("patient")),
):
    # Normalize once and use the same value throughout this operation.
    slot = normalize_slot(data.slot_time)

    doctor = validate_slot(
        db,
        user.id,
        data.doctor_id,
        data.appointment_date,
        slot,
    )

    existing = (
        db.query(Appointment)
        .filter_by(
            doctor_id=data.doctor_id,
            appointment_date=data.appointment_date,
        )
        .count()
    )

    number = (
        f"APT-{data.appointment_date:%Y%m%d}-"
        f"{uuid4().hex[:6].upper()}"
    )

    appointment = Appointment(
        appointment_number=number,
        patient_id=user.id,
        doctor_id=data.doctor_id,
        appointment_date=data.appointment_date,
        slot_time=slot,
        token_number=existing + 1,
        reason=data.reason,
        status="Booked",
        consultation_fee=doctor.consultation_fee,
    )

    db.add(appointment)

    try:
        db.flush()

        history(
            db,
            appointment,
            None,
            "Booked",
            user,
        )

        db.commit()
        db.refresh(appointment)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not reserve this slot; it may have just been booked",
        )

    background_tasks.add_task(
        send_email,
        user.email,
        "Appointment booked",
        (
            f"Appointment {appointment.appointment_number}; "
            f"doctor Dr. {doctor.name}; "
            f"date {appointment.appointment_date}; "
            f"time {appointment.slot_time}; "
            f"token {appointment.token_number}."
        ),
    )

    return appointment


@router.get("")
def list_appointments(
    status: str | None = None,
    doctor_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    appointment_number: str | None = None,
    skip: int = 0,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(Appointment)

    if user.role == "patient":
        query = query.filter(
            Appointment.patient_id == user.id
        )

    elif user.role == "doctor":
        doctor = (
            db.query(Doctor)
            .filter_by(user_id=user.id)
            .first()
        )

        if not doctor:
            return []

        query = query.filter(
            Appointment.doctor_id == doctor.id
        )

    if status:
        query = query.filter(
            Appointment.status == status
        )

    if doctor_id:
        query = query.filter(
            Appointment.doctor_id == doctor_id
        )

    if date_from:
        query = query.filter(
            Appointment.appointment_date >= date_from.date()
        )

    if date_to:
        query = query.filter(
            Appointment.appointment_date <= date_to.date()
        )

    if appointment_number:
        query = query.filter(
            Appointment.appointment_number.ilike(
                f"%{appointment_number}%"
            )
        )

    return (
        query.order_by(
            Appointment.appointment_date,
            Appointment.slot_time,
        )
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{appointment_id}")
def get_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    appointment = db.get(Appointment, appointment_id)

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found",
        )

    if user.role == "admin":
        return appointment

    if (
        user.role == "patient"
        and appointment.patient_id == user.id
    ):
        return appointment

    if (
        user.role == "doctor"
        and appointment.doctor.user_id == user.id
    ):
        return appointment

    raise HTTPException(
        status_code=403,
        detail="Not allowed to view this appointment",
    )


@router.put("/{appointment_id}/cancel")
def cancel(
    appointment_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    appointment = db.get(Appointment, appointment_id)

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found",
        )

    if user.role != "admin" and not (
        user.role == "patient"
        and appointment.patient_id == user.id
    ):
        raise HTTPException(
            status_code=403,
            detail="Not allowed",
        )

    if appointment.status != "Booked":
        raise HTTPException(
            status_code=409,
            detail="Only Booked appointments can be cancelled",
        )

    appointment_start = datetime.combine(
        appointment.appointment_date,
        normalize_slot(appointment.slot_time),
    )

    if (
        user.role != "admin"
        and appointment_start - datetime.now()
        < timedelta(hours=2)
    ):
        raise HTTPException(
            status_code=400,
            detail="Cancellation must be at least 2 hours before appointment",
        )

    old_status = appointment.status
    appointment.status = "Cancelled"

    history(
        db,
        appointment,
        old_status,
        appointment.status,
        user,
    )

    db.commit()

    background_tasks.add_task(
        send_email,
        appointment.patient.email,
        "Appointment cancelled",
        f"Appointment {appointment.appointment_number} was cancelled.",
    )

    return {"message": "Appointment cancelled"}


@router.put("/{appointment_id}/reschedule")
def reschedule(
    appointment_id: int,
    data: RescheduleIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("patient")),
):
    appointment = db.get(Appointment, appointment_id)

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found",
        )

    if appointment.patient_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Not your appointment",
        )

    if appointment.status != "Booked":
        raise HTTPException(
            status_code=409,
            detail="Only Booked appointments can be rescheduled",
        )

    if appointment.reschedule_count >= 2:
        raise HTTPException(
            status_code=400,
            detail="Maximum reschedules reached",
        )

    appointment_start = datetime.combine(
        appointment.appointment_date,
        normalize_slot(appointment.slot_time),
    )

    if appointment_start - datetime.now() < timedelta(hours=2):
        raise HTTPException(
            status_code=400,
            detail="Reschedule must be at least 2 hours before appointment",
        )

    new_slot = normalize_slot(data.slot_time)

    validate_slot(
        db,
        user.id,
        appointment.doctor_id,
        data.appointment_date,
        new_slot,
        ignore_id=appointment.id,
    )

    old_status = appointment.status

    appointment.appointment_date = data.appointment_date
    appointment.slot_time = new_slot
    appointment.reschedule_count += 1

    history(
        db,
        appointment,
        old_status,
        "Booked",
        user,
    )

    db.commit()
    db.refresh(appointment)

    background_tasks.add_task(
        send_email,
        user.email,
        "Appointment rescheduled",
        (
            f"Appointment {appointment.appointment_number} "
            f"moved to {appointment.appointment_date} "
            f"at {appointment.slot_time}."
        ),
    )

    return appointment


@router.put("/{appointment_id}/check-in")
def check_in(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    appointment = db.get(Appointment, appointment_id)

    if not appointment:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found",
        )

    if appointment.status != "Booked":
        raise HTTPException(
            status_code=409,
            detail="Only Booked appointments can be checked in",
        )

    now = datetime.now()

    appointment_start = datetime.combine(
        appointment.appointment_date,
        normalize_slot(appointment.slot_time),
    )

    if (
        now.date() != appointment.appointment_date
        or now < appointment_start - timedelta(minutes=30)
    ):
        raise HTTPException(
            status_code=400,
            detail="Check-in opens 30 minutes before the appointment on its date",
        )

    old_status = appointment.status
    appointment.status = "Checked-In"

    history(
        db,
        appointment,
        old_status,
        appointment.status,
        user,
    )

    db.commit()
    db.refresh(appointment)

    return appointment
