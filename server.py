import asyncio
import json
import logging
import os
import signal
import subprocess
import threading
import uuid
from datetime import datetime
from typing import Dict, Optional

import psutil
import uvicorn
import websockets
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SessionRequest(BaseModel):
    user_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    cdp_url: str
    created_at: str


class BrowserSession:
    def __init__(self, session_id, process, port):
        self.session_id = session_id
        self.process = process
        self.port = port
        self.created_at = datetime.now().isoformat()
        self.events = []


browser_sessions: Dict[str, BrowserSession] = {}
monitoring_tasks = {}


def log_output(process, session_id):
    """Read process output and log it"""
    try:
        for line in iter(process.stdout.readline, ''):
            logger.info(f"Chrome session {session_id}: {line.strip()}")
    except Exception as e:
        logger.error(f"Error logging output for {session_id}: {e}")


async def monitor_browser_session(session_id: str, port: int):
    cdp_host = os.environ.get("CDP_HOST", "host.docker.internal")
    cdp_url = f"ws://localhost:{port}/json/version"
    browser_info_response = None

    for _ in range(20):
        try:
            async with websockets.connect(cdp_url) as websocket:
                browser_info_response = await websocket.recv()
                break
        except Exception as e:
            await asyncio.sleep(0.5)
    else:
        logger.error(f"Could not connect to browser on port {port}")
        return

    browser_info = json.loads(browser_info_response)
    webSocketDebuggerUrl = browser_info.get("webSocketDebuggerUrl", "").replace(
        "localhost", cdp_host
    )

    try:
        async with websockets.connect(webSocketDebuggerUrl) as websocket:
            await websocket.send(json.dumps({"id": 1, "method": "Network.enable"}))
            await websocket.send(json.dumps({"id": 2, "method": "Page.enable"}))
            await websocket.send(json.dumps({"id": 3, "method": "Runtime.enable"}))

            while session_id in browser_sessions:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    event = json.loads(message)
                    if session_id in browser_sessions:
                        browser_sessions[session_id].events.append(event)
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error monitoring session {session_id}: {e}")
                    break
    except Exception as e:
        logger.error(f"Failed to connect to CDP: {e}")


@app.post("/sessions", response_model=SessionResponse)
async def create_session(request: SessionRequest):
    session_id = str(uuid.uuid4())
    port = find_free_port()

    chrome_bin = os.environ.get("CHROME_BIN", "google-chrome")
    cmd = [
        chrome_bin,
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=0.0.0.0",  
        "--disable-gpu",
        "--headless",  
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
    except Exception as e:
        logger.error(f"Failed to start Chrome: {e}")
        raise HTTPException(status_code=500, detail="Failed to start browser")

    log_thread = threading.Thread(
        target=log_output, args=(process, session_id), daemon=True
    )
    log_thread.start()

    await asyncio.sleep(1)
    if process.poll() is not None:
        output = (
            process.stdout.read() if process.stdout else "Process exited immediately"
        )
        logger.error(f"Browser process failed: {output}")
        raise HTTPException(status_code=500, detail=output)

    browser_sessions[session_id] = BrowserSession(
        session_id=session_id, process=process, port=port
    )

    monitoring_task = asyncio.create_task(monitor_browser_session(session_id, port))
    monitoring_tasks[session_id] = monitoring_task

    cdp_host = os.environ.get("CDP_HOST", "host.docker.internal")
    cdp_url = f"ws://{cdp_host}:{port}"
    return SessionResponse(
        session_id=session_id,
        cdp_url=cdp_url,
        created_at=browser_sessions[session_id].created_at,
    )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    if session_id not in browser_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = browser_sessions[session_id]
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "cdp_url": f"ws://{os.environ.get('CDP_HOST', 'host.docker.internal')}:{session.port}",
        "alive": is_process_running(session.process.pid),
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id not in browser_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = browser_sessions[session_id]

    try:
        if is_process_running(session.process.pid):
            os.kill(session.process.pid, signal.SIGTERM)
            logger.info(f"Terminated process {session.process.pid}")
    except Exception as e:
        logger.error(f"Error terminating process: {e}")

    if session_id in monitoring_tasks:
        monitoring_tasks[session_id].cancel()
        del monitoring_tasks[session_id]

    del browser_sessions[session_id]
    return {"status": "success", "message": f"Session {session_id} terminated"}


def find_free_port(start_port=9222, end_port=9322):
    import socket

    for port in range(start_port, end_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('', port))
                return port
            except OSError:
                continue
    raise IOError(f"No free ports in range {start_port}-{end_port}")


def is_process_running(pid):
    try:
        return psutil.pid_exists(pid)
    except:
        return False


@app.on_event("shutdown")
async def shutdown_event():
    for session_id, session in list(browser_sessions.items()):
        try:
            if is_process_running(session.process.pid):
                os.kill(session.process.pid, signal.SIGKILL)
        except Exception as e:
            logger.error(f"Error killing process {session.process.pid}: {e}")

        if session_id in monitoring_tasks:
            monitoring_tasks[session_id].cancel()

    browser_sessions.clear()
    monitoring_tasks.clear()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
