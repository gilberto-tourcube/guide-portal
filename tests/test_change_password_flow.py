"""Change-password flow: guides and vendors share the same API endpoint.

The legacy vendor-specific endpoint (PUT /tourcube/guidePortal/{id}/{pw})
is retired. Both account types now go through auth_service.change_password,
keyed on the client ID of the person behind the account.
"""

import pytest

from app.config import settings
from app.services.auth_service import auth_service


def _install_fake_change_password(monkeypatch):
    calls = {}

    async def fake_change_password(client_id, new_password, company_code=None, mode=None):
        calls.update(
            client_id=client_id,
            new_password=new_password,
            company_code=company_code,
            mode=mode,
        )
        return True

    monkeypatch.setattr(auth_service, "change_password", fake_change_password)
    return calls


@pytest.mark.asyncio
async def test_vendor_change_password_uses_unified_endpoint(
    monkeypatch, secure_client, session_cookie_factory, reset_debug
):
    settings.debug = False
    calls = _install_fake_change_password(monkeypatch)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "user_type": 2,
            "vendor_id": 73400,
            "client_id": 504627,  # person behind the vendor account
            "company_code": "WT",
            "mode": "Test",
            "temp_password": True,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.post(
        "/auth/change-password",
        data={
            "new_password": "NewVendorPass1",
            "confirm_password": "NewVendorPass1",
            "company_code": "WT",
            "mode": "Test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/vendor/home"
    assert calls == {
        "client_id": 504627,
        "new_password": "NewVendorPass1",
        "company_code": "WT",
        "mode": "Test",
    }


@pytest.mark.asyncio
async def test_guide_change_password_uses_unified_endpoint(
    monkeypatch, secure_client, session_cookie_factory, reset_debug
):
    settings.debug = False
    calls = _install_fake_change_password(monkeypatch)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "user_type": 1,
            "guide_id": 850669,
            "client_id": 850669,
            "company_code": "WT",
            "mode": "Test",
            "temp_password": True,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.post(
        "/auth/change-password",
        data={
            "new_password": "NewGuidePass1",
            "confirm_password": "NewGuidePass1",
            "company_code": "WT",
            "mode": "Test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/guide/home"
    assert calls == {
        "client_id": 850669,
        "new_password": "NewGuidePass1",
        "company_code": "WT",
        "mode": "Test",
    }


def test_vendor_specific_password_endpoint_is_retired():
    assert not hasattr(auth_service, "change_vendor_password")


@pytest.mark.asyncio
async def test_change_password_without_client_id_does_not_report_success(
    monkeypatch, secure_client, session_cookie_factory, reset_debug
):
    """A vendor account whose login carried no client ID must not be told the
    password changed — the endpoint has nothing to key the update on."""
    settings.debug = False
    calls = _install_fake_change_password(monkeypatch)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "user_type": 2,
            "vendor_id": 73400,
            "company_code": "WT",
            "mode": "Test",
            "temp_password": True,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.post(
        "/auth/change-password",
        data={
            "new_password": "NewVendorPass1",
            "confirm_password": "NewVendorPass1",
            "company_code": "WT",
            "mode": "Test",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/change-password?error=api_error"
    assert calls == {}
