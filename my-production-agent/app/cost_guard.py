import redis
from fastapi import HTTPException, status
from app.config import settings

r = redis.from_url(settings.REDIS_URL, decode_responses=True)

def check_budget(user_id: str, monthly_limit: float = 50.0):
    key = f"budget:{user_id}"
    
    current_spend = r.get(key)
    
    if current_spend and float(current_spend) >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly budget exceeded."
        )