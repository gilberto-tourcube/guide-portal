"""Tests for the global exception handlers added in #136."""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def error_client():
    """Local client with raise_app_exceptions=False so the test reaches the
    user-registered exception handler instead of bubbling the original
    exception up through the ASGI transport.

    Also forces ``settings.debug=False`` for the duration of the request — the
    Starlette debug traceback middleware shadows user-registered exception
    handlers when debug is on, which is irrelevant for this test surface.
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    original_debug = settings.debug
    original_app_debug = app.debug
    settings.debug = False
    app.debug = False
    try:
        async with AsyncClient(transport=transport, base_url="https://testserver") as ac:
            yield ac
    finally:
        settings.debug = original_debug
        app.debug = original_app_debug


@pytest.fixture(autouse=True)
def _reset_handler_routes():
    """Add temporary routes that always raise, then remove them after each test
    so the rest of the suite is unaffected.
    """

    @app.get("/__test__/boom")
    async def _boom():  # pragma: no cover - exercised via client
        raise RuntimeError("boom")

    @app.get("/__test__/http500")
    async def _http500():  # pragma: no cover
        raise HTTPException(status_code=500, detail="forced 500")

    @app.get("/__test__/http503")
    async def _http503():  # pragma: no cover
        raise HTTPException(status_code=503, detail="forced 503")

    @app.get("/__test__/http404")
    async def _http404():  # pragma: no cover
        raise HTTPException(status_code=404, detail="forced 404")

    yield

    # Strip the temporary routes so the app surface stays clean across tests.
    app.router.routes = [
        r for r in app.router.routes
        if not getattr(r, "path", "").startswith("/__test__/")
    ]


@pytest.mark.asyncio
async def test_unhandled_exception_renders_friendly_page_for_browser_navigation(
    error_client, reset_debug
):
    """A bare RuntimeError on a GET should yield 500 + the error.html page when
    the request looks like a browser navigation (Accept: text/html).
    """
    response = await error_client.get(
        "/__test__/boom",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 500
    body = response.text
    assert "Something Went Wrong" in body
    assert "Return Home" in body
    # Stack trace must NOT leak into the HTML.
    assert "Traceback" not in body
    assert "RuntimeError" not in body


@pytest.mark.asyncio
async def test_unhandled_exception_returns_json_for_api_caller(
    error_client, reset_debug
):
    """API/AJAX callers (Accept: application/json) must keep getting JSON,
    not the HTML page. Preserves API contract.
    """
    response = await error_client.get(
        "/__test__/boom",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Internal Server Error"
    # sentry_event_id key is always present (None when Sentry disabled).
    assert "sentry_event_id" in body


@pytest.mark.asyncio
async def test_5xx_http_exception_renders_friendly_page(secure_client, reset_debug):
    """HTTPException(500) on a browser navigation should also hit the friendly
    page rather than returning the bare {"detail": "..."} JSON.
    """
    response = await secure_client.get(
        "/__test__/http500",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 500
    assert "Something Went Wrong" in response.text


@pytest.mark.asyncio
async def test_503_renders_friendly_page(secure_client, reset_debug):
    response = await secure_client.get(
        "/__test__/http503",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 503
    assert "Something Went Wrong" in response.text


@pytest.mark.asyncio
async def test_4xx_http_exception_keeps_default_behaviour(
    secure_client, reset_debug
):
    """4xx responses must keep the default Starlette JSON behaviour so
    auth redirects and client-error contracts do not regress.
    """
    response = await secure_client.get(
        "/__test__/http404",
        headers={"Accept": "text/html"},
    )
    assert response.status_code == 404
    # Default Starlette HTTP handler returns JSON {"detail": "..."} — this is
    # the existing contract for non-redirected 4xxs.
    assert response.json() == {"detail": "forced 404"}


@pytest.mark.asyncio
async def test_405_method_not_allowed_keeps_default(secure_client, reset_debug):
    """POST against a GET-only route should still get a plain 405, not the
    friendly page (4xx is a client error, not a server fault).
    """
    response = await secure_client.post("/__test__/boom")
    assert response.status_code == 405
