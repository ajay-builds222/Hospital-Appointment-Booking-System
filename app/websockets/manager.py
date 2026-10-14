from collections import defaultdict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.queues: dict[int, set[WebSocket]] = defaultdict(set)
        self.users: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect_queue(self, doctor_id: int, ws: WebSocket):
        await ws.accept()
        self.queues[doctor_id].add(ws)

    async def connect_user(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.users[user_id].add(ws)

    def disconnect_queue(self, doctor_id: int, ws: WebSocket):
        self.queues[doctor_id].discard(ws)

    def disconnect_user(self, user_id: int, ws: WebSocket):
        self.users[user_id].discard(ws)

    async def broadcast_queue(self, doctor_id: int, payload: dict):
        dead = []
        for ws in list(self.queues[doctor_id]):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_queue(doctor_id, ws)

    async def notify_user(self, user_id: int, payload: dict):
        dead = []
        for ws in list(self.users[user_id]):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_user(user_id, ws)

manager = ConnectionManager()
