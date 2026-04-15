"""PWA routes — manifest.json, service worker (root scope), and document proxy."""

from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from app.config import settings

router = APIRouter()

SERVICE_WORKER_PATH = Path("static/service-worker.js")

# Hosts allowed when proxying document downloads (presigned URLs).
# Restricted to S3-compatible providers used for Tourcube documents.
ALLOWED_DOC_HOSTS = ("amazonaws.com", "wasabisys.com")

# Skin name → primary color for manifest theme_color
SKIN_COLORS = {
    "theme-wt-blue": "#0F4374",
    "theme-wt-brown": "#6B4F3A",
    "theme-bluelite": "#6576ff",
    "theme-blue": "#2c3782",
    "theme-darkblue": "#1c2f50",
    "theme-egyptian": "#6576ff",
    "theme-green": "#1ee0ac",
    "theme-purple": "#8091ff",
    "theme-red": "#e85347",
}


@router.get("/manifest.json")
async def manifest(request: Request):
    """Serve a tenant-specific PWA manifest"""
    company_code = (
        request.query_params.get("companyCode")
        or request.session.get("company_code")
        or settings.company_code
    )
    mode = (
        request.query_params.get("mode")
        or request.session.get("mode")
        or settings.mode
    )

    try:
        config = settings.get_company_config(company_code, mode)
    except Exception:
        config = None

    app_name = "Tourcube Guide Portal"
    theme_color = "#0F4374"
    icons = []

    if config:
        app_name = f"{config.company_id} Guide Portal"
        theme_color = SKIN_COLORS.get(config.skin_name, "#0F4374")

        if config.favicon:
            icon_path = f"/static/images/{config.favicon}"
            icons = [
                {"src": icon_path, "sizes": "192x192", "type": "image/png"},
                {"src": icon_path, "sizes": "512x512", "type": "image/png"},
            ]

    manifest_data = {
        "name": app_name,
        "short_name": app_name,
        "start_url": f"/?company_code={company_code}&mode={mode}",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": theme_color,
        "icons": icons,
    }

    return JSONResponse(
        content=manifest_data,
        media_type="application/manifest+json",
    )


@router.get("/service-worker.js", include_in_schema=False)
async def service_worker():
    """Serve the service worker at root scope.

    The Service-Worker-Allowed header is required for the SW to control
    URLs outside its directory (the file lives under /static/).
    """
    return FileResponse(
        SERVICE_WORKER_PATH,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
        },
    )


@router.get("/document-proxy", include_in_schema=False)
async def document_proxy(url: str = Query(...)):
    """Proxy presigned document URLs as same-origin so the SW can cache them.

    Presigned S3/Wasabi URLs do not return CORS headers, so the browser
    blocks the response body when fetched directly from the page. This
    proxy serves the same bytes from our origin.
    """
    target = unquote(url)
    parsed = urlparse(target)

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    host = parsed.hostname or ""
    if not any(host.endswith(allowed) for allowed in ALLOWED_DOC_HOSTS):
        raise HTTPException(status_code=403, detail="Host not allowed")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            upstream = await client.get(target)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Upstream fetch failed: {e}")

    if upstream.status_code != 200:
        raise HTTPException(
            status_code=upstream.status_code,
            detail="Upstream returned non-200",
        )

    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Cache-Control": "private, max-age=3600"},
    )
