from datetime import date, time
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    password: str = Field(min_length=8)
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value):
        if value is not None and (len(value) != 10 or not value.isdigit()):
            raise ValueError("Phone must contain exactly 10 digits")
        return value

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class DepartmentIn(BaseModel):
    name: str
    description: str | None = None

class DoctorIn(BaseModel):
    user_id: int
    name: str
    department_id: int
    specialization: str
    qualification: str
    experience_years: int = Field(ge=0)
    consultation_fee: float = Field(gt=0)
    slot_duration_minutes: int = Field(default=15)

    @field_validator("slot_duration_minutes")
    @classmethod
    def valid_slot(cls, value):
        if value not in (10, 15, 20, 30):
            raise ValueError("Slot duration must be 10, 15, 20, or 30")
        return value

class ScheduleIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    break_start: time | None = None
    break_end: time | None = None

class LeaveIn(BaseModel):
    leave_date: date
    reason: str | None = None

class AppointmentIn(BaseModel):
    doctor_id: int
    appointment_date: date
    slot_time: time
    reason: str | None = None

class RescheduleIn(BaseModel):
    appointment_date: date
    slot_time: time

class ConsultationIn(BaseModel):
    symptoms: str
    diagnosis: str
    prescription: str | None = None
    advice: str | None = None
    follow_up_date: date | None = None

class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
