"""Company resolution middleware (#160).

Reads ``company_code``/``mode`` from the session and resolves a
``CompanyConfig`` instance onto ``request.state.company``. Falls back
to ``None`` when the session is anonymous or the tenant cannot be
resolved — never to a default-tenant fallback (#148).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)


class CompanyResolutionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        company = None
        try:
            session = request.scope.get("session") or {}
            company_code = session.get("company_code")
            mode = session.get("mode")
            if company_code and mode:
                company = settings.get_company_config(company_code, mode)
        except Exception as exc:  # noqa: BLE001
            logger.debug("CompanyResolutionMiddleware: %s", exc)
            company = None

        request.state.company = company
        return await call_next(request)


def register_company_resolution(app: FastAPI) -> None:
    app.add_middleware(CompanyResolutionMiddleware)
