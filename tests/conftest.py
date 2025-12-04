import os
import sys
from pathlib import Path

import base64
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner

# Ensure required environment variables exist before application imports
os.environ.setdefault("SECRET_KEY", "test-secret-key")

# Make sure project root is on sys.path for module resolution
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app  # noqa: E402  # imported after env setup
from app.config import settings  # noqa: E402


@pytest_asyncio.fixture
async def client():
    """HTTP client using HTTP scheme (to test redirects)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def secure_client():
    """HTTP client using HTTPS scheme (avoids redirect middleware)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://testserver") as async_client:
        yield async_client


@pytest.fixture
def reset_debug():
    """Restore settings.debug after tests mutate it."""
    original_debug = settings.debug
    yield
    settings.debug = original_debug


@pytest.fixture
def session_cookie_factory():
    """Return a helper to sign session data into a cookie value."""
    signer = TimestampSigner(settings.secret_key)

    def _make_cookie(session_dict: dict) -> str:
        data = json.dumps(session_dict).encode("utf-8")
        data = base64.b64encode(data)
        signed = signer.sign(data)
        return signed.decode("utf-8")

    return _make_cookie
