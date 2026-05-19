"""Company resolution middleware (#160).

Reads ``company_code``/``mode`` from the session and resolves a
``CompanyConfig`` instance onto ``request.state.company``. Falls back
to ``None`` when the session is anonymous or the tenant cannot be
resolved — never to a default-tenant fallback (#148).
"""

from __future__ import annotations

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


class CompanyResolutionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        company = None
        company_code = None
        mode = None
        try:
            session = request.scope.get("session") or {}
            company_code = session.get("company_code")
            mode = session.get("mode")
            if company_code and mode:
                company = settings.get_company_config(company_code, mode)
        except Exception as exc:  # noqa: BLE001
            if company_code:
                logger.warning(
                    "CompanyResolutionMiddleware: failed to resolve company_code=%r mode=%r: %s",
                    company_code, mode, exc,
                )
            else:
                logger.debug(
                    "CompanyResolutionMiddleware: anonymous session, skipping: %s",
                    exc,
                )
            company = None

        request.state.company = company
        return await call_next(request)
