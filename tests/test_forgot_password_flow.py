from html import unescape

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_forgot_password_page_uses_auth_routes_and_tenant_context(
    secure_client, reset_debug
):
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-password?company_code=WT&mode=Test",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text)
    assert 'action="/auth/forgot-password"' in body
    assert 'href="/auth/login?company_code=WT&mode=Test"' in body
    assert 'name="company_code" value="WT"' in body
    assert 'name="mode" value="Test"' in body
    assert '{"detail":"Not Found"}' not in body


@pytest.mark.asyncio
async def test_forgot_password_submit_returns_friendly_branded_page(
    secure_client, reset_debug
):
    settings.debug = False
    company_config = settings.get_company_config("WT", "Test")

    response = await secure_client.post(
        "/auth/forgot-password",
        data={"username": "guide-user", "company_code": "WT", "mode": "Test"},
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = unescape(response.text)
    assert "Forgot password feature is not yet implemented. Please contact support." in body
    assert company_config.logo in body
    if company_config.login_background:
        assert company_config.login_background in body
    assert 'href="/auth/login?company_code=WT&mode=Test"' in body
    assert '{"detail":"Not Found"}' not in body
