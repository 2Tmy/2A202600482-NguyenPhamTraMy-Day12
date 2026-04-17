from fastapi import Header, HTTPException
from .config import settings


def verify_api_key(x_api_key: str = Header(...)):
    # Check missing
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Verify key
    if x_api_key != settings.AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Return user_id (simple mapping)
    return "user_1"