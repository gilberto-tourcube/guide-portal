"""Tests for the two new PWA-related fields on CompanyConfig (#160)."""

from app.config import CompanyConfig, Settings


def _minimal_config(**overrides) -> CompanyConfig:
    base = dict(
        company_id="ACME",
        logo="logo.png",
        tourcube_online=True,
        skin_name="theme-bluelite",
        test_api_key="t-key",
        test_url="https://test.example.com",
        production_api_key="p-key",
        production_url="https://prod.example.com",
        api_url="https://test.example.com",
        api_key="t-key",
    )
    base.update(overrides)
    return CompanyConfig(**base)


def test_company_config_defaults_pwa_flags_false():
    cfg = _minimal_config()
    assert cfg.pwa_enabled is False
    assert cfg.offline_documents_enabled is False


def test_company_config_accepts_pwa_flags_true():
    cfg = _minimal_config(pwa_enabled=True, offline_documents_enabled=True)
    assert cfg.pwa_enabled is True
    assert cfg.offline_documents_enabled is True


def test_load_company_configs_reads_pwa_flags(tmp_path, monkeypatch):
    fixture = tmp_path / "apikey.json"
    fixture.write_text("""
        {
            "TourcubeAPIKey": [
                {
                    "CompanyID": "ALPHA",
                    "Test": "k1",
                    "Production": "k2",
                    "TestURL": "https://t.example.com",
                    "ProductionURL": "https://p.example.com",
                    "PWAEnabled": true,
                    "OfflineDocumentsEnabled": true,
                    "SkinName": "theme-bluelite"
                },
                {
                    "CompanyID": "BETA",
                    "Test": "k1",
                    "Production": "k2",
                    "TestURL": "https://t.example.com",
                    "ProductionURL": "https://p.example.com",
                    "SkinName": "theme-bluelite"
                }
            ]
        }
    """)
    settings = Settings(secret_key="test", api_key_json_path=str(fixture))
    configs = settings._load_company_configs()
    assert configs["ALPHA"].pwa_enabled is True
    assert configs["ALPHA"].offline_documents_enabled is True
    assert configs["BETA"].pwa_enabled is False
    assert configs["BETA"].offline_documents_enabled is False
