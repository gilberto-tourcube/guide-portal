"""Guide-related route handlers"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Query, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.guide_service import guide_service
from app.utils.sentry_utils import capture_exception_with_context

router = APIRouter(prefix="/guide", tags=["guide"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/home", response_class=HTMLResponse)
async def guide_home(
    request: Request,
    guide_hash: Optional[str] = Query(
        None,
        alias="guide_hash",
        description="Guide hash for support access"
    ),
    guide_hash_alt: Optional[str] = Query(
        None,
        alias="guideHash",
        description="Guide hash for support access (camelCase compatibility)"
    ),
    company_code: Optional[str] = Query(None, description="Company identifier override"),
    mode: Optional[str] = Query(None, description="Test or Production")
):
    """
    Guide homepage displaying trips and forms

    This endpoint:
    1. Checks for authenticated guide in session
    2. Fetches guide's trips and forms from API
    3. Renders the homepage with all data

    Returns:
        Rendered HTML page with guide's homepage data

    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 500: If API call fails
    """
    # Resolve company/mode preference
    resolved_company_code = (
        company_code
        or request.session.get("company_code")
        or settings.company_code
    )
    resolved_mode = (
        mode
        or request.session.get("mode")
        or settings.mode
    )

    guide_id = request.session.get("guide_id")

    # If not authenticated and guide_hash is provided, resolve and bootstrap session
    resolved_hash = guide_hash or guide_hash_alt

    if not guide_id and resolved_hash:
        try:
            guide_id = await guide_service.get_guide_id_by_hash(
                guide_hash=resolved_hash,
                company_code=resolved_company_code,
                mode=resolved_mode
            )
            request.session.update(
                {
                    "authenticated": True,
                    "user_type": 1,
                    "user_role": "Guide",
                    "guide_id": guide_id,
                    "company_code": resolved_company_code,
                    "mode": resolved_mode,
                }
            )
        except Exception as exc:
            logger.error("Failed to resolve guideHash: %s", exc)
            capture_exception_with_context(exc, mode=resolved_mode, company_code=resolved_company_code)
            request.session.clear()
            return RedirectResponse(
                url=(
                    f"/auth/login?company_code={resolved_company_code}"
                    f"&mode={resolved_mode}&error=invalid_guide_link"
                ),
                status_code=302
            )

    if not guide_id or not resolved_company_code or not resolved_mode:
        request.session.clear()
        return RedirectResponse(
            url=(
                f"/auth/login?company_code={resolved_company_code}"
                f"&mode={resolved_mode}&error=unauthorized"
            ),
            status_code=302
        )

    try:
        # Get company configuration for logo and branding
        from app.config import settings
        company_config = settings.get_company_config(resolved_company_code, resolved_mode)

        # Fetch guide homepage data
        homepage_data = await guide_service.get_guide_homepage(
            guide_id=guide_id,
            company_code=resolved_company_code,
            mode=resolved_mode
        )

        # Save guide image to session for use in header across all pages
        if homepage_data.guide_image:
            request.session["user_image"] = str(homepage_data.guide_image)
        if homepage_data.guide_name:
            request.session["user_name"] = homepage_data.guide_name

        # Render template with data
        return templates.TemplateResponse(
            "pages/guide_home.html",
            {
                "request": request,
                "guide": homepage_data,
                "company_logo": company_config.logo,
                "company_code": resolved_company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "future")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        logger.error("API Error fetching guide homepage for guide %s: %s", guide_id, e)
        capture_exception_with_context(e, request=request)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load guide information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        logger.error("Unexpected error in guide_home for guide %s: %s", guide_id, e)
        capture_exception_with_context(e, request=request)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


# Note: /departure, /trip, and /client routes have been moved to resources.py
# These routes are now accessible at:
# - /departure/{id}  (not /guide/departure/{id})
# - /trip/{id}       (not /guide/trip/{id})
# - /client/{id}     (not /guide/client/{id})
# This reflects that they are generic resources accessible by both guides and vendors.
