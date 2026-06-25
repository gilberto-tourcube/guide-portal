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
    # The form now collects email + first name (the legacy username->email DB
    # lookup is not available to the modern portal; DEVCUR-1708).
    assert 'name="email"' in body
    assert 'name="first_name"' in body
    assert '{"detail":"Not Found"}' not in body
    assert "not yet implemented" not in body


@pytest.mark.asyncio
async def test_forgot_password_submit_sends_temp_password_and_redirects(
    monkeypatch, secure_client, reset_debug
):
    settings.debug = False
    calls = {}

    async def fake_send_temp_password(email, first_name, company_code=None, mode=None):
        calls.update(
            email=email,
            first_name=first_name,
            company_code=company_code,
            mode=mode,
        )
        return "OK"

    monkeypatch.setattr(auth_service, "send_temp_password", fake_send_temp_password)

    response = await secure_client.post(
        "/auth/forgot-password",
        data={
            "email": "guide@example.com",
            "first_name": "Guide",
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
        "email": "guide@example.com",
        "first_name": "Guide",
        "company_code": "WT",
        "mode": "Test",
    }


@pytest.mark.asyncio
async def test_forgot_password_submit_redirects_to_failure_on_api_error(
    monkeypatch, secure_client, reset_debug
):
    settings.debug = False

    async def fake_send_temp_password(email, first_name, company_code=None, mode=None):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(auth_service, "send_temp_password", fake_send_temp_password)

    response = await secure_client.post(
        "/auth/forgot-password",
        data={
            "email": "guide@example.com",
            "first_name": "Guide",
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
async def test_send_temp_password_builds_legacy_endpoint(monkeypatch):
    """The service hits the legacy contract: GET tempPassword/{email}/{first_name}
    with the tc-api-key header, percent-encoding the path segments.
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
    result = await auth_service.send_temp_password(
        email="jo ann@example.com",
        first_name="Jo Ann",
        company_code="WT",
        mode="Test",
    )

    assert result == "sent"
    assert captured["url"] == (
        f"{cfg.api_url}/tourcube/guidePortal/tempPassword/"
        "jo%20ann%40example.com/Jo%20Ann"
    )
    assert captured["headers"]["tc-api-key"] == cfg.api_key
