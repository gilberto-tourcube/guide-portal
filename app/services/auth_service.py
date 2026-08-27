"""Authentication service for guide portal login"""

import json
import logging
from urllib.parse import quote

import httpx
from typing import Optional, Dict, Any
from app.models.schemas import LoginAPIRequest, LoginAPIResponse
from app.config import settings
from app.utils.sentry_utils import capture_exception_with_context
from app.utils.sentry_scrubbing import redact_text

# Configure logging
logger = logging.getLogger(__name__)

# V7 API `Response.status` contract (verified against production, Aug 2026):
# 1 = ok, 2 = empty parameter, 3 = invalid API key, 4 = record not found.
_V7_RESPONSE_STATUS_MESSAGES = {
    "1": "ok",
    "2": "empty parameter",
    "3": "invalid API key",
    "4": "record not found",
}


def _api_business_failure(
    body_text: str,
    treat_not_found_as_failure: bool = True,
) -> Optional[str]:
    """Detect a V7 business-logic failure hidden inside an HTTP 200/40x body.

    The V7 TourCube API sometimes signals failure entirely inside the
    response body while still returning a "successful"-looking HTTP status
    (this is how a guide previously lost access to their account: the API
    rejected the request but the portal reported "password changed").

    Two shapes are known to positively indicate failure, verified against
    production:

    - A plain-text body containing `Access Denied` (invalid/missing
      `tc-api-key`).
    - A JSON object -- or a list containing exactly one JSON object --
      carrying `Response.status`, where anything other than `1`/`"1"` is a
      failure (see `_V7_RESPONSE_STATUS_MESSAGES` for the code meanings).

    Returns a short, secret-free description of the failure, or `None` when
    the body does not positively indicate one. A body that can't be parsed
    at all, or that has no `Response.status`, also returns `None` --
    absence of evidence is not evidence of failure, so callers keep the
    pre-existing "assume success" behavior rather than have this helper
    invent a failure.

    `treat_not_found_as_failure=False` makes status 4 ("record not found")
    look like success. The email-sending flows (forgot username / forgot
    password) pass it so that an unknown address stays indistinguishable
    from a known one: surfacing "not found" there would turn the public
    forms into an account-enumeration oracle. Password change keeps the
    default, because a silent "not found" there is exactly the false
    success this helper exists to prevent.
    """
    if not body_text:
        return None

    if "Access Denied" in body_text:
        return "API access denied (invalid API key)"

    try:
        parsed = json.loads(body_text)
    except (ValueError, TypeError):
        return None

    if isinstance(parsed, list):
        if len(parsed) != 1 or not isinstance(parsed[0], dict):
            return None
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        return None

    response = parsed.get("Response")
    if not isinstance(response, dict) or "status" not in response:
        return None

    status_str = str(response["status"])
    if status_str == "1":
        return None
    if status_str == "4" and not treat_not_found_as_failure:
        return None

    description = _V7_RESPONSE_STATUS_MESSAGES.get(status_str, "unknown error")
    return f"API business failure (status={status_str}: {description})"


class AuthService:
    """Service for authentication operations"""

    def __init__(self):
        self.timeout = settings.api_timeout
        self.ssl_verify = settings.ssl_verify

    async def login(
        self,
        username: str,
        password: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> LoginAPIResponse:
        """
        Authenticate user via Tourcube API

        Args:
            username: Portal username
            password: Portal password
            company_code: Company identifier. Required — no default-tenant
                fallback (#148).
            mode: "Test" or "Production". Required — no default-mode fallback
                (#148).

        Returns:
            LoginAPIResponse with authentication result

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Prepare request body
        login_request = LoginAPIRequest(
            portal_user_name=username,
            portal_password=password
        )

        # Build endpoint URL
        endpoint = f"{company_config.api_url}/tourcube/guidePortal/login"

        # Make API call
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.ssl_verify
            ) as client:
                response = await client.post(
                    endpoint,
                    json=login_request.model_dump(by_alias=True),
                    headers={
                        "tc-api-key": company_config.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()

                # Parse response
                data = response.json()
                return LoginAPIResponse(**data)
        except httpx.TimeoutException as e:
            logger.error("Login API timeout for user %s: %s", username, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Login API HTTP error for user %s: %s (status: %s)", username, e, e.response.status_code)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except Exception as e:
            logger.error("Login API unexpected error for user %s: %s", username, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise

    async def get_vendor_info(
        self,
        vendor_id: int,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch vendor information from API

        This is called immediately after vendor login to get vendor details
        and store them in the session.

        Args:
            vendor_id: Vendor's unique identifier
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            Dictionary with vendor info (name, etc.)

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Build endpoint URL
        endpoint = f"{company_config.api_url}/tourcube/guidePortal/getVendorHomepage/{vendor_id}"

        # Make API call
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.ssl_verify
            ) as client:
                response = await client.get(
                    endpoint,
                    headers={"tc-api-key": company_config.api_key}
                )
                response.raise_for_status()

                # Parse response and extract vendor info
                data = response.json()
                return {
                    "vendor_name": data.get("name", "Vendor"),
                    "vendor_id": vendor_id
                }
        except httpx.TimeoutException as e:
            logger.error("Get vendor info API timeout for vendor %s: %s", vendor_id, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Get vendor info API HTTP error for vendor %s: %s (status: %s)", vendor_id, e, e.response.status_code)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except Exception as e:
            logger.error("Get vendor info API unexpected error for vendor %s: %s", vendor_id, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise

    async def send_temp_password(
        self,
        email: str,
        first_name: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> str:
        """
        Send a temporary password email to the user.

        Mirrors the legacy Guide Portal flow (GP_SendGuidePortalTempPasswordEmail):
        the TourCube API generates a temporary password and emails it to the
        user. The legacy looked up email + first_name from the username against
        a local HyperFile DB; the modern portal has no such DB, so the form now
        collects the email and first name directly (same shape as the working
        forgot-username flow).

        Verified contract (OPTIONS against production, Aug 2026): this route
        only allows POST -- GET returns 405 Method Not Allowed. The call must
        carry a JSON body (`json={}` is enough; an empty body gets 411) and a
        `Content-Type: application/json` header (its absence gets 415).

        Args:
            email: User's email address (recipient)
            first_name: User's first name (used in the email greeting)
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            Raw response body from the API

        Raises:
            httpx.HTTPError: If the API call fails, or if the response body
                positively indicates a business-logic failure (see
                `_api_business_failure`).
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Build endpoint URL. Path order matches the legacy contract:
        # tempPassword/{email}/{first_name}. Segments are percent-encoded so
        # emails (@) and names with spaces survive the path.
        endpoint = (
            f"{company_config.api_url}/tourcube/guidePortal/tempPassword/"
            f"{quote(email, safe='')}/{quote(first_name, safe='')}"
        )

        # Make API call
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.ssl_verify
            ) as client:
                response = await client.post(
                    endpoint,
                    json={},
                    headers={
                        "tc-api-key": company_config.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()

                # Unknown addresses must stay indistinguishable from known
                # ones on this public form -- see _api_business_failure.
                failure = _api_business_failure(
                    response.text, treat_not_found_as_failure=False
                )
                if failure:
                    logger.error(
                        "Temp password API business failure for email %s: %s",
                        email, redact_text(failure)
                    )
                    raise httpx.HTTPError(f"Temp password request failed: {failure}")

                return response.text
        except httpx.TimeoutException as e:
            logger.error("Temp password API timeout for email %s: %s", email, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Temp password API HTTP error for email %s: %s (status: %s)", email, e, e.response.status_code)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except Exception as e:
            logger.error("Temp password API unexpected error for email %s: %s", email, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise

    async def send_forgot_username(
        self,
        email: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> str:
        """
        Send username reminder email to user

        Verified contract (OPTIONS against production, Aug 2026): this route
        allows POST/PUT -- GET returns 405 Method Not Allowed. The call must
        carry a JSON body (`json={}`; an empty body gets 411) and a
        `Content-Type: application/json` header (its absence gets 415).

        Args:
            email: User's email address
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            Response message from API

        Raises:
            httpx.HTTPError: If the API call fails, or if the response body
                positively indicates a business-logic failure (see
                `_api_business_failure`).
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Build endpoint URL. The email is percent-encoded so its `@` (and any
        # other reserved characters) survive as a single path segment.
        endpoint = (
            f"{company_config.api_url}/tourcube/guidePortal/forgotUserName/"
            f"{quote(email, safe='')}"
        )

        # Make API call
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.ssl_verify
            ) as client:
                response = await client.post(
                    endpoint,
                    json={},
                    headers={
                        "tc-api-key": company_config.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()

                # Unknown addresses must stay indistinguishable from known
                # ones on this public form -- see _api_business_failure.
                failure = _api_business_failure(
                    response.text, treat_not_found_as_failure=False
                )
                if failure:
                    logger.error(
                        "Forgot username API business failure for email %s: %s",
                        email, redact_text(failure)
                    )
                    raise httpx.HTTPError(f"Forgot username request failed: {failure}")

                return response.text
        except httpx.TimeoutException as e:
            logger.error("Forgot username API timeout for email %s: %s", email, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Forgot username API HTTP error for email %s: %s (status: %s)", email, e, e.response.status_code)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except Exception as e:
            logger.error("Forgot username API unexpected error for email %s: %s", email, e)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise


    async def change_password(
        self,
        client_id: int,
        new_password: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> bool:
        """
        Change portal password via Tourcube API.

        Used for both account types: guides pass their client ID and
        vendors pass their vendor ID (the API resolves both).

        Verified contract (OPTIONS against production, Aug 2026): this route
        only allows PUT, with `json={}` and `Content-Type: application/json`
        (same body/header requirements as the other auth endpoints). The new
        password is a URL PATH SEGMENT (V7 API contract, owned by a separate
        WinDev component -- not something this repo can change), so it must
        be percent-encoded: an un-encoded `%` in the password broke the path
        and made production return 400 (this is how a guide's password
        change silently failed while the portal reported success).

        Args:
            client_id: Guide's client ID or vendor's vendor ID
            new_password: New password to set
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            True if password was changed successfully

        Raises:
            httpx.HTTPError: If the API call fails, or if the response body
                positively indicates a business-logic failure (see
                `_api_business_failure`).
        """
        company_config = settings.get_company_config(company_code, mode)

        endpoint = (
            f"{company_config.api_url}/tourcube/v1/client/{client_id}/password/"
            f"{quote(new_password, safe='')}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                verify=self.ssl_verify
            ) as client:
                response = await client.put(
                    endpoint,
                    json={},
                    headers={
                        "tc-api-key": company_config.api_key,
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()

                failure = _api_business_failure(response.text)
                if failure:
                    # `failure` is a secret-free status description (see
                    # _api_business_failure) -- no redact_text needed on it,
                    # but the client_id-scoped log line follows the same
                    # redact_text(...) convention as the other except blocks
                    # below for consistency.
                    logger.error(
                        "Change password API business failure for client %s: %s",
                        client_id, redact_text(failure)
                    )
                    raise httpx.HTTPError(f"Change password request failed: {failure}")

                return True
        except httpx.TimeoutException as e:
            # The endpoint (and therefore str(e)) contains the new password
            # as a URL path segment (V7 API contract) -- redact before logging.
            logger.error("Change password API timeout for client %s: %s", client_id, redact_text(str(e)))
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("Change password API HTTP error for client %s: %s (status: %s)", client_id, redact_text(str(e)), e.response.status_code)
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise
        except Exception as e:
            logger.error("Change password API unexpected error for client %s: %s", client_id, redact_text(str(e)))
            capture_exception_with_context(e, mode=mode, company_code=company_code)
            raise


# Global auth service instance
auth_service = AuthService()
