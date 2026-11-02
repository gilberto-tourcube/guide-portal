"""Tenant redirect middleware (INCA V7 -> V8 cutover).

When the ``TENANT_REDIRECTS`` app setting maps a company code to an https
origin, every request whose tenant resolves to that company code is sent there
with its path and query intact. With the setting empty (the default) this is a
no-op and the app behaves exactly as before.

Tenant resolution reuses ``Settings.resolve_company_and_mode`` so the decision
matches the rest of the app: an explicit ``company_code``/``companyCode`` wins
(any case), then the tenant already in the session (a guide logged in before the
switch was turned on must not keep writing to V7), then the request host map. A
guide_hash link is covered because its tenant is resolved the same way; the
redirect runs before the V7 hash lookup so the hash is never consumed here.

The destination comes only from configuration. Nothing in the request (path,
query, Host or X-Forwarded-Host) can change where the redirect points.
"""

from __future__ import annotations

import logging
from urllib.parse import quote, quote_from_bytes, urlsplit

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings

logger = logging.getLogger(__name__)

# 307: temporary and method-preserving, so a POST keeps its method and body.
# Never 301/308: browsers cache those, and the switch must be reversible.
REDIRECT_STATUS = 307


# Never answered with a redirect: health probes and static assets are not tenant
# traffic, and a V7 page that is still open must keep loading its own assets.
EXEMPT_PREFIXES = ("/health", "/static/")

# Already-encoded URL characters kept as they are when re-encoding raw bytes.
_URL_SAFE = "%/?&=:;@!$'()*+,[]~#-._"


def _request_target(request: Request) -> str:
    """Path and query as received, re-encoded as ASCII, always starting with "/".

    The leading slash matters: the target is appended to a configured origin, so
    a request line like ``GET @evil.example`` must not be able to turn the
    origin into userinfo and change the host.
    """
    raw_path = request.scope.get("raw_path")
    path = raw_path if raw_path else quote(request.url.path).encode("ascii")
    query = request.scope.get("query_string", b"")
    target = quote_from_bytes(path + (b"?" + query if query else b""), safe=_URL_SAFE)
    return target if target.startswith("/") else f"/{target}"


class TenantRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Fast path: switch off means zero behaviour change.
        if not settings.tenant_redirects:
            return await call_next(request)

        redirect_map = settings.tenant_redirect_map()
        if not redirect_map:
            return await call_next(request)

        if request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        try:
            session = request.scope.get("session") or {}
            company_code, _ = settings.resolve_company_and_mode(
                company_code=(
                    settings.company_code_from_query(request.query_params)
                    or session.get("company_code")
                ),
                mode=request.query_params.get("mode"),
                host=host,
            )
        except Exception as exc:  # noqa: BLE001 - never let the switch break a request
            logger.warning("TenantRedirectMiddleware: tenant resolution failed: %s", exc)
            return await call_next(request)

        origin = settings.get_tenant_redirect(company_code)
        if not origin:
            return await call_next(request)

        # Already on the destination host: serve it, never loop.
        if settings._normalize_host(host) == urlsplit(origin).hostname:
            return await call_next(request)

        url = f"{origin}{_request_target(request)}"
        # Belt and braces: the host we send people to is the configured one.
        if urlsplit(url).netloc != urlsplit(origin).netloc:
            logger.warning("TenantRedirectMiddleware: refusing a redirect that left %s", origin)
            return await call_next(request)

        return RedirectResponse(url=url, status_code=REDIRECT_STATUS)
