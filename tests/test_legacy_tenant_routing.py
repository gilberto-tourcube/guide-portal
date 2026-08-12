"""Legacy Guide V7 tenant-routing contract.

The generic Guide hostname accepts legacy ``companyCode`` links as well as
``company_code``.  These tests keep the routing decision separate from any
live authentication attempt.
"""

import pytest

from app.config import (
    InvalidCompanyCodeError,
    Settings,
    settings,
)


GUIDE_TENANTS = ("WT", "MTS", "INCA", "IG", "SLV", "ARN", "EXC", "BJ", "CTJ")
TEST_ONLY_TENANTS = ("SLV", "ARN", "EXC", "BJ", "CTJ")


@pytest.fixture
def example_tenant_config(monkeypatch):
    """Use the tracked, credential-free tenant matrix for HTTP route tests."""
    monkeypatch.setattr(settings, "api_key_json_path", "config/apikey.json.example")
    monkeypatch.setattr(settings, "_company_configs", None)
    monkeypatch.setattr(settings, "_domain_map", None)


def _settings() -> Settings:
    return Settings(
        secret_key="test-secret",
        api_key_json_path="config/apikey.json.example",
    )


@pytest.mark.parametrize("company_code", GUIDE_TENANTS)
def test_all_guide_tenants_accept_case_insensitive_explicit_codes(company_code):
    config = _settings().get_company_config(company_code.lower(), "Test")

    assert config.company_id == company_code


@pytest.mark.asyncio
async def test_camel_case_company_code_wins_over_snake_case_on_generic_hostname(
    secure_client, reset_debug, example_tenant_config
):
    """Keep the existing legacy precedence: companyCode, then company_code."""
    settings.debug = False

    response = await secure_client.get(
        "/?companyCode=ig&company_code=WT&mode=Test",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?company_code=IG&mode=Test"


def test_explicit_unknown_tenant_cannot_fall_back_to_host_mapping():
    configured = _settings()
    configured._domain_map = {"guideportal.tourcube.net": ("WT", "Production")}

    company_code, mode = configured.resolve_company_and_mode(
        company_code="not-a-tenant",
        mode="Test",
        host="guideportal.tourcube.net",
    )

    assert (company_code, mode) == ("NOT-A-TENANT", "Test")
    with pytest.raises(InvalidCompanyCodeError):
        configured.get_company_config(company_code, mode)


@pytest.mark.parametrize("invalid_mode", ("test", "production", "Live", "Production "))
def test_invalid_mode_is_rejected_instead_of_selecting_any_environment(invalid_mode):
    configured = _settings()

    with pytest.raises(ValueError, match="mode must be exactly Test or Production"):
        configured.get_company_config("WT", invalid_mode)


def test_invalid_mode_cannot_override_a_mapped_production_hostname():
    configured = _settings()
    configured._domain_map = {"guideportal.tourcube.net": ("WT", "Production")}

    assert configured.resolve_company_and_mode(
        mode="Live", host="guideportal.tourcube.net"
    ) == (None, None)


@pytest.mark.asyncio
async def test_root_fails_closed_for_invalid_mode(
    secure_client, reset_debug, example_tenant_config
):
    settings.debug = False

    response = await secure_client.get(
        "/?companyCode=WT&mode=Live",
        follow_redirects=False,
        headers={"Accept": "text/html"},
    )

    assert response.status_code == 400
    assert "location" not in {key.lower() for key in response.headers}
    assert "WT" not in response.text


@pytest.mark.parametrize("company_code", TEST_ONLY_TENANTS)
def test_shared_guide_tenant_production_is_unavailable(company_code):
    configured = _settings()

    with pytest.raises(ValueError, match="not configured for Production"):
        configured.get_company_config(company_code, "Production")


def test_integrity_keeps_its_brand_while_using_inca_backend():
    configured = _settings()
    inca = configured.get_company_config("INCA", "Production")
    integrity = configured.get_company_config("ig", "Production")

    assert (integrity.logo, integrity.skin_name) == ("ig-logo.png", "theme-ig")
    assert (integrity.logo, integrity.skin_name) != (inca.logo, inca.skin_name)
    assert (integrity.api_url, integrity.api_key) == (inca.api_url, inca.api_key)


@pytest.mark.asyncio
async def test_guide_hash_with_explicit_company_code_and_no_mode_reaches_guide_home(
    secure_client, reset_debug, example_tenant_config, monkeypatch
):
    """Regression guard for PR #70: explicit companyCode with guideHash and no
    mode, on a Production host mapped to the SAME tenant, must still reach
    the guide-home bypass — not a neutral 400. This is the guides'
    auto-login entry point on the live MTS Production host.

    GuideHashMiddleware (app/main.py) intercepts any request carrying
    guide_hash/guideHash before it reaches a route handler and tries to
    resolve it via the real Tourcube API. Mock that lookup here (as
    tests/test_no_default_tenant_leak.py does for the same middleware) so
    this test exercises resolve_company_and_mode's routing decision instead
    of making a live network call.
    """
    settings.debug = False
    monkeypatch.setattr(
        settings,
        "_domain_map",
        {"mts.guideportal.tourcube.net": ("MTS", "Production")},
    )

    async def fake_get_guide_id_by_hash(*args, **kwargs):
        return 1

    async def fake_get_guide_homepage(*args, **kwargs):
        raise RuntimeError("homepage lookup is best-effort and should be skipped in this test")

    monkeypatch.setattr(
        "app.main.guide_service.get_guide_id_by_hash", fake_get_guide_id_by_hash
    )
    monkeypatch.setattr(
        "app.main.guide_service.get_guide_homepage", fake_get_guide_homepage
    )

    response = await secure_client.get(
        "/?guideHash=ABC123&companyCode=MTS",
        headers={"x-forwarded-host": "mts.guideportal.tourcube.net"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/guide/home?company_code=MTS&mode=Production&guide_hash=ABC123"
    )
