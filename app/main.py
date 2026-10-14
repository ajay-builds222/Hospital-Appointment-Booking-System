from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from app.jobs.scheduler import start_scheduler, stop_scheduler
from app.routers import auth, catalog, scheduling, appointments, consultations, live, reports

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="Hospital Appointment Booking System", version="1.0.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(scheduling.router)
app.include_router(appointments.router)
app.include_router(consultations.router)
app.include_router(live.router)
app.include_router(reports.router)

@app.get("/", tags=["Health"])
def root():
    return {"message": "Hospital Appointment Booking System API", "docs": "/docs"}

@app.get("/queue-test", response_class=HTMLResponse, include_in_schema=True)
def queue_test():
    return '''<!doctype html><html><head><meta charset="utf-8"><title>Queue WebSocket Test</title></head>
<body><h2>Live Queue Test</h2><label>Doctor ID <input id="doctor" value="1"></label>
<label>Access token <input id="token" style="width:420px" placeholder="Paste access token"></label>
<button onclick="connect()">Connect</button><pre id="messages"></pre>
<script>
let ws;
function connect(){
 if(ws) ws.close();
 const proto = location.protocol === "https:" ? "wss" : "ws";
 const url = `${proto}://${location.host}/ws/queue/${document.getElementById('doctor').value}?token=${encodeURIComponent(document.getElementById('token').value)}`;
 ws = new WebSocket(url);
 ws.onmessage = e => document.getElementById('messages').textContent += e.data + "\\n";
 ws.onclose = () => document.getElementById('messages').textContent += "Disconnected\\n";
 ws.onerror = () => document.getElementById('messages').textContent += "WebSocket error\\n";
}
</script></body></html>'''
