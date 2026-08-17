import hmac

from fastapi import Header, HTTPException

from app.config import CGM_SHARED_SECRET


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    # Fails closed: an unset CGM_SHARED_SECRET means every request is
    # rejected, not silently allowed through. Set CGM_SHARED_SECRET in the
    # environment (both here and in mobile-bridge) before running either
    # service, even locally.
    if not CGM_SHARED_SECRET or not x_api_key or not hmac.compare_digest(x_api_key, CGM_SHARED_SECRET):
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
