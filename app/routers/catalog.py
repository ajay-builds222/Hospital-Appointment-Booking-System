from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Department, Doctor, User
from app.routers.auth import current_user, require_roles
from app.schemas.schemas import DepartmentIn, DoctorIn

router = APIRouter(tags=["Departments and Doctors"])

@router.post("/departments", status_code=201)
def create_department(data: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    if db.query(Department).filter(Department.name == data.name).first():
        raise HTTPException(409, "Department name already exists")
    item = Department(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.get("/departments")
def list_departments(skip: int = 0, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    return db.query(Department).offset(skip).limit(limit).all()

@router.put("/departments/{department_id}")
def update_department(department_id: int, data: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    item = db.get(Department, department_id)
    if not item: raise HTTPException(404, "Department not found")
    item.name, item.description = data.name, data.description
    db.commit(); db.refresh(item)
    return item

@router.delete("/departments/{department_id}")
def delete_department(department_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    item = db.get(Department, department_id)
    if not item: raise HTTPException(404, "Department not found")
    if any(d.is_active for d in item.doctors): raise HTTPException(409, "Department has active doctors")
    db.delete(item); db.commit()
    return {"message": "Department deleted"}

@router.post("/doctors", status_code=201)
def create_doctor(data: DoctorIn, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    user = db.get(User, data.user_id)
    if not user: raise HTTPException(404, "User not found")
    if user.role != "doctor": raise HTTPException(400, "user_id must belong to a doctor account created by an admin")
    if not db.get(Department, data.department_id): raise HTTPException(404, "Department not found")
    item = Doctor(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.get("/doctors")
def list_doctors(department_id: int | None = None, specialization: str | None = None,
                 name: str | None = None, skip: int = 0, limit: int = Query(20, ge=1, le=100),
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Doctor).filter(Doctor.is_active.is_(True))
    if department_id: q = q.filter(Doctor.department_id == department_id)
    if specialization: q = q.filter(Doctor.specialization.ilike(f"%{specialization}%"))
    if name: q = q.filter(Doctor.name.ilike(f"%{name}%"))
    return q.offset(skip).limit(limit).all()

@router.get("/doctors/{doctor_id}")
def get_doctor(doctor_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    item = db.get(Doctor, doctor_id)
    if not item or not item.is_active: raise HTTPException(404, "Doctor not found")
    return item

@router.put("/doctors/{doctor_id}")
def update_doctor(doctor_id: int, data: DoctorIn, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    item = db.get(Doctor, doctor_id)
    if not item: raise HTTPException(404, "Doctor not found")
    for key, value in data.model_dump().items(): setattr(item, key, value)
    db.commit(); db.refresh(item)
    return item

@router.delete("/doctors/{doctor_id}")
def deactivate_doctor(doctor_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles("admin"))):
    item = db.get(Doctor, doctor_id)
    if not item: raise HTTPException(404, "Doctor not found")
    from datetime import date
    from app.models.models import Appointment
    upcoming = db.query(Appointment).filter(Appointment.doctor_id == doctor_id,
        Appointment.appointment_date >= date.today(), Appointment.status.in_(["Booked", "Checked-In", "In Consultation"])).first()
    if upcoming: raise HTTPException(409, "Doctor has upcoming appointments")
    item.is_active = False; db.commit()
    return {"message": "Doctor deactivated"}
