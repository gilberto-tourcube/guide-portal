import pytest
from pydantic import ValidationError

from app.config import InvalidCompanyCodeError, Settings


def _settings(**overrides) -> Settings:
    return Settings(
        secret_key="dummy-secret",
        api_key_json_path="config/apikey.json.example",
        **overrides,
    )


def test_get_company_config_switches_mode_correctly():
    settings = _settings()

    test_config = settings.get_company_config("WT", mode="Test")
    assert test_config.api_url == test_config.test_url
    assert test_config.api_key == test_config.test_api_key

    prod_config = settings.get_company_config("WT", mode="Production")
    assert prod_config.api_url == prod_config.production_url
    assert prod_config.api_key == prod_config.production_api_key


def test_get_company_config_invalid_company_code():
    settings = _settings()
    with pytest.raises(InvalidCompanyCodeError):
        settings.get_company_config("UNKNOWN_CODE", mode="Test")


def test_resolve_company_and_mode_precedence():
    """Explicit args win, then host mapping, then (None, None).

    There is intentionally NO default-tenant fallback (#148). A request with
    no explicit context and no host mapping must surface as unresolved so
    callers render a neutral / 400 response instead of impersonating some
    other tenant.
    """
    settings = _settings()
    settings._domain_map = {"portal.example": ("MAPPED_CO", "Production")}

    assert settings.resolve_company_and_mode(
        company_code="EXPLICIT_CO",
        mode="Production",
        host="portal.example"
    ) == ("EXPLICIT_CO", "Production")

    assert settings.resolve_company_and_mode(host="portal.example") == ("MAPPED_CO", "Production")
    # No host mapping and no explicit args resolves to (None, None).
    assert settings.resolve_company_and_mode(host="unknown.example") == (None, None)
    assert settings.resolve_company_and_mode() == (None, None)


def test_settings_has_no_default_tenant_fields():
    """Regression guard for #148 and its follow-up (ENG-521).

    `company_code` and `mode` were not just left unused on `Settings`, they
    were deleted entirely. `Settings` uses `extra="forbid"` (pydantic-settings
    default), so passing either as a constructor kwarg, the only way a
    default-tenant value could ever have been injected, must be rejected.
    This proves structurally that there is no field left for a default
    tenant to leak through.
    """
    with pytest.raises(ValidationError):
        _settings(company_code="LEAKY_DEFAULT", mode="Test")

    with pytest.raises(ValidationError):
        _settings(mode="Test")

    with pytest.raises(ValidationError):
        _settings(company_code="LEAKY_DEFAULT")


def test_resolve_company_and_mode_inherits_mode_from_matching_host():
    """Regression guard for PR #70: an explicit company_code with no mode
    must still inherit the mapped mode when the host maps to the SAME
    tenant (e.g. the guide_hash auto-login entry point, which supplies
    company_code but not mode)."""
    settings = _settings()
    settings._domain_map = {
        "guideportal.tourcube.net": ("WT", "Production"),
    }

    assert settings.resolve_company_and_mode(
        company_code="WT",
        mode=None,
        host="guideportal.tourcube.net",
    ) == ("WT", "Production")


def test_resolve_company_and_mode_does_not_inherit_mode_from_mismatched_host():
    """A host mapped to a DIFFERENT tenant must never supply a mode (or
    tenant identity) for an explicitly requested company code — the
    hardening PR #70 introduced must survive the mode-inheritance fix."""
    settings = _settings()
    settings._domain_map = {
        "mts.guideportal.tourcube.net": ("MTS", "Production"),
    }

    assert settings.resolve_company_and_mode(
        company_code="WT",
        mode=None,
        host="mts.guideportal.tourcube.net",
    ) == ("WT", None)


def test_resolve_company_and_mode_loads_domain_map_lazily(tmp_path):
    """Host-based tenant resolution must work on a cold Settings instance.

    Without this, the first request to a tenant-specific domain could be
    treated as anonymous until another route happened to load apikey.json.
    """
    apikey = tmp_path / "apikey.json"
    apikey.write_text(
        """
        {
          "TourcubeAPIKey": [
            {
              "CompanyID": "HOSTED",
              "Logo": "hosted.png",
              "TourcubeOnline": true,
              "SkinName": "theme-bluelite",
              "Test": "test-key",
              "TestURL": "https://test.example/api",
              "Production": "prod-key",
              "ProductionURL": "https://prod.example/api",
              "TestDomains": ["guide.test.example:443"],
              "ProductionDomains": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    settings = Settings(
        secret_key="dummy-secret",
        api_key_json_path=str(apikey),
    )
    assert settings._domain_map is None

    assert settings.resolve_company_and_mode(host="guide.test.example") == (
        "HOSTED",
        "Test",
    )


def test_get_company_config_requires_mode():
    """#148: `get_company_config` must not fall back to a default mode."""
    settings = _settings()
    with pytest.raises(ValueError, match="mode is required"):
        settings.get_company_config("WT", None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="company_code is required"):
        settings.get_company_config("", "Test")


def test_normalize_host_strips_port_and_lowercases():
    assert Settings._normalize_host("Example.COM:8080") == "example.com"
    assert Settings._normalize_host(None) is None
