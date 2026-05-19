"""Mobile detection middleware (ported from guest-portal #163).

Sets ``request.state.is_mobile`` based on the User-Agent header so templates
and routes can gate PWA emission (manifest, service worker, install hints,
Save Offline button) to phones and tablets only.

The check is intentionally lenient: any UA token matching a known mobile
or tablet keyword flips the flag. Desktop Chrome/Safari/Firefox stay False
and therefore see a plain website. iPad on iPadOS 13+ ships a desktop
Safari UA — for that case we rely on the client-side viewport guard in
``pwa_head.html``.
"""

from __future__ import annotations

import re

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

_MOBILE_UA_RE = re.compile(
    r"iPhone|iPod|Android.*Mobile|Mobile.*Android|iPad|Tablet|"
    r"Mobile Safari|Opera Mini|IEMobile|Windows Phone|BlackBerry|"
    r"Kindle|Silk",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str) -> bool:
    """Return True when the UA string looks like a phone or tablet."""
    if not user_agent:
        return False
    return bool(_MOBILE_UA_RE.search(user_agent))


class MobileDetectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.is_mobile = is_mobile_user_agent(
            request.headers.get("user-agent", "")
        )
        return await call_next(request)


def register_mobile_detection(app: FastAPI) -> None:
    app.add_middleware(MobileDetectionMiddleware)
