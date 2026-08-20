"""Manifest gating matrix (#160): 4 scenarios over (pwa_enabled, is_mobile)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import CompanyConfig, settings
from app.routes.pwa import DEFAULT_PWA_THEME_COLOR


IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) Mobile/15E148"
DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605"


@pytest.fixture(autouse=True)
def tracked_tenant_matrix(monkeypatch):
    """PWA tests need the versioned tenant schema, never a local secret file."""
    monkeypatch.setattr(settings, "api_key_json_path", "config/apikey.json.example")
    monkeypatch.setattr(settings, "_company_configs", None)
    monkeypatch.setattr(settings, "_domain_map", None)


def _manifest(company_code: str, ua: str):
    client = TestClient(app)
    return client.get(
        f"/manifest.json?companyCode={company_code}&mode=Test",
        headers={"User-Agent": ua},
    )


def _manifest_snake_case(company_code: str, ua: str):
    client = TestClient(app)
    return client.get(
        f"/manifest.json?company_code={company_code}&mode=Test",
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
        pytest.skip("No opted-in tenant in apikey.json (pre-Task-15 rollout)")
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 200
    body = json.loads(resp.content)
    assert "name" in body


def test_manifest_accepts_snake_case_company_code_query():
    code = _first_pwa_enabled_tenant()
    if not code:
        pytest.skip("No opted-in tenant in apikey.json (pre-Task-15 rollout)")
    resp = _manifest_snake_case(code, IPHONE_UA)
    assert resp.status_code == 200


def test_manifest_pwa_on_desktop_returns_404():
    code = _first_pwa_enabled_tenant()
    if not code:
        pytest.skip("No opted-in tenant in apikey.json (pre-Task-15 rollout)")
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_mobile_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        pytest.skip("No opted-out tenant in apikey.json")
    resp = _manifest(code, IPHONE_UA)
    assert resp.status_code == 404


def test_manifest_pwa_off_desktop_returns_404():
    code = _first_pwa_disabled_tenant()
    if not code:
        pytest.skip("No opted-out tenant in apikey.json")
    resp = _manifest(code, DESKTOP_UA)
    assert resp.status_code == 404


def test_manifest_anonymous_returns_404():
    """No companyCode/mode + no session → 404 (no neutral install surface)."""
    client = TestClient(app)
    resp = client.get("/manifest.json", headers={"User-Agent": IPHONE_UA})
    assert resp.status_code == 404


def _pwa_config(company_code: str, skin_name: str, color: str = "") -> CompanyConfig:
    return CompanyConfig(
        company_id=company_code,
        logo="logo.png",
        tourcube_online=True,
        skin_name=skin_name,
        test_api_key="test-key",
        test_url="https://test.example.com",
        production_api_key="production-key",
        production_url="https://production.example.com",
        api_url="https://test.example.com",
        api_key="test-key",
        pwa_enabled=True,
        pwa_theme_color=color,
    )


@pytest.mark.parametrize(
    ("company_code", "skin_name", "configured_color", "expected_color"),
    [
        ("WT", "theme-wt-blue", "", "#0F4374"),
        ("MTS", "theme-blue", "", "#2c3782"),
        ("THIRD", "tenant-custom", "#123456", "#123456"),
        ("UNKNOWN", "not-a-real-skin", "", DEFAULT_PWA_THEME_COLOR),
    ],
)
def test_manifest_theme_color_is_tenant_aware_and_unknown_skin_is_neutral(
    monkeypatch,
    company_code,
    skin_name,
    configured_color,
    expected_color,
):
    config = _pwa_config(company_code, skin_name, configured_color)
    monkeypatch.setattr(
        type(settings),
        "get_company_config",
        lambda _self, *_args: config,
    )

    response = _manifest(company_code, IPHONE_UA)

    assert response.status_code == 200
    assert response.json()["theme_color"] == expected_color
