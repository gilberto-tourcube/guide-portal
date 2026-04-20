"""Vendor-related route handlers"""

import logging
from typing import Optional
import httpx
from fastapi import APIRouter, Query, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.services.vendor_service import vendor_service
from app.utils.sentry_utils import capture_exception_with_context

router = APIRouter(prefix="/vendor", tags=["vendor"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/home", response_class=HTMLResponse)
async def vendor_home(
    request: Request,
    vendor_hash: Optional[str] = Query(
        None,
        alias="vendor_hash",
        description="Vendor hash for back office deep-link access"
    ),
    vendor_hash_alt: Optional[str] = Query(
        None,
        alias="vendorHash",
        description="Vendor hash (camelCase compatibility)"
    ),
    company_code: Optional[str] = Query(None, description="Company identifier override"),
    mode: Optional[str] = Query(None, description="Test or Production")
):
    """
    Vendor homepage displaying trips and forms

    This endpoint:
    1. When called with a vendorHash query parameter (from back office),
       resolves the hash to a vendor_id and bootstraps a session.
    2. Otherwise checks for authenticated vendor in session.
    3. Fetches vendor's trips and forms from API.
    4. Renders the homepage with all data.

    Returns:
        Rendered HTML page with vendor's homepage data

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

    vendor_id = request.session.get("vendor_id")

    # If not authenticated and vendor_hash is provided, resolve and bootstrap session
    resolved_hash = vendor_hash or vendor_hash_alt

    if not vendor_id and resolved_hash:
        try:
            vendor_id = await vendor_service.get_vendor_id_by_hash(
                vendor_hash=resolved_hash,
                company_code=resolved_company_code,
                mode=resolved_mode
            )
            request.session.update(
                {
                    "authenticated": True,
                    "user_type": 2,
                    "user_role": "Vendor",
                    "vendor_id": vendor_id,
                    "company_code": resolved_company_code,
                    "mode": resolved_mode,
                }
            )
        except Exception as exc:
            logger.error("Failed to resolve vendorHash: %s", exc)
            capture_exception_with_context(exc, mode=resolved_mode, company_code=resolved_company_code)
            request.session.clear()
            return RedirectResponse(
                url=(
                    f"/auth/login?company_code={resolved_company_code}"
                    f"&mode={resolved_mode}&error=invalid_vendor_link"
                ),
                status_code=302
            )

    # Force password change if temp_password is set
    if request.session.get("temp_password"):
        return RedirectResponse(url="/auth/change-password", status_code=302)

    # Use the resolved company_code and mode for the rest of the flow
    company_code = resolved_company_code
    mode = resolved_mode

    if not vendor_id or not company_code or not mode:
        # Redirect to login if not authenticated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    try:
        # Get company configuration for logo and branding
        company_config = settings.get_company_config(company_code, mode)

        # Fetch vendor homepage data
        homepage_data = await vendor_service.get_vendor_homepage(
            vendor_id=vendor_id,
            company_code=company_code,
            mode=mode
        )

        # Populate navbar user_name with the vendor name returned by the API.
        # Without this the header falls back to the literal string "User"
        # (happens after hash bootstrap since login.py is skipped).
        if homepage_data.vendor_name:
            request.session["user_name"] = homepage_data.vendor_name

        # Render template with data
        return templates.TemplateResponse(
            "pages/vendor_home.html",
            {
                "request": request,
                "vendor": homepage_data,
                "company_logo": company_config.logo,
                "company_favicon": company_config.favicon,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "future")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        logger.error("API Error fetching vendor homepage for vendor %s: %s", vendor_id, e)
        capture_exception_with_context(e, request=request)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load vendor information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        logger.error("Unexpected error in vendor_home for vendor %s: %s", vendor_id, e)
        capture_exception_with_context(e, request=request)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
