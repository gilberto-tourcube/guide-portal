"""apikey.json contract (#160).

Every tenant entry must declare ``PWAEnabled`` and
``OfflineDocumentsEnabled`` as booleans. The tracked example template
(``config/apikey.json.example``) is the schema source of truth — it
must always satisfy the contract because CI runs against it. The live
``config/apikey.json`` is gitignored; we check it opportunistically
when present (developer workstations, staging deploys) so a missing
field there is caught locally before reaching production.
"""

import json
from pathlib import Path

import pytest

from app.config import Settings


def _assert_contract(tenants: list) -> None:
    assert tenants, "apikey config has no tenants"
    for entry in tenants:
        cid = entry.get("CompanyID", "<no id>")
        assert "PWAEnabled" in entry, f"{cid} missing PWAEnabled"
        assert "OfflineDocumentsEnabled" in entry, f"{cid} missing OfflineDocumentsEnabled"
        assert isinstance(entry["PWAEnabled"], bool), f"{cid} PWAEnabled not bool"
        assert isinstance(entry["OfflineDocumentsEnabled"], bool), f"{cid} OfflineDocumentsEnabled not bool"


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


def test_integrity_and_inca_brand_assets_are_packaged_and_visually_distinct():
    """Every configured logo and skin must ship in the deployment artifact."""
    assets = {
        "INCA": (
            Path("static/images/inca-logo.svg"),
            Path("static/css/skins/theme-inca.css"),
        ),
        "IG": (
            Path("static/images/ig-logo.png"),
            Path("static/css/skins/theme-ig.css"),
        ),
    }

    for logo, skin in assets.values():
        assert logo.is_file(), f"missing branded logo: {logo}"
        assert skin.is_file(), f"missing branded skin: {skin}"
        assert logo.stat().st_size > 0
        assert skin.stat().st_size > 0

    assert assets["INCA"][0].read_bytes() != assets["IG"][0].read_bytes()
    assert assets["INCA"][1].read_bytes() != assets["IG"][1].read_bytes()
