import os
import time
import json
import uuid
import signal
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from utils.mock_llm import ask

# Redis
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))
PORT = int(os.getenv("PORT", "8000"))
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_is_shutting_down = False
_in_flight_requests = 0

r = redis.from_url(REDIS_URL, decode_responses=True)


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None


def session_key(session_id: str) -> str:
    return f"session:{session_id}"


def save_session(session_id: str, data: dict) -> None:
    r.setex(session_key(session_id), SESSION_TTL_SECONDS, json.dumps(data))


def load_session(session_id: str) -> dict:
    raw = r.get(session_key(session_id))
    return json.loads(raw) if raw else {}


def append_to_history(session_id: str, role: str, content: str) -> list[dict]:
    session = load_session(session_id)
    history = session.get("history", [])
    history.append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    history = history[-MAX_HISTORY_MESSAGES:]
    session["history"] = history
    save_session(session_id, session)
    return history


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _is_shutting_down

    logger.info(f"Starting instance {INSTANCE_ID}")
    logger.info("Connecting to Redis...")
    r.ping()
    logger.info("Redis connected")
    _is_ready = True
    _is_shutting_down = False
    logger.info("Agent is ready")

    yield

    logger.info("Graceful shutdown initiated...")
    _is_ready = False
    _is_shutting_down = True

    timeout = 30
    waited = 0
    while _in_flight_requests > 0 and waited < timeout:
        logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
        time.sleep(1)
        waited += 1

    logger.info("Shutdown complete")


app = FastAPI(
    title="Stateless Agent with Redis",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_requests(request, call_next):
    global _in_flight_requests

    if _is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"detail": "Server is shutting down"},
        )

    _in_flight_requests += 1
    try:
        response = await call_next(request)
        return response
    finally:
        _in_flight_requests -= 1


@app.get("/")
def root():
    return {
        "message": "Stateless Agent with Redis session storage",
        "instance_id": INSTANCE_ID,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    if not _is_ready or _is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "instance_id": INSTANCE_ID},
        )

    try:
        r.ping()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "detail": "Redis unavailable"},
        )

    return {
        "status": "ready",
        "instance_id": INSTANCE_ID,
        "in_flight_requests": _in_flight_requests,
    }


@app.post("/ask")
async def ask_agent(body: ChatRequest):
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty")

    session_id = body.session_id or str(uuid.uuid4())

    append_to_history(session_id, "user", question)

    session = load_session(session_id)
    history = session.get("history", [])

    # In real app, you would pass history into the LLM prompt.
    answer = ask(question)

    append_to_history(session_id, "assistant", answer)

    updated = load_session(session_id)
    updated_history = updated.get("history", [])

    return {
        "session_id": session_id,
        "question": question,
        "answer": answer,
        "history_count": len(updated_history),
        "recent_history": updated_history[-4:],
        "served_by": INSTANCE_ID,
        "storage": "redis",
    }


@app.get("/chat/{session_id}/history")
def get_history(session_id: str):
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    history = session.get("history", [])
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history),
        "served_by": INSTANCE_ID,
    }


@app.delete("/chat/{session_id}")
def delete_session(session_id: str):
    r.delete(session_key(session_id))
    return {
        "deleted": session_id,
        "served_by": INSTANCE_ID,
    }


def shutdown_handler(signum, frame):
    global _is_ready, _is_shutting_down
    logger.info(f"Received signal {signum}")
    _is_ready = False
    _is_shutting_down = True


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        timeout_graceful_shutdown=30,
    )