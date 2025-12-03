"""FastAPI application setup and configuration"""

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.routes import guide, auth, vendor, resources
from app.services.guide_service import guide_service

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

        # Resolve company/mode from query or host
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        company_code = request.query_params.get("company_code")
        mode = request.query_params.get("mode")
        company_code, mode = settings.resolve_company_and_mode(
            company_code=company_code,
            mode=mode,
            host=host
        )

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
            except Exception:
                # Ignore failures here; session remains valid
                pass
        except Exception:
            # On failure, clear session and redirect to login with error
            request.session.clear()
            return RedirectResponse(
                url=f"/auth/login?company_code={company_code}&mode={mode}&error=invalid_guide_link",
                status_code=302
            )

        return await call_next(request)

# Add guide hash middleware (inner), then session (outer), then others
app.add_middleware(GuideHashMiddleware)

# Add session middleware for authentication (outermost for session availability)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    https_only=not settings.debug,
    same_site="lax"
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

    # Resolve company/mode from query or host
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code = request.query_params.get("company_code")
    mode = request.query_params.get("mode")
    company_code, mode = settings.resolve_company_and_mode(
        company_code=company_code,
        mode=mode,
        host=host
    )

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
    except Exception:
        # On failure, clear session and redirect to login with error
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
app.include_router(resources.router)  # Generic resources (trips, departures, clients)
app.include_router(guide.router)      # Guide-specific routes (/guide/home)
app.include_router(vendor.router)     # Vendor-specific routes (/vendor/home)


@app.get("/")
async def root(request: Request):
    """
    Redirect root to login or guide home (when guide_hash is provided).
    """
    params = request.query_params
    guide_hash = params.get("guide_hash") or params.get("guideHash")
    company_code = params.get("company_code") or settings.company_code
    mode = params.get("mode") or settings.mode

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
