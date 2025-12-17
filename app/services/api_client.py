"""HTTP client for external Tourcube API communication"""

import httpx
import logging
import json as json_module
import sentry_sdk
from typing import Optional, Dict, Any
from app.config import settings

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class APIClient:
    """Async HTTP client for Tourcube API"""

    def __init__(self):
        self.base_url = settings.api_base_url
        self.api_key = settings.api_key
        self.timeout = settings.api_timeout
        self.verify_ssl = settings.ssl_verify

    def _get_headers(self) -> Dict[str, str]:
        """Get standard headers for API requests"""
        return {
            "tc-api-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": f"{settings.app_name}/{settings.app_version}"
        }

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform GET request to Tourcube API

        Args:
            endpoint: API endpoint path (without base URL)
            params: Optional query parameters

        Returns:
            JSON response as dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # Log request details
        logger.info("="*80)
        logger.info("API GET REQUEST")
        logger.info(f"URL: {url}")
        logger.info(f"Params: {params}")
        logger.info(f"Headers: {headers}")

        # Build cURL command
        curl_cmd = f"curl -X GET '{url}'"
        if params:
            param_str = "&".join([f"{k}={v}" for k, v in params.items()])
            curl_cmd = f"curl -X GET '{url}?{param_str}'"
        for key, value in headers.items():
            curl_cmd += f" -H '{key}: {value}'"
        logger.info(f"cURL equivalent:\n{curl_cmd}")
        logger.info("="*80)

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl
            ) as client:
                response = await client.get(url, params=params)

                # Log response details
                logger.info("="*80)
                logger.info("API GET RESPONSE")
                logger.info(f"Status Code: {response.status_code}")
                logger.info(f"Response Body:\n{json_module.dumps(response.json(), indent=2, ensure_ascii=False)}")
                logger.info("="*80)

                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            logger.error("API GET timeout for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("API GET HTTP error for %s: %s (status: %s)", url, e, e.response.status_code)
            sentry_sdk.capture_exception(e)
            raise
        except httpx.RequestError as e:
            logger.error("API GET request error for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise
        except Exception as e:
            logger.error("API GET unexpected error for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise

    async def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Perform POST request to Tourcube API

        Args:
            endpoint: API endpoint path (without base URL)
            data: Optional form data
            json: Optional JSON payload

        Returns:
            JSON response as dictionary

        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.base_url}{endpoint}"
        headers = self._get_headers()

        # Log request details
        logger.info("="*80)
        logger.info("API POST REQUEST")
        logger.info(f"URL: {url}")
        logger.info(f"Form Data: {data}")
        logger.info(f"JSON Body: {json_module.dumps(json, indent=2, ensure_ascii=False) if json else None}")
        logger.info(f"Headers: {headers}")

        # Build cURL command
        curl_cmd = f"curl -X POST '{url}'"
        for key, value in headers.items():
            curl_cmd += f" -H '{key}: {value}'"
        if json:
            json_str = json_module.dumps(json, ensure_ascii=False).replace("'", "'\\''")
            curl_cmd += f" -d '{json_str}'"
        elif data:
            for key, value in data.items():
                curl_cmd += f" -d '{key}={value}'"
        logger.info(f"cURL equivalent:\n{curl_cmd}")
        logger.info("="*80)

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self.timeout,
                verify=self.verify_ssl
            ) as client:
                response = await client.post(url, data=data, json=json)

                # Log response details
                logger.info("="*80)
                logger.info("API POST RESPONSE")
                logger.info(f"Status Code: {response.status_code}")
                logger.info(f"Response Body:\n{json_module.dumps(response.json(), indent=2, ensure_ascii=False)}")
                logger.info("="*80)

                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as e:
            logger.error("API POST timeout for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise
        except httpx.HTTPStatusError as e:
            logger.error("API POST HTTP error for %s: %s (status: %s)", url, e, e.response.status_code)
            sentry_sdk.capture_exception(e)
            raise
        except httpx.RequestError as e:
            logger.error("API POST request error for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise
        except Exception as e:
            logger.error("API POST unexpected error for %s: %s", url, e)
            sentry_sdk.capture_exception(e)
            raise


# Global API client instance
api_client = APIClient()
