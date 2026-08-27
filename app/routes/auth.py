"""Authentication routes for login, logout, and password recovery"""

import logging
import re
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request, Form, HTTPException, status, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import settings, InvalidCompanyCodeError
from app.models.schemas import LoginRequest
from app.services.auth_service import auth_service
from app.utils.sentry_utils import capture_exception_with_context
from app.utils.templates import create_templates

router = APIRouter(prefix="/auth", tags=["authentication"])

# Jinja2 templates
templates = create_templates()
logger = logging.getLogger(__name__)

# Characters a new password must not contain. This is not a password-policy
# preference: the V7 change-password API transports the new password as a URL
# path segment. Measured against test-2.tourcube.net, IIS rejects '/' and '\'
# even percent-encoded, rejects a literal '+', and rejects '%' whenever what
# follows looks like another percent-escape (unpredictable either way). These
# four characters have no way to reach the API regardless of encoding, so we
# reject them client- and server-side before attempting the change.
PASSWORD_URL_UNSAFE_CHARS = set("%+/\\")


def _login_url(company_code: str, mode: str, *, error: Optional[str] = None) -> str:
    """Build a login redirect with only the canonical, safe tenant context."""
    params = {"company_code": company_code, "mode": mode}
    if error:
        params["error"] = error
    return f"/auth/login?{urlencode(params)}"


def _neutral_tenant_error(
    request: Request, status_code: int = 400
) -> HTMLResponse:
    """Render the neutral error page (no tenant identity) when a request
    arrives without a resolvable tenant (#148). Used by every auth route
    that previously fell back to ``settings.company_code`` / ``settings.mode``.
    """
    return templates.TemplateResponse(
        "pages/error.html",
        {
            "request": request,
            "skin_name": None,
            "company_logo": None,
            "company_favicon": None,
            "company_code": None,
            "mode": None,
            "theme_color": None,
            "sentry_event_id": None,
            "tenant_resolved": False,
        },
        status_code=status_code,
    )


@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect root to login when tenant can be resolved from query/host; render
    neutral error page otherwise (#148 — no default-tenant fallback).
    """
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code, mode = settings.resolve_company_and_mode(
        company_code=settings.company_code_from_query(request.query_params),
        mode=request.query_params.get("mode"),
        host=host,
    )
    if not company_code or not mode:
        return _neutral_tenant_error(request)
    return RedirectResponse(
        url=_login_url(company_code, mode),
        status_code=302,
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    company_code: Optional[str] = Query(None, description="Company identifier", min_length=1, max_length=50),
    mode: Optional[str] = Query(None, description="Test or Production", pattern="^(Test|Production)$"),
    error: Optional[str] = Query(None),
    TempPassword: Optional[bool] = Query(None, description="Force temp password flow for testing")
):
    """
    Display login form

    Query Parameters:
        company_code: Company identifier (required)
        mode: Test or Production (required)
        error: Error message to display
        TempPassword: Optional override to force change password flow
    """
    # Check if already authenticated
    if request.session.get("authenticated"):
        # Force password change if temp_password is set
        if request.session.get("temp_password"):
            return RedirectResponse(url="/auth/change-password", status_code=302)
        user_type = request.session.get("user_type")
        if user_type == 1:  # Guide
            return RedirectResponse(url="/guide/home", status_code=302)
        elif user_type == 2:  # Vendor
            return RedirectResponse(url="/vendor/home", status_code=302)

    # Resolve company and mode from query or host. No default-tenant fallback (#148).
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code_resolved, mode_resolved = settings.resolve_company_and_mode(
        company_code=settings.company_code_from_query(request.query_params) or company_code,
        mode=mode,
        host=host
    )
    if not company_code_resolved or not mode_resolved:
        return _neutral_tenant_error(request)

    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code_resolved, mode_resolved)
    except (InvalidCompanyCodeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/login.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "company_favicon": company_config.favicon,
            "login_background": company_config.login_background,
            "skin_name": company_config.skin_name,
            "company_code": company_code_resolved,
            "mode": mode_resolved,
            "error": error,
            "temp_password_override": TempPassword or False
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
    form_data: LoginRequest = Depends(_login_form_dependency),
    temp_password_override: Optional[str] = Form(None)
):
    """
    Process login form submission

    Form Parameters:
        username: Portal username
        password: Portal password
        company_code: Company identifier
        mode: Test or Production
        temp_password_override: Optional override to force change password flow
    """
    company_code = settings._normalize_company_code(form_data.company_code)
    try:
        mode = settings._require_mode(form_data.mode)
        if not company_code:
            raise ValueError("company_code is required")
        # Validate the tenant/mode before any API request. This blocks an
        # explicit but unknown tenant and Test-only Production links locally.
        settings.get_company_config(company_code, mode)
    except (InvalidCompanyCodeError, ValueError):
        return _neutral_tenant_error(request)

    try:
        # Call authentication service
        login_response = await auth_service.login(
            username=form_data.username,
            password=form_data.password,
            company_code=company_code,
            mode=mode,
        )

        # Check if login failed
        if login_response.login_failed:
            # Redirect back to login with error
            return RedirectResponse(
                url=_login_url(company_code, mode, error="invalid_credentials"),
                status_code=303
            )

        # Login successful - create session
        request.session["authenticated"] = True
        request.session["user_type"] = login_response.type
        request.session["company_code"] = company_code
        request.session["mode"] = mode

        # Check if user must change temporary password
        must_change_password = bool(login_response.temp_password) or temp_password_override == "True"
        if must_change_password:
            request.session["temp_password"] = True

        # Client ID of the person behind the account, for both guides and
        # vendors. This is what the password endpoint is keyed on.
        request.session["client_id"] = login_response.guide_client_id

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

            # Redirect to change password if temporary, otherwise guide homepage
            if must_change_password:
                return RedirectResponse(url="/auth/change-password", status_code=303)
            return RedirectResponse(url="/guide/home", status_code=303)

        elif login_response.type == 2:  # Vendor
            # Store vendor-specific data
            request.session["vendor_id"] = login_response.guide_vendor_id

            # Fetch vendor info and store in session
            try:
                vendor_info = await auth_service.get_vendor_info(
                    vendor_id=login_response.guide_vendor_id,
                    company_code=company_code,
                    mode=mode
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

            # Redirect to change password if temporary, otherwise vendor homepage
            if must_change_password:
                return RedirectResponse(url="/auth/change-password", status_code=303)
            return RedirectResponse(url="/vendor/home", status_code=303)

        else:
            # Unknown user type
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unknown user type returned from API"
            )

    except httpx.HTTPError as e:
        # API call failed
        logger.error("Login API error for user %s: %s", form_data.username, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url=_login_url(company_code, mode, error="api_error"),
            status_code=303
        )
    except Exception as e:
        # Unexpected error
        logger.error("Login unexpected error for user %s: %s", form_data.username, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url=_login_url(company_code, mode, error="unexpected_error"),
            status_code=303
        )


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    error: Optional[str] = Query(None),
    success: Optional[bool] = Query(None)
):
    """Display change password form (required when TempPassword=1)"""
    if not request.session.get("authenticated"):
        # Unauthenticated hit on /change-password. Don't invent a tenant for
        # the redirect URL — render the neutral error page instead (#148).
        company_code = request.session.get("company_code")
        mode = request.session.get("mode")
        if not company_code or not mode:
            return _neutral_tenant_error(request, status_code=401)
        return RedirectResponse(
            url=_login_url(company_code, mode, error="unauthorized"),
            status_code=302
        )

    company_code = request.session.get("company_code")
    mode = request.session.get("mode")
    user_type = request.session.get("user_type")

    if not company_code or not mode:
        # Authenticated session missing tenant context — render neutral error.
        return _neutral_tenant_error(request, status_code=500)

    try:
        company_config = settings.get_company_config(company_code, mode)
    except InvalidCompanyCodeError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return templates.TemplateResponse(
        "pages/change_password.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "company_favicon": company_config.favicon,
            "login_background": company_config.login_background,
            "skin_name": company_config.skin_name,
            "company_code": company_code,
            "mode": mode,
            "user_type": user_type,
            "error": error,
            "success": success
        }
    )


@router.post("/change-password")
async def change_password_submit(
    request: Request,
    new_password: str = Form(..., min_length=1),
    confirm_password: str = Form(..., min_length=1),
    company_code: str = Form(...),
    mode: str = Form(...)
):
    """Process change password form submission"""
    if not request.session.get("authenticated"):
        return RedirectResponse(
            url=f"/auth/login?company_code={company_code}&mode={mode}&error=unauthorized",
            status_code=303
        )

    # Validate passwords match
    if new_password != confirm_password:
        return RedirectResponse(
            url="/auth/change-password?error=passwords_mismatch",
            status_code=303
        )

    # Validate minimum length
    if len(new_password) < 6:
        return RedirectResponse(
            url="/auth/change-password?error=password_too_short",
            status_code=303
        )

    # Validate against characters the change-password API cannot transport
    # (see PASSWORD_URL_UNSAFE_CHARS above).
    if any(char in PASSWORD_URL_UNSAFE_CHARS for char in new_password):
        return RedirectResponse(
            url="/auth/change-password?error=password_invalid_chars",
            status_code=303
        )

    user_type = request.session.get("user_type")

    home_url = "/vendor/home" if user_type == 2 else "/guide/home"

    # Both account types use the same endpoint, keyed on the client ID of the
    # person behind the account (the vendor-specific endpoint is retired).
    client_id = request.session.get("client_id")
    if not client_id:
        # The login response carried no client ID for this account, so there is
        # nothing to update. Fail loudly instead of reporting a false success.
        logger.error("Change password blocked: no client_id in session for user type %s", user_type)
        return RedirectResponse(
            url="/auth/change-password?error=api_error",
            status_code=303
        )

    try:
        await auth_service.change_password(
            client_id=client_id,
            new_password=new_password,
            company_code=company_code,
            mode=mode
        )
        request.session.pop("temp_password", None)
        return RedirectResponse(url=home_url, status_code=303)

    except httpx.HTTPError as e:
        logger.error("Change password API error for user type %s: %s", user_type, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url="/auth/change-password?error=api_error",
            status_code=303
        )
    except Exception as e:
        logger.error("Change password unexpected error for user type %s: %s", user_type, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url="/auth/change-password?error=unexpected_error",
            status_code=303
        )


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login"""
    # Get company_code and mode before clearing session. No default-tenant
    # fallback (#148) — if the session lacks tenant context, render the
    # neutral logout/error page instead of inventing a tenant.
    company_code = request.session.get("company_code")
    mode = request.session.get("mode")

    request.session.clear()

    if not company_code or not mode:
        return _neutral_tenant_error(request, status_code=200)

    # Redirect to login with parameters
    return RedirectResponse(
        url=_login_url(company_code, mode),
        status_code=302
    )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    company_code: Optional[str] = Query(None, description="Company identifier"),
    mode: Optional[str] = Query(None, description="Test or Production"),
    success: Optional[str] = Query(None)
):
    """Display forgot password form"""
    # Resolve company and mode from query or host. No default-tenant fallback (#148).
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code_resolved, mode_resolved = settings.resolve_company_and_mode(
        company_code=settings.company_code_from_query(request.query_params) or company_code,
        mode=mode,
        host=host
    )
    if not company_code_resolved or not mode_resolved:
        return _neutral_tenant_error(request)

    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code_resolved, mode_resolved)
    except (InvalidCompanyCodeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/forgot_password.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "company_favicon": company_config.favicon,
            "login_background": company_config.login_background,
            "skin_name": company_config.skin_name,
            "company_code": company_code_resolved,
            "mode": mode_resolved,
            "success": success
        }
    )


@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    first_name: str = Form(...),
    company_code: str = Form(...),
    mode: str = Form(...)
):
    """Process forgot password form: send a temporary password email.

    The TourCube API generates the temporary password and emails it to the
    user. We collect email + first name directly (the legacy username->email
    DB lookup is not available to the modern portal).
    """
    try:
        # Call auth service to send the temporary password email
        await auth_service.send_temp_password(
            email=email,
            first_name=first_name,
            company_code=company_code,
            mode=mode
        )

        # Redirect to success page
        return RedirectResponse(
            url=f"/auth/forgot-password?company_code={company_code}&mode={mode}&success=true",
            status_code=303
        )

    except httpx.HTTPError as e:
        logger.error("Temp password API error for email %s: %s", email, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url=f"/auth/forgot-password?company_code={company_code}&mode={mode}&success=false",
            status_code=303
        )


@router.get("/forgot-username", response_class=HTMLResponse)
async def forgot_username_page(
    request: Request,
    company_code: Optional[str] = Query(None, description="Company identifier"),
    mode: Optional[str] = Query(None, description="Test or Production"),
    success: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
):
    """Display forgot username form"""
    # Resolve company and mode from query or host. No default-tenant fallback (#148).
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    company_code_resolved, mode_resolved = settings.resolve_company_and_mode(
        company_code=settings.company_code_from_query(request.query_params) or company_code,
        mode=mode,
        host=host
    )
    if not company_code_resolved or not mode_resolved:
        return _neutral_tenant_error(request)

    # Get company configuration with mode
    try:
        company_config = settings.get_company_config(company_code_resolved, mode_resolved)
    except (InvalidCompanyCodeError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    return templates.TemplateResponse(
        "pages/forgot_username.html",
        {
            "request": request,
            "company_logo": company_config.logo,
            "company_favicon": company_config.favicon,
            "login_background": company_config.login_background,
            "skin_name": company_config.skin_name,
            "company_code": company_code_resolved,
            "mode": mode_resolved,
            "success": success,
            "error": error
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
    # Validate email format before hitting the API. type="email" alone accepts
    # addresses with no domain dot (e.g. name@test), so enforce a stricter check
    # server-side too (defense in depth) and show a clear inline message.
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", (email or "").strip()):
        return RedirectResponse(
            url=f"/auth/forgot-username?company_code={company_code}&mode={mode}&error=invalid_email",
            status_code=303
        )

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
        logger.error("Forgot username API error for email %s: %s", email, e)
        capture_exception_with_context(e, mode=mode, company_code=company_code)
        return RedirectResponse(
            url=f"/auth/forgot-username?company_code={company_code}&mode={mode}&success=false",
            status_code=303
        )
