"""FastAPI application setup and configuration"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.config import settings
from app.routes import guide, auth, vendor, resources

# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug
)

# Add session middleware for authentication
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
async def root():
    """Redirect root to login page with default parameters"""
    return RedirectResponse(
        url=f"/auth/login?company_code={settings.company_code}&mode={settings.mode}",
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
