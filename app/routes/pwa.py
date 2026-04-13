"""PWA routes — manifest.json per tenant"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.config import settings

router = APIRouter()

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
