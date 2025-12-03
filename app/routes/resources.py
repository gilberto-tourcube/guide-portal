"""Generic resource route handlers (trips, departures, clients)

These routes are accessible by both guides and vendors.
Access control is handled at the service layer.
"""

import logging

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.services.guide_service import guide_service
import httpx
from app.config import settings

# Generic resources router (no prefix, resources at root level)
router = APIRouter(tags=["resources"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/departure/{trip_departure_id}", response_class=HTMLResponse)
async def departure_details(request: Request, trip_departure_id: int):
    """
    Departure details page (accessible by both guides and vendors)

    This endpoint displays detailed information about a specific trip departure,
    including:
    - Trip information (name, dates, banner image)
    - Trip leaders/guides
    - Area Manager (Trip Developer)
    - Passengers list (Clients tab)
    - Documents (Trip Documents and Departure Documents)
    - Trip Leader Forms to complete

    Args:
        request: FastAPI request object
        trip_departure_id: Unique trip departure identifier

    Returns:
        Rendered HTML page with trip departure details

    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 500: If API call fails
    """
    # Get user info from session (works for both guides and vendors)
    user_id = request.session.get("guide_id") or request.session.get("vendor_id")
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    if not user_id or not company_code or not mode:
        # Redirect to login with error
        company_code = company_code or settings.company_code
        mode = mode or settings.mode
        return RedirectResponse(
            url=f"/auth/login?company_code={company_code}&mode={mode}&error=unauthorized",
            status_code=302
        )

    try:
        # Get company configuration for logo and branding
        company_config = settings.get_company_config(company_code, mode)

        # Fetch trip departure data (API accepts both guide_id and vendor_id in same parameter)
        departure_data = await guide_service.get_trip_departure(
            trip_departure_id=trip_departure_id,
            guide_id=user_id,
            company_code=company_code,
            mode=mode
        )

        # Render template with data
        return templates.TemplateResponse(
            "pages/trip_departure.html",
            {
                "request": request,
                "departure": departure_data,
                "company_logo": company_config.logo,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "clients")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        logger.error("API Error fetching trip departure: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load trip information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        logger.exception("Unexpected error in trip_details: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


@router.get("/trip/{trip_id}", response_class=HTMLResponse)
async def trip_page(request: Request, trip_id: int):
    """
    Trip page showing all departures for a specific trip (accessible by both guides and vendors)

    This endpoint displays:
    - Trip information (name, banner image)
    - Future Departures tab (dates, trip leaders, clients count)
    - Past Departures tab (dates, trip leaders, clients count)
    - Trip Documents tab (documents with links)

    Args:
        request: FastAPI request object
        trip_id: Unique trip identifier

    Returns:
        Rendered HTML page with trip details

    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 500: If API call fails
    """
    # Get user info from session (works for both guides and vendors)
    user_id = request.session.get("guide_id") or request.session.get("vendor_id")
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    if not user_id or not company_code or not mode:
        company_code = company_code or settings.company_code
        mode = mode or settings.mode
        return RedirectResponse(
            url=f"/auth/login?company_code={company_code}&mode={mode}&error=unauthorized",
            status_code=302
        )

    try:
        # Get company configuration for logo and branding
        company_config = settings.get_company_config(company_code, mode)

        # Fetch trip page data (API accepts both guide_id and vendor_id in same parameter)
        trip_data = await guide_service.get_trip_page(
            trip_id=trip_id,
            guide_id=user_id,
            company_code=company_code,
            mode=mode
        )

        # Render template with data
        return templates.TemplateResponse(
            "pages/trip.html",
            {
                "request": request,
                "trip": trip_data,
                "company_logo": company_config.logo,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "active_tab": request.query_params.get("tab", "future")
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        logger.error("API Error fetching trip page: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load trip information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        logger.exception("Unexpected error in trip_page: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


@router.get("/client/{client_id}", response_class=HTMLResponse)
async def client_page(
    request: Request,
    client_id: int,
    from_page: str = None,
    trip_id: int = None,
    departure_id: int = None,
    trip_name: str = None,
    trip_dates: str = None
):
    """
    Client details page (accessible by both guides and vendors)

    This endpoint displays detailed information about a client/passenger:
    - Basic info (name, age, gender, hometown, contact)
    - Medical allergies
    - Fitness level
    - Dietary restrictions and preferences
    - Trip history (past trips, past trips with leader, future trips)
    - Notes on client

    Args:
        request: FastAPI request object
        client_id: Unique client identifier
        from_page: Source page (e.g., "trip_departure", "home")
        trip_id: Trip ID if coming from trip page
        departure_id: Departure ID if coming from departure page
        trip_name: Trip name for breadcrumb
        trip_dates: Trip dates for breadcrumb

    Returns:
        Rendered HTML page with client details

    Raises:
        HTTPException 401: If user is not authenticated
        HTTPException 500: If API call fails
    """
    # Get user info from session (works for both guides and vendors)
    user_id = request.session.get("guide_id") or request.session.get("vendor_id")
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    if not user_id or not company_code or not mode:
        company_code = company_code or settings.company_code
        mode = mode or settings.mode
        return RedirectResponse(
            url=f"/auth/login?company_code={company_code}&mode={mode}&error=unauthorized",
            status_code=302
        )

    try:
        # Get company configuration for logo and branding
        company_config = settings.get_company_config(company_code, mode)

        # Fetch client details
        client_data = await guide_service.get_client_details(
            client_id=client_id,
            guide_id=user_id,
            company_code=company_code,
            mode=mode
        )

        # Render template with data
        return templates.TemplateResponse(
            "pages/client.html",
            {
                "request": request,
                "client": client_data,
                "company_logo": company_config.logo,
                "company_code": company_code,
                "skin_name": company_config.skin_name,
                "from_page": from_page,
                "trip_id": trip_id,
                "departure_id": departure_id,
                "trip_name": trip_name,
                "trip_dates": trip_dates
            }
        )

    except httpx.HTTPError as e:
        # Log error and show user-friendly message
        logger.error("API Error fetching client details: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load client information. Please try again later."
        )
    except Exception as e:
        # Catch any other errors
        logger.exception("Unexpected error in client_page: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )
