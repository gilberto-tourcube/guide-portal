"""Sentry utility functions for error tracking with dynamic context"""

from typing import Optional
import sentry_sdk
from fastapi import Request


def capture_exception_with_context(
    exception: Exception,
    request: Optional[Request] = None,
    mode: Optional[str] = None,
    company_code: Optional[str] = None,
    **extra_tags
) -> None:
    """
    Capture an exception to Sentry with dynamic context from the request.

    This allows the mode (Test/Production) from the querystring or session
    to override the default APP_ENV environment, making it easier to filter
    errors in Sentry by the actual user context.

    Args:
        exception: The exception to capture
        request: Optional FastAPI Request object to extract session data
        mode: Optional mode override (Test/Production)
        company_code: Optional company code override
        **extra_tags: Additional tags to include in the Sentry event

    Usage:
        # In route handlers with request available:
        capture_exception_with_context(e, request=request)

        # In services without request:
        capture_exception_with_context(e, mode=mode, company_code=company_code)

        # With extra tags:
        capture_exception_with_context(e, request=request, user_id=123)
    """
    # Try to extract mode and company_code from request session if not provided
    if request is not None:
        if mode is None:
            mode = request.session.get("mode")
        if company_code is None:
            company_code = request.session.get("company_code")

    # Set tags for this specific event
    with sentry_sdk.push_scope() as scope:
        # Add mode tag (normalizes Test -> test, Production -> production)
        if mode:
            normalized_mode = mode.lower()
            scope.set_tag("mode", normalized_mode)
            # Also set environment tag to override the default if different
            scope.set_tag("user_mode", normalized_mode)

        # Add company_code tag
        if company_code:
            scope.set_tag("company_code", company_code)

        # Add any extra tags
        for key, value in extra_tags.items():
            scope.set_tag(key, value)

        # Capture the exception with this scope
        sentry_sdk.capture_exception(exception)
