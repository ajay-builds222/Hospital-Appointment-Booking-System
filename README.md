# Hospital Appointment Booking System

A FastAPI backend starter for hospital departments, doctors, schedules, appointments, consultations, file uploads, live queues, scheduled jobs, and reports.

## Requirements
- Python 3.9+ (Python 3.11+ recommended)
- MySQL 8+
- SMTP account/app password for email delivery

## Setup (Windows PowerShell)
1. Create a MySQL database:
   ```sql
   CREATE DATABASE hospital_appointment_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and set your MySQL password, a strong JWT secret, and SMTP app password. Never commit `.env`.
5. Create the Alembic migration and apply it:
   ```powershell
   alembic revision --autogenerate -m "initial schema"
   alembic upgrade head
   ```
6. Start the API:
   ```powershell
   uvicorn app.main:app --reload
   ```
7. Open Swagger at http://127.0.0.1:8000/docs and WebSocket test page at http://127.0.0.1:8000/queue-test.

## Authentication
- `POST /auth/register` creates Patient accounts only.
- `POST /auth/login` returns access and refresh tokens.
- Use `Authorization: Bearer <access_token>` for protected routes.
- `POST /auth/refresh` body: `{"refresh_token":"..."}`.
- `POST /auth/logout` body: `{"refresh_token":"..."}`.
- `GET /auth/me` returns the current user.

**Admin bootstrap:** Public registration deliberately cannot create an Admin. Create the first Admin through a controlled one-time database/seed procedure before using admin-only APIs. Do not expose an unauthenticated role-upgrade endpoint.

## Main API groups
- Authentication: `/auth/*`
- Departments and doctors: `/departments`, `/doctors`
- Schedules and leaves: `/doctors/{doctor_id}/schedules`, `/doctors/{doctor_id}/leaves`, `/doctors/{doctor_id}/available-slots`
- Appointments: `/appointments`
- Consultations and files: `/appointments/{appointment_id}/consultation`, `/appointments/{appointment_id}/files`, `/files/{file_id}/download`, `/patients/me/history`
- WebSockets: `/ws/queue/{doctor_id}?token=<access_token>`, `/ws/notifications?token=<access_token>`
- Reports: `/reports/*`

## Email
Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM` in `.env`. Gmail typically requires an App Password with two-step verification enabled. Email failures are logged and do not undo the main API operation.

## WebSocket testing
1. Login to obtain an access token.
2. Open `/queue-test`, enter doctor ID and token, and click Connect.
3. Check in a patient or call the next patient from Swagger and watch the message area.

Alternatively use browser console:
```javascript
const ws = new WebSocket("ws://localhost:8000/ws/queue/1?token=YOUR_ACCESS_TOKEN");
ws.onmessage = e => console.log("Queue update:", e.data);
```

## Important implementation notes
This ZIP is a starter implementation, not a certified or fully verified hospital production system. Review the code before real use. Before production, complete and test: database-level concurrency-safe token assignment, strict slot uniqueness and transaction locking, cancellation notifications for leave, complete history on every status transition, patient-specific WebSocket queue views, exact reminder/no-show time-window checks, secure admin bootstrap, and integration tests. Protect medical data and uploads according to applicable law and organizational policy.
