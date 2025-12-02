"""FastAPI application setup and configuration"""

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
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
    max_age=settings.session_max_age
)

# Add middleware to handle proxy headers (for HTTPS detection behind Azure)
@app.middleware("http")
async def force_https_scheme(request, call_next):
    """Force HTTPS scheme for URL generation when behind a reverse proxy"""
    # Azure App Service sets X-Forwarded-Proto header
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# Add CORS middleware if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure properly for production
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
