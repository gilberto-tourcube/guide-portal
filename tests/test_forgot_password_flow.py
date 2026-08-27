from html import unescape

import httpx
import pytest

from app.config import settings
from app.services.auth_service import auth_service


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
    # The form now collects a portal username (DEVCUR-1761): the working
    # v1/client/resetPassword route is keyed on username, not email/first
    # name -- same shape as the legacy guide portal's own reset screen.
    assert 'name="username"' in body
    assert 'name="email"' not in body
    assert 'name="first_name"' not in body
    assert '{"detail":"Not Found"}' not in body
    assert "not yet implemented" not in body


@pytest.mark.asyncio
async def test_forgot_password_submit_requests_password_reset_and_redirects(
    monkeypatch, secure_client, reset_debug
):
    settings.debug = False
    calls = {}

    async def fake_request_password_reset(portal_user_name, company_code=None, mode=None):
        calls.update(
            portal_user_name=portal_user_name,
            company_code=company_code,
            mode=mode,
        )
        return "OK"

    monkeypatch.setattr(
        auth_service, "request_password_reset", fake_request_password_reset
    )

    response = await secure_client.post(
        "/auth/forgot-password",
        data={
            "username": "guide.jsmith",
            "company_code": "WT",
            "mode": "Test",
        },
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/auth/forgot-password?company_code=WT&mode=Test&success=true"
    )
    assert calls == {
        "portal_user_name": "guide.jsmith",
        "company_code": "WT",
        "mode": "Test",
    }


@pytest.mark.asyncio
async def test_forgot_password_submit_redirects_to_failure_on_api_error(
    monkeypatch, secure_client, reset_debug
):
    settings.debug = False

    async def fake_request_password_reset(portal_user_name, company_code=None, mode=None):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(
        auth_service, "request_password_reset", fake_request_password_reset
    )

    response = await secure_client.post(
        "/auth/forgot-password",
        data={
            "username": "guide.jsmith",
            "company_code": "WT",
            "mode": "Test",
        },
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/auth/forgot-password?company_code=WT&mode=Test&success=false"
    )


@pytest.mark.asyncio
async def test_forgot_password_submit_rejects_empty_username_without_calling_service(
    monkeypatch, secure_client, reset_debug
):
    """An empty username must not reach the service -- `min_length=1` on the
    form field rejects it with a 422 before `request_password_reset` is
    ever called."""
    settings.debug = False
    calls = {"n": 0}

    async def fake_request_password_reset(portal_user_name, company_code=None, mode=None):
        calls["n"] += 1
        return "OK"

    monkeypatch.setattr(
        auth_service, "request_password_reset", fake_request_password_reset
    )

    response = await secure_client.post(
        "/auth/forgot-password",
        data={"username": "", "company_code": "WT", "mode": "Test"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 422
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_forgot_password_page_shows_success_message(secure_client, reset_debug):
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-password?company_code=WT&mode=Test&success=true",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text)
    assert "Email sent!" in body


@pytest.mark.asyncio
async def test_request_password_reset_builds_client_endpoint(monkeypatch):
    """The service hits the working contract: GET v1/client/resetPassword/
    {portalUserName} with the tc-api-key header, percent-encoding the path
    segment.

    Measured against test AND production (Aug 2026, DEVCUR-1761): the
    legacy tempPassword/{email}/{firstName} route crashes inside the API
    with a 500 on both environments, so it was replaced with this GET,
    keyed on portal username instead of email/first name.
    """
    captured = {}

    class FakeResponse:
        text = "sent"

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResponse()

    import app.services.auth_service as svc

    monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)

    cfg = settings.get_company_config("WT", "Test")
    result = await auth_service.request_password_reset(
        portal_user_name="jo ann/smith",
        company_code="WT",
        mode="Test",
    )

    assert result == "sent"
    assert captured["url"] == (
        f"{cfg.api_url}/tourcube/v1/client/resetPassword/"
        "jo%20ann%2Fsmith"
    )
    assert captured["headers"]["tc-api-key"] == cfg.api_key
    assert "Content-Type" not in captured["headers"]
