from html import unescape

import pytest

from app.config import settings
from app.services.auth_service import auth_service


@pytest.mark.asyncio
async def test_forgot_username_page_uses_auth_routes_and_tenant_context(
    secure_client, reset_debug
):
    """The form must post to /auth/forgot-username (not /forgot-username, which
    404s with {"detail":"Not Found"}) and the Back to Login link must point at
    the /auth login route. (DEVCUR-1708 returned testing.)
    """
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-username?company_code=WT&mode=Test",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text)
    assert 'action="/auth/forgot-username"' in body
    assert 'action="/forgot-username"' not in body
    assert 'href="/auth/login?company_code=WT&mode=Test"' in body
    assert 'name="email"' in body


@pytest.mark.asyncio
async def test_forgot_username_page_shows_failure_message(secure_client, reset_debug):
    """An invalid/failed submission redirects with success=false; the page must
    render the inline error banner instead of leaving the user with no feedback.
    """
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-username?company_code=WT&mode=Test&success=false",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text)
    assert "Unable to send email." in body


@pytest.mark.asyncio
async def test_forgot_username_page_shows_success_message(secure_client, reset_debug):
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-username?company_code=WT&mode=Test&success=true",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text)
    assert "Email sent!" in body


@pytest.mark.asyncio
async def test_forgot_username_email_input_enforces_stricter_pattern(
    secure_client, reset_debug
):
    """type=email alone accepts addresses with no domain dot (e.g.
    name@test); the input must carry a stricter pattern so the browser
    rejects them.
    """
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-username?company_code=WT&mode=Test",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    assert "pattern=" in response.text


@pytest.mark.asyncio
async def test_forgot_username_rejects_malformed_email_without_calling_api(
    monkeypatch, secure_client, reset_debug
):
    """A malformed email (no domain dot) must not reach the API; the user is
    redirected back with a clear invalid-email message.
    """
    settings.debug = False
    calls = {"n": 0}

    async def fake_send_forgot_username(email, company_code=None, mode=None):
        calls["n"] += 1
        return "OK"

    monkeypatch.setattr(
        auth_service, "send_forgot_username", fake_send_forgot_username
    )

    response = await secure_client.post(
        "/auth/forgot-username",
        data={"email": "not-a-email@test", "company_code": "WT", "mode": "Test"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/auth/forgot-username?company_code=WT&mode=Test&error=invalid_email"
    )
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_forgot_username_page_shows_invalid_email_message(
    secure_client, reset_debug
):
    settings.debug = False

    response = await secure_client.get(
        "/auth/forgot-username?company_code=WT&mode=Test&error=invalid_email",
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 200
    body = unescape(response.text).lower()
    assert "valid email address" in body
