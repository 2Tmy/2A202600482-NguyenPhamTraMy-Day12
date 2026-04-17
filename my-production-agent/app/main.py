from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse

from .config import settings
from .auth import verify_api_key
from .rate_limiter import check_rate_limit
from .cost_guard import check_budget

app = FastAPI()

# Optional Redis client
r = None
try:
    import redis

    if getattr(settings, "REDIS_URL", None):
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
except Exception:
    r = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if r is None:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "redis unavailable"},
        )

    try:
        r.ping()
        return {"status": "ready"}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "redis ping failed"},
        )


@app.post("/ask")
def ask(
    question: str,
    user_id: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    history_key = f"history:{user_id}"
    history = []

    if r is not None:
        try:
            history = r.lrange(history_key, 0, -1)
        except Exception:
            history = []

    answer = f"Mock answer: I received your question: {question}"

    if r is not None:
        try:
            r.rpush(history_key, f"user: {question}")
            r.rpush(history_key, f"assistant: {answer}")
            r.ltrim(history_key, -settings.HISTORY_LIMIT, -1)
        except Exception:
            pass

    history_count = len(history) + 2 if history else 2

    return {
        "user_id": user_id,
        "question": question,
        "answer": answer,
        "history_count": history_count,
        "redis_enabled": r is not None,
    }