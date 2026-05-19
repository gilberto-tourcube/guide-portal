"""Manifest gating matrix (#160): 4 scenarios over (pwa_enabled, is_mobile)."""

import json

from fastapi.testclient import TestClient

from app.main import app


IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148"
DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605"


def _manifest(company_code: str, ua: str):
    client = TestClient(app)
    return client.get(
        f"/manifest.json?companyCode={company_code}&mode=Test",
        headers={"User-Agent": ua},
    )


def _first_pwa_enabled_tenant():
    from app.config import settings
    for code, cfg in settings._load_company_configs().items():
        if cfg.pwa_enabled:
            return code
    return None


def _first_pwa_disabled_tenant():
    from app.config import settings
    for code, cfg in settings._load_company_configs().items():
        if not cfg.pwa_enabled:
            return code
    return None


def test_manifest_pwa_on_mobile_returns_200():
    code = _first_pwa_enabled_tenant()
    if not code:
        # Skip when apikey.json has no opted-in tenant (e.g. pre-rollout).
        return
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert "name" in body


def test_manifest_pwa_on_desktop_returns_404():
    code = _first_pwa_enabled_tenant()
    if not code:
        return
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_mobile_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        return
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_desktop_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        return
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_anonymous_returns_404():
    """No companyCode/mode + no session → 404 (no neutral install surface)."""
    client = TestClient(app)
    resp = client.get("/manifest.json", headers={"User-Agent": IPHONE_UA})
    assert resp.status_code == 404
