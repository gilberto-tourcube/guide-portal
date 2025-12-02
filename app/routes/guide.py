"""Guide-related route handlers"""

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.guide_service import guide_service
import httpx

router = APIRouter(prefix="/guide", tags=["guide"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")


@router.get("/home", response_class=HTMLResponse)
async def guide_home(request: Request):
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
    # Get guide info from session
    # TODO: Implement proper session management
    guide_id = request.session.get("guide_id")
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    if not guide_id or not company_code or not mode:
        # Redirect to login if not authenticated
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    try:
        # Get company configuration for logo and branding
        from app.config import settings
        company_config = settings.get_company_config(company_code, mode)

        # Fetch guide homepage data
        homepage_data = await guide_service.get_guide_homepage(
            guide_id=guide_id,
            company_code=company_code,
            mode=mode
        )

        # Save guide image to session for use in header across all pages
        if homepage_data.guide_image:
            request.session["user_image"] = str(homepage_data.guide_image)

        # Render template with data
        return templates.TemplateResponse(
            "pages/guide_home.html",
            {
                "request": request,
                "guide": homepage_data,
                "company_logo": company_config.logo,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "future")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        print(f"API Error fetching guide homepage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load guide information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        print(f"Unexpected error in guide_home: {e}")
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
