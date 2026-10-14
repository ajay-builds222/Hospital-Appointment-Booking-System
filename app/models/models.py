from datetime import datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(10), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="patient")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    doctor_profile: Mapped["Doctor | None"] = relationship(back_populates="user", uselist=False)
    patient_appointments: Mapped[list["Appointment"]] = relationship(back_populates="patient", foreign_keys="Appointment.patient_id")

class RefreshToken(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

class Department(TimestampMixin, Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctors: Mapped[list["Doctor"]] = relationship(back_populates="department")

class Doctor(TimestampMixin, Base):
    __tablename__ = "doctors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    specialization: Mapped[str] = mapped_column(String(120))
    qualification: Mapped[str] = mapped_column(String(120))
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    consultation_fee: Mapped[float] = mapped_column(Numeric(10, 2))
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, default=15)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped["User"] = relationship(back_populates="doctor_profile")
    department: Mapped["Department"] = relationship(back_populates="doctors")
    schedules: Mapped[list["Schedule"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    leaves: Mapped[list["DoctorLeave"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")
    appointments: Mapped[list["Appointment"]] = relationship(back_populates="doctor")

class Schedule(TimestampMixin, Base):
    __tablename__ = "schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # Monday=0 ... Sunday=6
    start_time: Mapped[object] = mapped_column(Time)
    end_time: Mapped[object] = mapped_column(Time)
    break_start: Mapped[object | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[object | None] = mapped_column(Time, nullable=True)
    doctor: Mapped["Doctor"] = relationship(back_populates="schedules")

class DoctorLeave(TimestampMixin, Base):
    __tablename__ = "doctor_leaves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    leave_date: Mapped[object] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    doctor: Mapped["Doctor"] = relationship(back_populates="leaves")

class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("doctor_id", "appointment_date", "slot_time", name="uq_doctor_slot"),
        UniqueConstraint("appointment_number", name="uq_appointment_number"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id"), index=True)
    appointment_date: Mapped[object] = mapped_column(Date, index=True)
    slot_time: Mapped[object] = mapped_column(Time)
    token_number: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="Booked", index=True)
    consultation_fee: Mapped[float] = mapped_column(Numeric(10, 2))
    reschedule_count: Mapped[int] = mapped_column(Integer, default=0)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    patient: Mapped["User"] = relationship(back_populates="patient_appointments", foreign_keys=[patient_id])
    doctor: Mapped["Doctor"] = relationship(back_populates="appointments")
    consultation: Mapped["Consultation | None"] = relationship(back_populates="appointment", uselist=False, cascade="all, delete-orphan")
    history: Mapped[list["AppointmentHistory"]] = relationship(back_populates="appointment", cascade="all, delete-orphan")

class AppointmentHistory(TimestampMixin, Base):
    __tablename__ = "appointment_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30))
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    appointment: Mapped["Appointment"] = relationship(back_populates="history")

class Consultation(TimestampMixin, Base):
    __tablename__ = "consultations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), unique=True)
    symptoms: Mapped[str] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    prescription: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    appointment: Mapped["Appointment"] = relationship(back_populates="consultation")
    files: Mapped[list["UploadedFile"]] = relationship(back_populates="consultation", cascade="all, delete-orphan")

class UploadedFile(TimestampMixin, Base):
    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    consultation_id: Mapped[int | None] = mapped_column(ForeignKey("consultations.id"), nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_type: Mapped[str] = mapped_column(String(40))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    size_kb: Mapped[int] = mapped_column(Integer)
    consultation: Mapped["Consultation | None"] = relationship(back_populates="files")
