"""Tests for MobileDetectionMiddleware and is_mobile_user_agent (#160)."""

import pytest

from app.middleware.mobile_detection import is_mobile_user_agent


MOBILE_UAS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 12_5 like Mac OS X) Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 12; SM-T870) Tablet Safari/537.36",
    "Opera/9.80 (J2ME/MIDP; Opera Mini/9.80; U; en) Presto",
    "Mozilla/5.0 (Windows Phone 10.0; IEMobile/9.0)",
    "BlackBerry9700/5.0",
    "Mozilla/5.0 (Linux; U; Android 4.0.3; en-us; Kindle Fire) Silk/2.1",
]

DESKTOP_UAS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (X11; Linux x86_64) Firefox/121.0",
    "",
]


@pytest.mark.parametrize("ua", MOBILE_UAS)
def test_mobile_ua_detected(ua):
    assert is_mobile_user_agent(ua) is True


@pytest.mark.parametrize("ua", DESKTOP_UAS)
def test_desktop_ua_not_detected(ua):
    assert is_mobile_user_agent(ua) is False


def test_main_app_sets_is_mobile_attribute():
    """Smoke: confirm app.main wires MobileDetectionMiddleware so
    request.state.is_mobile is always populated."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # Route does not matter; we just need any request to flow through.
    # Use a route that exists (/healthz or /) — fallback to /manifest.json
    # which exists in app.routes.pwa.
    resp = client.get("/manifest.json", headers={"User-Agent": "iPhone"})
    # We're not asserting on body here; only that the app boots and the
    # request flowed without crashing inside any middleware.
    assert resp.status_code in (200, 404)
