"""
BASIC — Health Check + Graceful Shutdown

Hai tính năng tối thiểu cần có trước khi deploy:
  1. GET /health  — liveness: "agent có còn sống không?"
  2. GET /ready   — readiness: "agent có sẵn sàng nhận request chưa?"
  3. Graceful shutdown: hoàn thành request hiện tại trước khi tắt

Chạy:
    python app.py

Test health check:
    curl http://localhost:8000/health
    curl http://localhost:8000/ready

Simulate shutdown:
    # Trong terminal khác
    kill -SIGTERM <pid>
    # Xem agent log graceful shutdown message
"""

import os
import time
import signal
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from utils.mock_llm import ask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_is_shutting_down = False
_in_flight_requests = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _is_shutting_down

    # Startup
    logger.info("Agent starting up...")
    logger.info("Loading model and checking dependencies...")
    time.sleep(0.2)  # simulate startup time
    _is_ready = True
    _is_shutting_down = False
    logger.info("✅ Agent is ready!")

    yield

    # Shutdown
    _is_ready = False
    _is_shutting_down = True
    logger.info("🔄 Graceful shutdown initiated...")

    # Chờ request hiện tại hoàn thành tối đa 30 giây
    timeout = 30
    waited = 0
    while _in_flight_requests > 0 and waited < timeout:
        logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
        time.sleep(1)
        waited += 1

    logger.info("✅ Shutdown complete")


app = FastAPI(title="Agent — Health Check Demo", lifespan=lifespan)


@app.middleware("http")
async def track_requests(request, call_next):
    """Theo dõi số request đang xử lý."""
    global _in_flight_requests

    # Khi đang shutdown thì từ chối request mới
    if _is_shutting_down:
        return JSONResponse(
            status_code=503,
            content={"status": "shutting_down", "detail": "Server is shutting down"},
        )

    _in_flight_requests += 1
    try:
        response = await call_next(request)
        return response
    finally:
        _in_flight_requests -= 1


@app.get("/")
def root():
    return {"message": "AI Agent with health checks!"}


@app.post("/ask")
async def ask_agent(question: str):
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Agent not ready")

    # giả lập xử lý hơi lâu để test graceful shutdown
    time.sleep(2)

    return {"answer": ask(question)}


# ─────────────────────────────────────────
# Exercise 5.1 — Health / Ready
# ─────────────────────────────────────────

@app.get("/health")
def health():
    """Liveness probe — container còn sống không?"""
    uptime = round(time.time() - START_TIME, 1)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    """Readiness probe — sẵn sàng nhận traffic không?"""
    try:
        if not _is_ready or _is_shutting_down:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not ready",
                    "ready": False,
                    "shutting_down": _is_shutting_down,
                },
            )

        # Nếu có Redis / DB thật thì check ở đây
        # Ví dụ:
        # r.ping()
        # db.execute("SELECT 1")

        return {
            "status": "ready",
            "ready": True,
            "in_flight_requests": _in_flight_requests,
        }
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "ready": False},
        )


# ─────────────────────────────────────────
# Exercise 5.2 — Graceful Shutdown
# ─────────────────────────────────────────

def shutdown_handler(signum, frame):
    """Handle SIGTERM from container orchestrator"""
    global _is_ready, _is_shutting_down

    logger.info(f"Received signal {signum}. Starting graceful shutdown...")
    _is_ready = False
    _is_shutting_down = True
    # Uvicorn sẽ tiếp tục xử lý shutdown thật qua lifespan


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting agent on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_graceful_shutdown=30,
    )