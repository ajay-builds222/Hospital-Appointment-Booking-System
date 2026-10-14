import os
from datetime import date
from uuid import uuid4
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Appointment, Consultation, Doctor, UploadedFile, User
from app.routers.auth import current_user
from app.schemas.schemas import ConsultationIn

router = APIRouter(tags=["Consultations and Files"])
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

def get_authorized_appointment(db, appointment_id, user):
    a = db.get(Appointment, appointment_id)
    if not a: raise HTTPException(404, "Appointment not found")
    if user.role == "admin": return a
    if user.role == "patient" and a.patient_id == user.id: return a
    if user.role == "doctor" and a.doctor.user_id == user.id: return a
    raise HTTPException(403, "Not allowed")

@router.post("/appointments/{appointment_id}/consultation", status_code=201)
def write_consultation(appointment_id: int, data: ConsultationIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = get_authorized_appointment(db, appointment_id, user)
    if user.role != "doctor" or a.doctor.user_id != user.id: raise HTTPException(403, "Only the assigned doctor can write a consultation")
    if a.status != "In Consultation": raise HTTPException(409, "Appointment must be In Consultation")
    if a.consultation: raise HTTPException(409, "Consultation already exists")
    c = Consultation(appointment_id=a.id, **data.model_dump())
    a.status = "Completed"
    db.add(c); db.commit(); db.refresh(c)
    return c

@router.get("/appointments/{appointment_id}/consultation")
def read_consultation(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = get_authorized_appointment(db, appointment_id, user)
    if not a.consultation: raise HTTPException(404, "Consultation not found")
    return a.consultation

@router.post("/appointments/{appointment_id}/files", status_code=201)
async def upload_file(appointment_id: int, file: UploadFile = File(...), file_type: str = "Lab Report",
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = get_authorized_appointment(db, appointment_id, user)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED: raise HTTPException(415, "Only PDF, JPG, and PNG files are allowed")
    if user.role == "patient" and a.patient_id != user.id: raise HTTPException(403, "Not your appointment")
    if user.role == "doctor" and a.doctor.user_id != user.id: raise HTTPException(403, "Not your patient")
    if user.role == "patient" and file_type != "Lab Report": raise HTTPException(403, "Patients may upload lab reports only")
    if user.role == "doctor" and file_type not in ("Prescription", "Scan"): raise HTTPException(400, "Doctors may upload prescriptions or scans")
    contents = await file.read(5 * 1024 * 1024 + 1)
    if len(contents) > 5 * 1024 * 1024: raise HTTPException(413, "File exceeds 5 MB")
    stored = f"{uuid4().hex}{ext}"
    with open(os.path.join(UPLOAD_DIR, stored), "wb") as out: out.write(contents)
    consultation = a.consultation
    record = UploadedFile(appointment_id=a.id, consultation_id=consultation.id if consultation else None,
        uploaded_by=user.id, file_type=file_type, original_name=file.filename or "upload", stored_name=stored,
        size_kb=max(1, len(contents)//1024))
    db.add(record); db.commit(); db.refresh(record)
    return record

@router.get("/appointments/{appointment_id}/files")
def list_files(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    get_authorized_appointment(db, appointment_id, user)
    return db.query(UploadedFile).filter_by(appointment_id=appointment_id).all()

@router.get("/files/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    record = db.get(UploadedFile, file_id)
    if not record: raise HTTPException(404, "File not found")
    get_authorized_appointment(db, record.appointment_id, user)
    path = os.path.join(UPLOAD_DIR, record.stored_name)
    if not os.path.isfile(path): raise HTTPException(404, "Stored file not found")
    return FileResponse(path, filename=record.original_name)

@router.get("/patients/me/history")
def patient_history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role != "patient": raise HTTPException(403, "Patients only")
    return db.query(Appointment).filter(Appointment.patient_id == user.id).order_by(Appointment.appointment_date.desc()).all()
