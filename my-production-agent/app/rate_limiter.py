import time
import redis
from fastapi import HTTPException, status
from app.config import settings # Assuming settings are imported here

r = redis.from_url(settings.REDIS_URL, decode_responses=True)

def check_rate_limit(user_id: str, limit: int = 100, window_seconds: int = 60):
    """
    Implements a sliding window rate limit using Redis Sorted Sets.
    """
    now = time.time()
    key = f"rate_limit:{user_id}"
    window_start = now - window_seconds

    # Use a pipeline to ensure atomicity and reduce round-trips
    pipe = r.pipeline()

    # 1. Remove timestamps older than the current window
    pipe.zremrangebyscore(key, 0, window_start)
    
    # 2. Count the remaining elements in the set
    pipe.zcard(key)
    
    # 3. Add the current request timestamp
    pipe.zadd(key, {str(now): now})
    
    # 4. Set an expiration on the key to clean up idle users
    pipe.expire(key, window_seconds)
    
    # Execute the pipeline
    _, current_count, _, _ = pipe.execute()

    if current_count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )