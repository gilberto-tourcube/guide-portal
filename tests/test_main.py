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
async def test_root_renders_neutral_error_without_tenant_context(
    secure_client, reset_debug
):
    """Anonymous `GET /` (no companyCode, no mode, no host mapping) must
    render the neutral error page — never redirect to login with the env-var
    default tenant (#148).
    """
    settings.debug = False
    response = await secure_client.get(
        "/",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 400
    body = response.text
    assert "Tenant Required" in body
    # Default-tenant leak guards: the env-var values must NOT appear anywhere.
    assert settings.company_code not in body
    assert "Wilderness Travel" not in body
    # Make sure the page is not redirecting to a tenant-branded login.
    assert "location" not in {k.lower() for k in response.headers}


@pytest.mark.asyncio
async def test_root_redirects_to_login_when_tenant_in_query(
    secure_client, reset_debug
):
    """When the caller supplies tenant context via query params, `GET /`
    redirects to `/auth/login` carrying those same params. Verifies the
    happy-path still works after the default-tenant fallback was removed.
    """
    settings.debug = False
    response = await secure_client.get(
        "/?company_code=WTGUIDE&mode=Test",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?company_code=WTGUIDE&mode=Test"
