"""
Tests for authentication and rate limiting.
"""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from bookclub.auth import RateLimiter


class TestAuth:
    """Tests for token-based authentication."""

    def test_valid_token(self, client, sample_user):
        response = client.get(
            f"/users/{sample_user.id}",
            headers={"Authorization": f"Bearer token-{sample_user.id}"},
        )
        assert response.status_code == 200

    def test_no_token_on_public_endpoint(self, client, sample_user):
        """Public endpoints should work without auth."""
        response = client.get(f"/users/{sample_user.id}")
        assert response.status_code == 200

    def test_malformed_token(self, client, sample_books):
        response = client.post(
            f"/books/{sample_books[0].id}/reviews",
            json={"rating": 4, "text": "Good book"},
            headers={"Authorization": "Bearer bad-token"},
        )
        assert response.status_code == 401

    def test_missing_token_on_protected_endpoint(self, client, sample_books):
        """Review creation requires auth."""
        response = client.post(
            f"/books/{sample_books[0].id}/reviews",
            json={"rating": 4, "text": "Good book"},
        )
        assert response.status_code == 401


class TestRateLimiter:
    """Tests for the rate limiting middleware."""

    def test_rate_limiter_authenticated(self):
        """Authenticated requests should be rate limited by client token."""
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/books",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )

        for _ in range(5):
            limiter.rate_limit_check(request, authorization="Bearer token-1")

        with pytest.raises(HTTPException) as exc_info:
            limiter.rate_limit_check(request, authorization="Bearer token-1")

        assert exc_info.value.status_code == 429

    def test_rate_limiter_no_auth_header_does_not_crash(self):
        """Unauthenticated requests should be bucketed by IP, not crash."""
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/books",
                "headers": [],
                "client": ("127.0.0.1", 9999),
            }
        )

        limiter.rate_limit_check(request)
        limiter.rate_limit_check(request)

        with pytest.raises(HTTPException) as exc_info:
            limiter.rate_limit_check(request)

        assert exc_info.value.status_code == 429

    def test_rate_limiter_no_auth_with_malformed_client_does_not_crash(self):
        """Malformed client metadata should fall back to anonymous bucketing."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/books",
                "headers": [],
                "client": "invalid-client-shape",
            }
        )

        limiter.rate_limit_check(request)

        with pytest.raises(HTTPException) as exc_info:
            limiter.rate_limit_check(request)

        assert exc_info.value.status_code == 429

    def test_rate_limiter_exempts_docs_and_openapi_paths(self):
        """Docs endpoints should bypass global rate limiting."""
        limiter = RateLimiter(max_requests=1, window_seconds=60)

        docs_request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/docs",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )
        openapi_request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/openapi.json",
                "headers": [],
                "client": ("127.0.0.1", 12345),
            }
        )

        for _ in range(3):
            limiter.rate_limit_check(docs_request)
            limiter.rate_limit_check(openapi_request)

