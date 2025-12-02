"""Authentication routes for login, logout, and password recovery"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Request, Form, HTTPException, status, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import settings, InvalidCompanyCodeError
from app.models.schemas import LoginRequest
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])

# Jinja2 templates
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect root to login page with default parameters"""
    return RedirectResponse(
        url=f"/auth/login?company_code={settings.company_code}&mode={settings.mode}",
        status_code=302
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    company_code: str = Query(..., description="Company identifier", min_length=1, max_length=50),
    mode: str = Query(..., description="Test or Production", pattern="^(Test|Production)$"),
    error: Optional[str] = Query(None)
):
    """
    Display login form

    Query Parameters:
        company_code: Company identifier (required)
        mode: Test or Production (required)
        error: Error message to display
    """
    # Check if already authenticated
    if request.session.get("authenticated"):
        user_type = request.session.get("user_type")
        if user_type == 1:  # Guide
            return RedirectResponse(url="/guide/home", status_code=302)
        elif user_type == 2:  # Vendor
            return RedirectResponse(url="/vendor/home", status_code=302)

    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code, mode)
    except InvalidCompanyCodeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "skin_name": company_config.skin_name,
            "company_code": company_code,
            "mode": mode,
            "error": error
        }
    )


def _login_form_dependency(
    username: str = Form(..., min_length=1, max_length=100),
    password: str = Form(..., min_length=1, max_length=100),
    company_code: str = Form(..., min_length=1, max_length=50),
    mode: str = Form(..., pattern="^(Test|Production)$")
) -> LoginRequest:
    return LoginRequest(
        username=username,
        password=password,
        company_code=company_code,
        mode=mode
    )


@router.post("/login")
async def login_submit(
    request: Request,
    form_data: LoginRequest = Depends(_login_form_dependency)
):
    """
    Process login form submission

    Form Parameters:
        username: Portal username
        password: Portal password
        company_code: Company identifier
        mode: Test or Production
    """
    try:
        # Call authentication service
        login_response = await auth_service.login(
            username=form_data.username,
            password=form_data.password,
            company_code=form_data.company_code,
            mode=form_data.mode
        )

        # Check if login failed
        if login_response.login_failed:
            # Redirect back to login with error
            return RedirectResponse(
                url=f"/auth/login?company_code={form_data.company_code}&mode={form_data.mode}&error=invalid_credentials",
                status_code=303
            )

        # Login successful - create session
        request.session["authenticated"] = True
        request.session["user_type"] = login_response.type
        request.session["company_code"] = form_data.company_code
        request.session["mode"] = form_data.mode

        # Store user-specific data based on type
        if login_response.type == 1:  # Guide
            # Store guide-specific data
            request.session["guide_id"] = login_response.guide_client_id
            request.session["guide_first_name"] = login_response.guide_first_name
            request.session["guide_last_name"] = login_response.guide_last_name
            request.session["guide_email"] = login_response.guide_email

            # Store normalized user data
            request.session["user_name"] = f"{login_response.guide_first_name} {login_response.guide_last_name}".strip()
            request.session["user_email"] = login_response.guide_email
            request.session["user_image"] = None  # Will be set after loading homepage
            request.session["user_role"] = "Guide"

            # Redirect to guide homepage
            return RedirectResponse(url="/guide/home", status_code=303)

        elif login_response.type == 2:  # Vendor
            # Store vendor-specific data
            request.session["vendor_id"] = login_response.guide_vendor_id

            # Fetch vendor info and store in session
            try:
                vendor_info = await auth_service.get_vendor_info(
                    vendor_id=login_response.guide_vendor_id,
                    company_code=form_data.company_code,
                    mode=form_data.mode
                )
                vendor_name = vendor_info["vendor_name"]
            except Exception as e:
                # If fetching vendor info fails, use a default name
                logger.warning("Could not fetch vendor info: %s", e)
                vendor_name = "Vendor"

            # Store normalized user data
            request.session["user_name"] = vendor_name
            request.session["user_email"] = None  # Vendors don't have email in current API
            request.session["user_image"] = None  # Vendors don't have images
            request.session["user_role"] = "Vendor"

            # Redirect to vendor homepage
            return RedirectResponse(url="/vendor/home", status_code=303)

        else:
            # Unknown user type
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unknown user type returned from API"
            )

    except httpx.HTTPError as e:
        # API call failed
        print(f"Login API error: {e}")
        return RedirectResponse(
            url=f"/auth/login?company_code={form_data.company_code}&mode={form_data.mode}&error=api_error",
            status_code=303
        )
    except Exception as e:
        # Unexpected error
        logger.error("Login error: %s", e)
        return RedirectResponse(
            url=f"/auth/login?company_code={form_data.company_code}&mode={form_data.mode}&error=unexpected_error",
            status_code=303
        )


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login"""
    # Get company_code and mode before clearing session
    company_code = request.session.get("company_code", settings.company_code)
    mode = request.session.get("mode", settings.mode)
    
    # Clear session
    request.session.clear()
    
    # Redirect to login with parameters
    return RedirectResponse(
        url=f"/auth/login?company_code={company_code}&mode={mode}",
        status_code=302
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    company_code: str = Query(..., description="Company identifier"),
    mode: str = Query(..., description="Test or Production")
):
    """Display forgot password form"""
    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code, mode)
    except InvalidCompanyCodeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/forgot_password.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "skin_name": company_config.skin_name,
            "company_code": company_code,
            "mode": mode
        }
    )


@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    username: str = Form(...),
    company_code: str = Form(...),
    mode: str = Form(...)
):
    """
    Process forgot password form

    Note: This is currently not implemented as it requires
    user lookup to get email and first_name before calling API
    """
    # TODO: Implement user lookup and temp password email
    return templates.TemplateResponse(
        "pages/forgot_password.html",
        {
            "request": request,
            "company_code": company_code,
            "mode": mode,
            "message": "Forgot password feature is not yet implemented. Please contact support."
        }
    )


@router.get("/forgot-username", response_class=HTMLResponse)
async def forgot_username_page(
    request: Request,
    company_code: str = Query(..., description="Company identifier"),
    mode: str = Query(..., description="Test or Production"),
    success: Optional[bool] = Query(None)
):
    """Display forgot username form"""
    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code, mode)
    except InvalidCompanyCodeError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/forgot_username.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "skin_name": company_config.skin_name,
            "company_code": company_code,
            "mode": mode,
            "success": success
        }
    )


@router.post("/forgot-username")
async def forgot_username_submit(
    request: Request,
    email: str = Form(...),
    company_code: str = Form(...),
    mode: str = Form(...)
):
    """Process forgot username form"""
    try:
        # Call auth service to send username reminder
        await auth_service.send_forgot_username(
            email=email,
            company_code=company_code,
            mode=mode
        )

        # Redirect to success page
        return RedirectResponse(
            url=f"/auth/forgot-username?company_code={company_code}&mode={mode}&success=true",
            status_code=303
        )

    except httpx.HTTPError as e:
        print(f"Forgot username API error: {e}")
        return RedirectResponse(
            url=f"/auth/forgot-username?company_code={company_code}&mode={mode}&success=false",
            status_code=303
        )
