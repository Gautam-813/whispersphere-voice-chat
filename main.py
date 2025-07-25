from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import threading
import time
import webbrowser
import json
from collections import defaultdict, deque

app = FastAPI()

# Serve the frontend (index.html) from the 'frontend' directory
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# @app.on_event("startup")
# def open_browser():
#     def _open():
#         time.sleep(1)  # Wait for server to start
#         webbrowser.open("http://localhost:8000")
#     threading.Thread(target=_open).start()

@app.get("/")
def get_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# In-memory room management: room_code -> set of (WebSocket, encrypted_nickname, nickiv, pubkey)
rooms = {}

# Simple in-memory rate limiting: IP -> deque of timestamps
RATE_LIMIT = 10  # max connections per minute per IP
rate_limit_window = 60  # seconds
ip_conn_times = defaultdict(lambda: deque(maxlen=RATE_LIMIT))

def is_rate_limited(ip: str) -> bool:
    now = time.time()
    dq = ip_conn_times[ip]
    # Remove old timestamps
    while dq and now - dq[0] > rate_limit_window:
        dq.popleft()
    if len(dq) >= RATE_LIMIT:
        return True
    dq.append(now)
    return False

async def broadcast_user_list(room_code):
    users = [{"data": nick, "iv": nickiv} for _, nick, nickiv, _ in rooms[room_code]]
    message = json.dumps({"type": "userlist", "users": users, "count": len(users)})
    for ws, _, _, _ in rooms[room_code]:
        await ws.send_text(message)

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    client_ip = websocket.client.host if websocket.client else None
    if client_ip and is_rate_limited(client_ip):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    enc_nickname = None
    nickiv = None
    pubkey = None
    if room_code not in rooms:
        rooms[room_code] = set()
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "pubkey":
                enc_nickname = msg.get("nickname")
                nickiv = msg.get("nickiv")
                pubkey = msg.get("key")
                # Send all existing users' pubkeys to the new user
                for ws, nick, niv, key in rooms[room_code]:
                    if ws != websocket:
                        await websocket.send_text(json.dumps({"type": "pubkey", "nickname": nick, "nickiv": niv, "key": key}))
                # Add new user to the room
                rooms[room_code].add((websocket, enc_nickname, nickiv, pubkey))
                # Notify others of join
                join_msg = json.dumps({"type": "join", "nickname": enc_nickname, "nickiv": nickiv})
                for ws, _, _, _ in rooms[room_code]:
                    if ws != websocket:
                        await ws.send_text(join_msg)
                        # Send new user's pubkey to existing users
                        await ws.send_text(json.dumps({"type": "pubkey", "nickname": enc_nickname, "nickiv": nickiv, "key": pubkey}))
                await broadcast_user_list(room_code)
            elif msg.get("type") == "msg":
                # Relay encrypted message to others
                for ws, _, _, _ in rooms[room_code]:
                    if ws != websocket:
                        await ws.send_text(data)
            elif msg.get("type") in ["file_start", "file_chunk", "file_complete"]:
                # Relay file messages to others (real-time file sharing)
                for ws, _, _, _ in rooms[room_code]:
                    if ws != websocket:
                        await ws.send_text(data)
            elif msg.get("type") == "clear_chat":
                # Relay clear chat message to others
                for ws, _, _, _ in rooms[room_code]:
                    if ws != websocket:
                        await ws.send_text(data)
            elif msg.get("type") in ["call_offer", "call_answer", "call_reject", "call_end", "audio_chunk", "call_status"]:
                # Relay voice call messages to others (encrypted audio chunks and call control)
                for ws, _, _, _ in rooms[room_code]:
                    if ws != websocket:
                        await ws.send_text(data)
    except WebSocketDisconnect:
        if enc_nickname:
            rooms[room_code] = set([t for t in rooms[room_code] if t[0] != websocket])
            # Notify others of leave
            leave_msg = json.dumps({"type": "leave", "nickname": enc_nickname, "nickiv": nickiv})
            for ws, _, _, _ in rooms.get(room_code, set()):
                await ws.send_text(leave_msg)
            if room_code in rooms and rooms[room_code]:
                await broadcast_user_list(room_code)
            else:
                rooms.pop(room_code, None)

if __name__ == "__main__":
    import uvicorn
    import logging

    # Disable all logging for maximum privacy
    logging.getLogger("uvicorn").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn.access").setLevel(logging.CRITICAL)
    logging.getLogger("uvicorn.error").setLevel(logging.CRITICAL)
    logging.getLogger("fastapi").setLevel(logging.CRITICAL)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="critical",
        access_log=False
    )