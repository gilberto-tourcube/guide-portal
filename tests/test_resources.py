import types

import httpx
import pytest
from starlette.responses import HTMLResponse

from app.config import settings
from app.routes import resources
from app.services.guide_service import guide_service


def _patch_template(monkeypatch, captured: dict):
    """Replace TemplateResponse with a stub that captures inputs."""

    def fake_template_response(template_name, context):
        captured["template_name"] = template_name
        captured["context"] = context
        return HTMLResponse("ok", status_code=200)

    monkeypatch.setattr(
        resources,
        "templates",
        types.SimpleNamespace(TemplateResponse=fake_template_response)
    )


@pytest.mark.asyncio
async def test_departure_requires_auth_redirects_to_login(secure_client, reset_debug):
    settings.debug = False
    response = await secure_client.get("/departure/123", follow_redirects=False)

    expected_location = (
        f"/auth/login?company_code={settings.company_code}&mode={settings.mode}&error=unauthorized"
    )
    assert response.status_code == 302
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
async def test_departure_renders_with_session(monkeypatch, secure_client, session_cookie_factory, reset_debug):
    settings.debug = False
    captured = {}
    _patch_template(monkeypatch, captured)

    async def fake_get_trip_departure(trip_departure_id, guide_id, company_code, mode):
        captured["service_args"] = {
            "trip_departure_id": trip_departure_id,
            "guide_id": guide_id,
            "company_code": company_code,
            "mode": mode,
        }
        return {"id": trip_departure_id, "name": "Departure Name"}

    monkeypatch.setattr(guide_service, "get_trip_departure", fake_get_trip_departure)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "guide_id": 9,
            "company_code": settings.company_code,
            "mode": settings.mode,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.get("/departure/321?tab=forms")

    assert response.status_code == 200
    assert captured["template_name"] == "pages/trip_departure.html"
    assert captured["context"]["departure"] == {"id": 321, "name": "Departure Name"}
    assert captured["context"]["active_tab"] == "forms"
    assert captured["service_args"] == {
        "trip_departure_id": 321,
        "guide_id": 9,
        "company_code": settings.company_code,
        "mode": settings.mode,
    }


@pytest.mark.asyncio
async def test_trip_requires_auth_redirects_to_login(secure_client, reset_debug):
    settings.debug = False
    response = await secure_client.get("/trip/555", follow_redirects=False)

    expected_location = (
        f"/auth/login?company_code={settings.company_code}&mode={settings.mode}&error=unauthorized"
    )
    assert response.status_code == 302
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
async def test_trip_renders_with_vendor_session(monkeypatch, secure_client, session_cookie_factory, reset_debug):
    settings.debug = False
    captured = {}
    _patch_template(monkeypatch, captured)

    async def fake_get_trip_page(trip_id, guide_id, company_code, mode):
        captured["service_args"] = {
            "trip_id": trip_id,
            "guide_id": guide_id,
            "company_code": company_code,
            "mode": mode,
        }
        return {"id": trip_id, "title": "Trip Title"}

    monkeypatch.setattr(guide_service, "get_trip_page", fake_get_trip_page)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "vendor_id": 77,  # vendor should be used when guide_id is absent
            "company_code": settings.company_code,
            "mode": settings.mode,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.get("/trip/42?tab=past")

    assert response.status_code == 200
    assert captured["template_name"] == "pages/trip.html"
    assert captured["context"]["trip"] == {"id": 42, "title": "Trip Title"}
    assert captured["context"]["active_tab"] == "past"
    assert captured["service_args"] == {
        "trip_id": 42,
        "guide_id": 77,  # vendor ID used as guide_id parameter
        "company_code": settings.company_code,
        "mode": settings.mode,
    }


@pytest.mark.asyncio
async def test_client_requires_auth_redirects_to_login(secure_client, reset_debug):
    settings.debug = False
    response = await secure_client.get("/client/999", follow_redirects=False)

    expected_location = (
        f"/auth/login?company_code={settings.company_code}&mode={settings.mode}&error=unauthorized"
    )
    assert response.status_code == 302
    assert response.headers["location"] == expected_location


@pytest.mark.asyncio
async def test_client_renders_with_session(monkeypatch, secure_client, session_cookie_factory, reset_debug):
    settings.debug = False
    captured = {}
    _patch_template(monkeypatch, captured)

    async def fake_get_client_details(client_id, guide_id, company_code, mode):
        captured["service_args"] = {
            "client_id": client_id,
            "guide_id": guide_id,
            "company_code": company_code,
            "mode": mode,
        }
        return {"id": client_id, "name": "Client Name"}

    monkeypatch.setattr(guide_service, "get_client_details", fake_get_client_details)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "guide_id": 5,
            "company_code": settings.company_code,
            "mode": settings.mode,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.get(
        "/client/88?from_page=trip_departure&trip_id=1&departure_id=2&trip_name=Trip&trip_dates=2024"
    )

    assert response.status_code == 200
    assert captured["template_name"] == "pages/client.html"
    assert captured["context"]["client"] == {"id": 88, "name": "Client Name"}
    assert captured["context"]["from_page"] == "trip_departure"
    assert captured["context"]["trip_id"] == 1
    assert captured["context"]["departure_id"] == 2
    assert captured["context"]["trip_name"] == "Trip"
    assert captured["context"]["trip_dates"] == "2024"
    assert captured["service_args"] == {
        "client_id": 88,
        "guide_id": 5,
        "company_code": settings.company_code,
        "mode": settings.mode,
    }


@pytest.mark.asyncio
async def test_trip_handles_http_error(monkeypatch, secure_client, session_cookie_factory, reset_debug):
    settings.debug = False

    async def fake_get_trip_page(*_args, **_kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(guide_service, "get_trip_page", fake_get_trip_page)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "guide_id": 1,
            "company_code": settings.company_code,
            "mode": settings.mode,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.get("/trip/9")

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to load trip information. Please try again later."


@pytest.mark.asyncio
async def test_client_handles_http_error(monkeypatch, secure_client, session_cookie_factory, reset_debug):
    settings.debug = False

    async def fake_get_client_details(*_args, **_kwargs):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(guide_service, "get_client_details", fake_get_client_details)

    session_cookie = session_cookie_factory(
        {
            "authenticated": True,
            "guide_id": 1,
            "company_code": settings.company_code,
            "mode": settings.mode,
        }
    )
    secure_client.cookies.set(settings.session_cookie_name, session_cookie)

    response = await secure_client.get("/client/7")

    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to load client information. Please try again later."
