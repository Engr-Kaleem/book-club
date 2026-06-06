"""
Simple token-based authentication and rate limiting middleware.

This module provides:
    - Token extraction and user identification from Authorization headers
    - A simple in-memory rate limiter keyed by client identity

The auth system is intentionally simple for this project — tokens are
just "token-<user_id>" strings. In production you'd use JWT or OAuth.
"""

import time
from typing import Optional

from fastapi import Header, HTTPException, Request
from sqlalchemy.orm import Session

from bookclub.database import get_db
from bookclub.models import User


# ---------------------------------------------------------------------------
# Token-based authentication
# ---------------------------------------------------------------------------

def get_current_user_id(authorization: Optional[str] = Header(None)) -> Optional[int]:
    """
    Extract the user ID from the Authorization header.

    Expected format: "Bearer token-<user_id>"
    Returns None if no Authorization header is present.
    Raises 401 if the header is present but malformed.
    """
    if authorization is None:
        return None

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = parts[1]
    if not token.startswith("token-"):
        raise HTTPException(status_code=401, detail="Invalid token format")

    try:
        user_id = int(token[len("token-"):])
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token: user ID must be numeric")

    return user_id


def require_auth(authorization: Optional[str] = Header(None)) -> int:
    """
    Like get_current_user_id, but raises 401 if not authenticated.
    Use this dependency for endpoints that require authentication.
    """
    user_id = get_current_user_id(authorization)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """
    Simple in-memory rate limiter using a token bucket algorithm.

    Each client gets a bucket identified by their client_id (derived from
    the auth token). The bucket allows `max_requests` requests per `window_seconds`.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, dict] = {}
        self._exempt_paths = {
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            "/openapi.json",
        }

    def _is_exempt_path(self, path: str) -> bool:
        """Return True when a path should bypass rate limiting."""
        return path in self._exempt_paths

    def _get_or_create_bucket(self, client_id: str) -> dict:
        """Get or create a rate limit bucket for the given client."""
        now = time.time()
        if client_id not in self._buckets:
            self._buckets[client_id] = {
                "count": 0,
                "window_start": now,
            }
        bucket = self._buckets[client_id]
        # Reset bucket if the window has expired
        if now - bucket["window_start"] >= self.window_seconds:
            bucket["count"] = 0
            bucket["window_start"] = now
        return bucket

    def _resolve_client_id(self, request: Request, authorization: Optional[str]) -> str:
        """Resolve a stable client identifier from auth token or client IP."""
        if authorization:
            parts = authorization.split(" ")
            if len(parts) == 2 and parts[0] == "Bearer" and parts[1].startswith("token-"):
                return parts[1]

        # Prefer the ASGI scope to avoid Request.client parsing failures from
        # malformed test scopes or unusual server adapters.
        client_from_scope = request.scope.get("client")
        if isinstance(client_from_scope, (tuple, list)) and client_from_scope:
            host = client_from_scope[0]
            if isinstance(host, str) and host:
                return f"ip:{host}"

        try:
            client = request.client
        except Exception:
            client = None

        host = getattr(client, "host", None)
        if isinstance(host, str) and host:
            return f"ip:{host}"

        return "anonymous"

    def rate_limit_check(self, request: Request, authorization: Optional[str] = None):
        """
        FastAPI dependency that enforces rate limiting.

        Extracts the client_id from the auth token. If the client has
        exceeded max_requests in the current window, raises HTTP 429.
        """
        if self._is_exempt_path(request.url.path):
            return

        header_value = authorization if isinstance(authorization, str) else None
        if header_value is None:
            header_value = request.headers.get("Authorization")

        client_id = self._resolve_client_id(request, header_value)
        bucket = self._get_or_create_bucket(client_id)
        bucket["count"] += 1

        if bucket["count"] > self.max_requests:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
            )


# Global rate limiter instance
rate_limiter = RateLimiter()
