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
