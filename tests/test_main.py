import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_health_endpoint_returns_status_and_version(secure_client, reset_debug):
    settings.debug = False
    response = await secure_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "version": settings.app_version}
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains; preload"


@pytest.mark.asyncio
async def test_http_requests_are_redirected_to_https(client, reset_debug):
    settings.debug = False
    response = await client.get("/health", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://testserver/health"


@pytest.mark.asyncio
async def test_http_requests_skip_redirect_when_debug(client, reset_debug):
    settings.debug = True
    response = await client.get("/health")

    assert response.status_code == 200
    assert "Strict-Transport-Security" not in response.headers


@pytest.mark.asyncio
async def test_root_redirects_to_login_with_defaults(secure_client, reset_debug):
    settings.debug = False
    response = await secure_client.get("/", follow_redirects=False)

    expected_location = f"/auth/login?company_code={settings.company_code}&mode={settings.mode}"
    assert response.status_code == 302
    assert response.headers["location"] == expected_location
