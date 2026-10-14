from datetime import date
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError
from sqlalchemy.orm import Session
from app.auth.security import decode_token
from app.database import SessionLocal, get_db
from app.models.models import Appointment, Doctor, User
from app.routers.auth import current_user, require_roles
from app.websockets.manager import manager

router = APIRouter(tags=["Live Queue"])

def ws_user(token: str, db: Session):
    try:
        payload = decode_token(token)
        if payload.get("type") != "access": return None
        user = db.get(User, int(payload["sub"]))
        return user if user and user.is_active else None
    except (JWTError, ValueError, KeyError):
        return None

@router.websocket("/ws/queue/{doctor_id}")
async def queue_ws(ws: WebSocket, doctor_id: int, token: str):
    db = SessionLocal()
    user = ws_user(token, db)
    doctor = db.get(Doctor, doctor_id)
    if not user or not doctor or (user.role == "doctor" and doctor.user_id != user.id):
        await ws.close(code=1008); db.close(); return
    await manager.connect_queue(doctor_id, ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_queue(doctor_id, ws)
    finally: db.close()

@router.websocket("/ws/notifications")
async def notifications_ws(ws: WebSocket, token: str):
    db = SessionLocal()
    user = ws_user(token, db)
    if not user:
        await ws.close(code=1008); db.close(); return
    await manager.connect_user(user.id, ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_user(user.id, ws)
    finally: db.close()

@router.put("/doctors/me/call-next")
async def call_next(db: Session = Depends(get_db), user: User = Depends(require_roles("doctor"))):
    doctor = db.query(Doctor).filter_by(user_id=user.id).first()
    if not doctor: raise HTTPException(404, "Doctor profile not found")
    current = db.query(Appointment).filter_by(doctor_id=doctor.id, appointment_date=date.today(), status="In Consultation").first()
    if current: raise HTTPException(409, "Complete the current consultation before calling next")
    next_appt = db.query(Appointment).filter_by(doctor_id=doctor.id, appointment_date=date.today(), status="Checked-In").order_by(Appointment.token_number).first()
    if not next_appt: raise HTTPException(404, "No checked-in patients waiting")
    next_appt.status = "In Consultation"
    db.commit()
    waiting = db.query(Appointment).filter_by(doctor_id=doctor.id, appointment_date=date.today(), status="Checked-In").count()
    await manager.broadcast_queue(doctor.id, {"current_token": next_appt.token_number, "waiting": waiting})
    await manager.notify_user(next_appt.patient_id, {"message": "You are next, please be ready", "appointment_id": next_appt.id})
    return {"message": "Patient called", "token_number": next_appt.token_number, "waiting": waiting}
