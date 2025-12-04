import pytest

from app.config import InvalidCompanyCodeError, Settings


def test_get_company_config_switches_mode_correctly():
    settings = Settings(secret_key="dummy-secret")

    test_config = settings.get_company_config("WTGUIDE", mode="Test")
    assert test_config.api_url == test_config.test_url
    assert test_config.api_key == test_config.test_api_key

    prod_config = settings.get_company_config("WTGUIDE", mode="Production")
    assert prod_config.api_url == prod_config.production_url
    assert prod_config.api_key == prod_config.production_api_key


def test_get_company_config_invalid_company_code():
    settings = Settings(secret_key="dummy-secret")
    with pytest.raises(InvalidCompanyCodeError):
        settings.get_company_config("UNKNOWN_CODE", mode="Test")


def test_resolve_company_and_mode_precedence():
    settings = Settings(secret_key="dummy-secret", company_code="DEFAULT_CO", mode="Test")
    settings._domain_map = {"portal.example": ("MAPPED_CO", "Production")}

    assert settings.resolve_company_and_mode(
        company_code="EXPLICIT_CO",
        mode="Production",
        host="portal.example"
    ) == ("EXPLICIT_CO", "Production")

    assert settings.resolve_company_and_mode(host="portal.example") == ("MAPPED_CO", "Production")
    assert settings.resolve_company_and_mode(host="unknown.example") == ("DEFAULT_CO", "Test")


def test_normalize_host_strips_port_and_lowercases():
    assert Settings._normalize_host("Example.COM:8080") == "example.com"
    assert Settings._normalize_host(None) is None
