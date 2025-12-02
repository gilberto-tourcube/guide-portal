"""Vendor-related route handlers"""

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.vendor_service import vendor_service
import httpx

router = APIRouter(prefix="/vendor", tags=["vendor"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")


@router.get("/home", response_class=HTMLResponse)
async def vendor_home(request: Request):
    """
    Vendor homepage displaying trips and forms

    This endpoint:
    1. Checks for authenticated vendor in session
    2. Fetches vendor's trips and forms from API
    3. Renders the homepage with all data

    Returns:
        Rendered HTML page with vendor's homepage data

    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 500: If API call fails
    """
    # Get vendor info from session
    vendor_id = request.session.get("vendor_id")
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    if not vendor_id or not company_code or not mode:
        # Redirect to login if not authenticated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    try:
        # Get company configuration for logo and branding
        from app.config import settings
        company_config = settings.get_company_config(company_code, mode)

        # Fetch vendor homepage data
        homepage_data = await vendor_service.get_vendor_homepage(
            vendor_id=vendor_id,
            company_code=company_code,
            mode=mode
        )

        # Render template with data
        return templates.TemplateResponse(
            "pages/vendor_home.html",
            {
                "request": request,
                "vendor": homepage_data,
                "company_logo": company_config.logo,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "future")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        print(f"API Error fetching vendor homepage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load vendor information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        print(f"Unexpected error in vendor_home: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
