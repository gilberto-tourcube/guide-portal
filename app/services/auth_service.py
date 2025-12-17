"""Authentication service for guide portal login"""

import logging
import httpx
from typing import Optional, Dict, Any
from app.models.schemas import LoginAPIRequest, LoginAPIResponse
from app.config import settings
from app.utils.sentry_utils import capture_exception_with_context

# Configure logging
logger = logging.getLogger(__name__)


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
            company_code: Company identifier (defaults to settings.company_code)
            mode: "Test" or "Production" (defaults to settings.mode)

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
        username: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> str:
        """
        Send temporary password email to user

        This requires looking up the user's email first, then calling the API.
        For now, we'll assume the username lookup happens client-side or
        the API accepts username directly.

        Args:
            username: Portal username
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            Response message from API

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Note: The legacy system queries the database first to get email and first_name
        # For the modern system, we'll need to either:
        # 1. Query our own database/API to get this info first
        # 2. Have the API endpoint accept username instead
        # For now, this is a simplified version that assumes API will handle lookup

        # TODO: Implement proper user lookup before calling this endpoint
        # For now, raising NotImplementedError
        raise NotImplementedError(
            "send_temp_password requires user lookup implementation. "
            "Please implement user query to get email and first_name before calling API."
        )

    async def send_forgot_username(
        self,
        email: str,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> str:
        """
        Send username reminder email to user

        Args:
            email: User's email address
            company_code: Company identifier
            mode: "Test" or "Production"

        Returns:
            Response message from API

        Raises:
            httpx.HTTPError: If API call fails
        """
        # Get company configuration with API credentials
        company_config = settings.get_company_config(company_code, mode)

        # Build endpoint URL
        endpoint = f"{company_config.api_url}/tourcube/guidePortal/forgotUserName/{email}"

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


# Global auth service instance
auth_service = AuthService()
