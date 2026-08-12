"""apikey.json contract (#160).

Every tenant entry must declare ``PWAEnabled`` and
``OfflineDocumentsEnabled`` as booleans. The tracked example template
(``config/apikey.json.example``) is the schema source of truth — it
must always satisfy the contract because CI runs against it. The live
``config/apikey.json`` is gitignored; we check it opportunistically
when present (developer workstations, staging deploys) so a missing
field there is caught locally before reaching production.
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, UnavailableCompanyModeError
from app.main import app


SHARED_TENANTS = {
    "SLV": ("slv-logo.png", "theme-blue"),
    "ARN": ("arn-logo.png", "theme-blue"),
    "EXC": ("exc-logo.svg", "theme-excursionist"),
    "BJ": ("bj-logo.jpg", "theme-blue"),
    "CTJ": ("ctj-logo.jpg", "theme-blue"),
}

CANONICAL_GUEST_ASSET_HASHES = {
    "static/css/skins/theme-excursionist.css": (
        "a63e130806207d412edb81832aac249681bdb0d0bdd2dd1f0b0099e068ed68c0"
    ),
    "static/images/slv-logo.png": (
        "ac6fe8045608df08454948e4e0e8c2ba7763cc47a52f245180d8bb80a4460415"
    ),
    "static/images/arn-logo.png": (
        "26ee955720ceb2b0097b9e5f30b541ceb03891a03fc9df1da516ad4f1342c0cb"
    ),
    "static/images/exc-logo.svg": (
        "b7927fcc5c8605c0d43f0f372c6a50c7c3bef321d49968534582db46c1b7ba3e"
    ),
    "static/images/bj-logo.jpg": (
        "3d49b1354d06566368b7e5cc5fd7dacdb2946cddec69edcdf5a55562fb266e68"
    ),
    "static/images/ctj-logo.jpg": (
        "3ccb49e893666c99cbe76a7d44c2ca25ff7b1566a782aadf30c42cef59a68df8"
    ),
}


def _assert_contract(tenants: list) -> None:
    assert tenants, "apikey config has no tenants"
    for entry in tenants:
        cid = entry.get("CompanyID", "<no id>")
        assert "PWAEnabled" in entry, f"{cid} missing PWAEnabled"
        assert "OfflineDocumentsEnabled" in entry, f"{cid} missing OfflineDocumentsEnabled"
        assert isinstance(entry["PWAEnabled"], bool), f"{cid} PWAEnabled not bool"
        assert isinstance(entry["OfflineDocumentsEnabled"], bool), f"{cid} OfflineDocumentsEnabled not bool"
        if "PWAThemeColor" in entry:
            color = entry["PWAThemeColor"]
            assert isinstance(color, str), f"{cid} PWAThemeColor not string"
            assert len(color) == 7 and color.startswith("#"), (
                f"{cid} PWAThemeColor must use #RRGGBB"
            )
            int(color[1:], 16)


def test_apikey_json_example_carries_pwa_schema():
    """The tracked template must always satisfy the schema."""
    path = Path("config/apikey.json.example")
    if not path.exists():
        pytest.fail("config/apikey.json.example is missing — it's the tracked schema reference")
    data = json.loads(path.read_text())
    _assert_contract(data["TourcubeAPIKey"])


def test_apikey_json_live_carries_pwa_schema_when_present():
    """When a live apikey.json exists locally, it must also satisfy the schema."""
    path = Path("config/apikey.json")
    if not path.exists():
        pytest.skip("config/apikey.json not present locally — CI or fresh env")
    data = json.loads(path.read_text())
    _assert_contract(data["TourcubeAPIKey"])


def test_integrity_and_inca_share_backend_credentials_but_keep_distinct_branding():
    """Integrity is an INCA brand with its own company code and visual identity."""
    settings = Settings(
        secret_key="test-secret",
        api_key_json_path="config/apikey.json.example",
    )

    inca = settings.get_company_config("INCA", "Production")
    integrity = settings.get_company_config("IG", "Production")

    assert inca.company_id == "INCA"
    assert integrity.company_id == "IG"
    assert inca.api_url == integrity.api_url == "https://web2.tourcube.net"
    assert inca.api_key == integrity.api_key
    assert settings.get_api_credentials(
        "INCA", "Test"
    ) == settings.get_api_credentials("IG", "Test")
    assert settings.get_api_credentials(
        "INCA", "Production"
    ) == settings.get_api_credentials("IG", "Production")
    assert (inca.logo, inca.skin_name) == ("inca-logo.svg", "theme-inca")
    assert (integrity.logo, integrity.skin_name) == ("ig-logo.png", "theme-ig")
    assert (inca.logo, inca.skin_name) != (integrity.logo, integrity.skin_name)


def _assert_mts_test_isolated_from_production(path: str) -> None:
    """MTS Test must use the dedicated test backend and API key."""
    settings = Settings(
        secret_key="test-secret",
        api_key_json_path=path,
    )

    mts_test_url, mts_test_key = settings.get_api_credentials("MTS", "Test")
    mts_production_url, mts_production_key = settings.get_api_credentials(
        "MTS", "Production"
    )
    mts_branding = settings.get_company_config("MTS", "Test")

    assert mts_test_url == "https://test-2.tourcube.net"
    assert mts_production_url == "https://web2.tourcube.net"
    assert mts_test_key != mts_production_key
    assert (mts_branding.logo, mts_branding.skin_name) == (
        "mts-logo.jpg",
        "theme-mts",
    )


def test_mts_example_isolates_test_from_production():
    _assert_mts_test_isolated_from_production("config/apikey.json.example")


def test_mts_live_config_isolates_test_from_production_when_present():
    path = Path("config/apikey.json")
    if not path.exists():
        pytest.skip("config/apikey.json not present locally — CI or fresh env")
    _assert_mts_test_isolated_from_production(str(path))


def test_shared_tenant_example_has_environment_and_branding_contract():
    """Shared Guest tenants keep their canonical Guide routing and identity."""
    settings = Settings(
        secret_key="test-secret",
        api_key_json_path="config/apikey.json.example",
    )

    assert set(settings._load_company_configs()) == {
        "WT",
        "MTS",
        "INCA",
        "IG",
        *SHARED_TENANTS,
    }

    for company_code, (logo, skin) in SHARED_TENANTS.items():
        test = settings.get_company_config(company_code, "Test")
        assert settings.resolve_company_and_mode(
            company_code=company_code,
            mode="Test",
        ) == (company_code, "Test")
        assert settings.get_api_credentials(company_code, "Test")[0] == (
            "https://test-2.tourcube.net"
        )
        test_url, test_key = settings.get_api_credentials(company_code, "Test")
        assert test_url == "https://test-2.tourcube.net"
        assert test_key
        with pytest.raises(UnavailableCompanyModeError):
            settings.get_api_credentials(company_code, "Production")
        assert (test.logo, test.skin_name) == (logo, skin)
        assert test.pwa_enabled is False
        assert test.offline_documents_enabled is True


def test_shared_tenant_live_config_is_test_only_when_present():
    """The deploy candidate must fail closed for the five Production modes."""
    path = Path("config/apikey.json")
    if not path.exists():
        pytest.skip("config/apikey.json not present locally — CI or fresh env")

    settings = Settings(secret_key="test-secret", api_key_json_path=str(path))
    for company_code in SHARED_TENANTS:
        test_url, test_key = settings.get_api_credentials(company_code, "Test")
        assert test_url == "https://test-2.tourcube.net"
        assert test_key
        with pytest.raises(UnavailableCompanyModeError):
            settings.get_api_credentials(company_code, "Production")


def test_shared_tenant_login_pages_reference_their_brand_assets():
    client = TestClient(app)

    for company_code, (logo, skin) in SHARED_TENANTS.items():
        response = client.get(
            f"/auth/login?company_code={company_code}&mode=Test"
        )
        assert response.status_code == 200
        assert f"/static/images/{logo}" in response.text
        assert f"/static/css/skins/{skin}.css" in response.text


def test_shared_tenant_assets_match_canonical_guest_sources():
    for relative_path, expected_hash in CANONICAL_GUEST_ASSET_HASHES.items():
        path = Path(relative_path)
        assert path.is_file(), f"missing canonical Guest asset: {path}"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash


def test_configured_brand_assets_are_packaged_and_visually_distinct():
    """Every configured logo and skin must ship in the deployment artifact."""
    assets = {
        "WT": (
            Path("static/images/wt-horizontal-logo-black-type.png"),
            Path("static/css/skins/theme-wt-blue.css"),
        ),
        "MTS": (
            Path("static/images/mts-logo.jpg"),
            Path("static/css/skins/theme-mts.css"),
        ),
        "INCA": (
            Path("static/images/inca-logo.svg"),
            Path("static/css/skins/theme-inca.css"),
        ),
        "IG": (
            Path("static/images/ig-logo.png"),
            Path("static/css/skins/theme-ig.css"),
        ),
        **{
            company_code: (
                Path("static/images") / logo,
                Path("static/css/skins") / f"{skin}.css",
            )
            for company_code, (logo, skin) in SHARED_TENANTS.items()
        },
    }

    for logo, skin in assets.values():
        assert logo.is_file(), f"missing branded logo: {logo}"
        assert skin.is_file(), f"missing branded skin: {skin}"
        assert logo.stat().st_size > 0
        assert skin.stat().st_size > 0

    client = TestClient(app)
    for logo, skin in assets.values():
        assert client.get(f"/static/images/{logo.name}").status_code == 200
        assert client.get(f"/static/css/skins/{skin.name}").status_code == 200

    assert assets["INCA"][0].read_bytes() != assets["IG"][0].read_bytes()
    assert assets["INCA"][1].read_bytes() != assets["IG"][1].read_bytes()
