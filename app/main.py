"""FastAPI application setup and configuration"""

import logging
import sentry_sdk

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.middleware.mobile_detection import MobileDetectionMiddleware
from app.middleware.company_resolution import CompanyResolutionMiddleware
from app.config import settings
from app.routes import guide, auth, vendor, resources, pwa
from app.services.guide_service import guide_service
from app.utils.sentry_utils import capture_exception_with_context

# Templates instance for global error pages — mirrors the per-route loaders
# in app/routes/*.py which all point at the top-level "templates/" dir.
_error_templates = Jinja2Templates(directory="templates")

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Sentry for error tracking (only if enabled)
if settings.sentry_enabled and settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        # Add data like request headers and IP for users
        send_default_pii=True,
        # Set traces_sample_rate to capture performance data
        traces_sample_rate=1.0,
        # Set environment (test/production)
        environment=settings.app_env,
        # Set release version
        release=f"guide-portal@{settings.app_version}",
    )

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

class GuideHashMiddleware(BaseHTTPMiddleware):
    """Bootstrap guide session via guide_hash on all non-vendor routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""

        # Skip vendor routes/home
        if path.startswith("/vendor"):
            return await call_next(request)

        # Session must exist; SessionMiddleware runs outside (added after this)
        if "session" not in request.scope:
            return await call_next(request)

        # Already authenticated? proceed
        if request.session.get("authenticated"):
            return await call_next(request)

        guide_hash = request.query_params.get("guide_hash") or request.query_params.get("guideHash")
        if not guide_hash:
            return await call_next(request)

        # Resolve company/mode from query or host. No default-tenant fallback (#148).
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        company_code = request.query_params.get("company_code")
        mode = request.query_params.get("mode")
        company_code, mode = settings.resolve_company_and_mode(
            company_code=company_code,
            mode=mode,
            host=host
        )
        if not company_code or not mode:
            # Cannot resolve a tenant for this guide_hash. Don't impersonate
            # another tenant — clear the guide_hash and let the request flow
            # to its normal handler (which will redirect to login or render
            # the neutral error page).
            logger.warning(
                "guide_hash provided but tenant could not be resolved (host=%s)", host,
            )
            return await call_next(request)

        try:
            guide_id = await guide_service.get_guide_id_by_hash(
                guide_hash=guide_hash,
                company_code=company_code,
                mode=mode
            )
            request.session.update(
                {
                    "authenticated": True,
                    "user_type": 1,
                    "user_role": "Guide",
                    "guide_id": guide_id,
                    "company_code": company_code,
                    "mode": mode,
                }
            )
            # Best-effort: load basic guide info to populate navbar
            try:
                homepage_data = await guide_service.get_guide_homepage(
                    guide_id=guide_id,
                    company_code=company_code,
                    mode=mode
                )
                if homepage_data.guide_name:
                    request.session["user_name"] = homepage_data.guide_name
                if homepage_data.guide_image:
                    request.session["user_image"] = str(homepage_data.guide_image)
            except Exception as e:
                # Log warning but session remains valid
                logger.warning("Failed to load guide homepage data in middleware: %s", e)
        except Exception as e:
            # On failure, log error, clear session and redirect to login with error
            logger.error("Failed to resolve guide_hash in middleware: %s", e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            request.session.clear()
            return RedirectResponse(
                url=f"/auth/login?company_code={company_code}&mode={mode}&error=invalid_guide_link",
                status_code=302
            )

        return await call_next(request)

# Add guide hash middleware (inner), then session (outer), then others
app.add_middleware(GuideHashMiddleware)

# PWA gating support (#160). Order matters — these are registered AFTER
# GuideHashMiddleware (the most recently added wraps the previous one),
# so at request time their execution order is:
#   SessionMiddleware → MobileDetectionMiddleware → CompanyResolutionMiddleware → GuideHashMiddleware
# Both new middlewares run after SessionMiddleware (so request.scope['session']
# is populated) and before GuideHashMiddleware (so guide-hash redirects can
# rely on request.state.company and request.state.is_mobile).
app.add_middleware(CompanyResolutionMiddleware)
app.add_middleware(MobileDetectionMiddleware)

# Add session middleware for authentication (outermost for session availability)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    https_only=not settings.debug,
    same_site="lax",
    path="/"
)

# Add middleware to enforce HTTPS and set HSTS when appropriate
@app.middleware("http")
async def enforce_https_and_hsts(request, call_next):
    """
    Redirect HTTP to HTTPS (in non-debug), respect proxy headers, and set HSTS.
    """
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"

    is_https = request.scope.get("scheme") == "https"
    if not is_https and not settings.debug:
        https_url = request.url.replace(scheme="https")
        return RedirectResponse(url=str(https_url), status_code=307)

    response = await call_next(request)

    if is_https and not settings.debug:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains; preload"
        )

    return response


# Middleware to auto-bootstrap guide session via guide_hash (bypass login)
@app.middleware("http")
async def guide_hash_auto_login(request: Request, call_next):
    """
    If guide_hash is provided and there is no active session, resolve it to a guide_id
    and bootstrap a guide session. Skips vendor routes.
    """
    path = request.url.path or ""

    # Skip vendor routes/home
    if path.startswith("/vendor"):
        return await call_next(request)

    # If session middleware is not present, skip
    if "session" not in request.scope:
        return await call_next(request)

    # Already authenticated? proceed
    if request.session.get("authenticated"):
        return await call_next(request)

    guide_hash = request.query_params.get("guide_hash") or request.query_params.get("guideHash")
    if not guide_hash:
        return await call_next(request)

    # Resolve company/mode from query or host. No default-tenant fallback (#148).
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code = request.query_params.get("company_code")
    mode = request.query_params.get("mode")
    company_code, mode = settings.resolve_company_and_mode(
        company_code=company_code,
        mode=mode,
        host=host
    )
    if not company_code or not mode:
        logger.warning(
            "auto_login: guide_hash provided but tenant could not be resolved (host=%s)",
            host,
        )
        return await call_next(request)

    try:
        guide_id = await guide_service.get_guide_id_by_hash(
            guide_hash=guide_hash,
            company_code=company_code,
            mode=mode
        )
        request.session.update(
            {
                "authenticated": True,
                "user_type": 1,
                "user_role": "Guide",
                "guide_id": guide_id,
                "company_code": company_code,
                "mode": mode,
            }
        )
    except Exception as e:
        # On failure, log error, clear session and redirect to login with error.
        # company_code and mode are guaranteed non-empty here (guarded above).
        logger.error("Failed to resolve guide_hash in auto_login middleware: %s", e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        request.session.clear()
        return RedirectResponse(
            url=f"/auth/login?company_code={company_code}&mode={mode}&error=invalid_guide_link",
            status_code=302
        )

    return await call_next(request)

# Add CORS middleware if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(auth.router)
app.include_router(pwa.router)        # PWA manifest
app.include_router(resources.router)  # Generic resources (trips, departures, clients)
app.include_router(guide.router)      # Guide-specific routes (/guide/home)
app.include_router(vendor.router)     # Vendor-specific routes (/vendor/home)


def _is_browser_navigation(request: Request) -> bool:
    """Return True when the request looks like a top-level browser navigation,
    so the friendly error page is appropriate. AJAX/API callers still get JSON.
    """
    if request.method != "GET":
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept and "application/json" not in accept


def _error_context(request: Request, sentry_event_id: str | None = None) -> dict:
    """Build the template context for error.html with whatever tenant info is
    actually resolvable for THIS request — never fall back to the default
    tenant env-var (#148). If the tenant cannot be resolved (no query params,
    empty session, no host mapping), the page renders with neutral chrome
    (no logo, no tenant name, no skin) so it cannot impersonate another
    tenant on a failure screen.
    """
    session = getattr(request, "session", {}) or {}
    company_code = (
        request.query_params.get("company_code")
        or request.query_params.get("companyCode")
        or session.get("company_code")
    )
    mode = (
        request.query_params.get("mode")
        or session.get("mode")
    )

    skin_name = session.get("skin_name")
    company_logo = session.get("company_logo")
    company_favicon = session.get("company_favicon")
    theme_color = None
    tenant_resolved = bool(company_code and mode)

    # Best-effort tenant lookup so the error page picks up the right skin
    # when the session has not been populated yet but query params identify
    # the tenant. We never invent a tenant — `company_code` and `mode` must
    # already be non-empty before this lookup runs.
    if tenant_resolved and not skin_name:
        try:
            cfg = settings.get_company_config(company_code, mode)
            skin_name = cfg.skin_name
            company_logo = company_logo or cfg.logo
            company_favicon = company_favicon or cfg.favicon
        except Exception:
            # Never let context resolution itself raise — that would loop the
            # exception handler. The page falls back to neutral chrome.
            tenant_resolved = False
            skin_name = None
            company_logo = None
            company_favicon = None

    return {
        "request": request,
        "skin_name": skin_name,
        "company_logo": company_logo,
        "company_favicon": company_favicon,
        "company_code": company_code if tenant_resolved else None,
        "mode": mode if tenant_resolved else None,
        "theme_color": theme_color,
        "sentry_event_id": sentry_event_id,
        "tenant_resolved": tenant_resolved,
    }


@app.exception_handler(StarletteHTTPException)
async def http_exception_friendly_page(request: Request, exc: StarletteHTTPException):
    """Render the friendly error page for 5xx HTTPException responses on
    browser navigations; capture them in Sentry. 4xx responses (and AJAX
    calls of any status) keep the default FastAPI/Starlette behaviour so
    auth redirects and API contracts do not regress.
    """
    if exc.status_code >= 500 and _is_browser_navigation(request):
        event_id = None
        if settings.sentry_enabled and settings.sentry_dsn:
            try:
                event_id = sentry_sdk.capture_exception(exc)
            except Exception:
                event_id = None
        logger.error(
            "Unhandled HTTPException %s on %s: %s",
            exc.status_code, request.url.path, exc.detail,
        )
        return _error_templates.TemplateResponse(
            "pages/error.html",
            _error_context(request, str(event_id) if event_id else None),
            status_code=exc.status_code,
        )

    return await http_exception_handler(request, exc)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled exceptions. Logs to Sentry and renders the
    friendly error page on browser navigations, JSON otherwise.
    """
    event_id = None
    if settings.sentry_enabled and settings.sentry_dsn:
        try:
            event_id = sentry_sdk.capture_exception(exc)
        except Exception:
            event_id = None
    logger.error(
        "Unhandled exception on %s: %s",
        request.url.path, exc, exc_info=True,
    )

    if _is_browser_navigation(request):
        return _error_templates.TemplateResponse(
            "pages/error.html",
            _error_context(request, str(event_id) if event_id else None),
            status_code=500,
        )

    return JSONResponse(
        {
            "error": "Internal Server Error",
            "sentry_event_id": str(event_id) if event_id else None,
        },
        status_code=500,
    )


@app.get("/")
async def root(request: Request):
    """
    Redirect root to login or guide home (when guide_hash is provided).

    Requires the caller to supply tenant context via query params or via a
    host that maps to a tenant in the domain map (#148). Anonymous hits
    without resolvable tenant context get a neutral 400 page instead of
    silently inheriting the default tenant's branding.
    """
    params = request.query_params
    guide_hash = params.get("guide_hash") or params.get("guideHash")
    company_code, mode = settings.resolve_company_and_mode(
        company_code=params.get("company_code"),
        mode=params.get("mode"),
        host=request.headers.get("host"),
    )

    if not company_code or not mode:
        # No tenant context — render the neutral error page rather than
        # redirecting to a tenant-branded login.
        return _error_templates.TemplateResponse(
            "pages/error.html",
            _error_context(request),
            status_code=400,
        )

    if guide_hash:
        # If guide_hash is present, go straight to guide home (login bypass)
        return RedirectResponse(
            url=f"/guide/home?company_code={company_code}&mode={mode}&guide_hash={guide_hash}",
            status_code=302
        )

    return RedirectResponse(
        url=f"/auth/login?company_code={company_code}&mode={mode}",
        status_code=302
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": settings.app_version}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload
    )
