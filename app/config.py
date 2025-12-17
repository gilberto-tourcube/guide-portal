"""Application configuration using Pydantic Settings"""

import json
from pathlib import Path
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from typing import Optional, Dict, List


class InvalidCompanyCodeError(Exception):
    """Raised when company code is not found in configuration"""
    pass


class CompanyConfig(BaseModel):
    """Company-specific configuration from apikey.json"""
    company_id: str
    logo: str
    tourcube_online: bool
    skin_name: str
    test_api_key: str
    test_url: str
    production_api_key: str
    production_url: str
    test_domains: List[str] = []
    production_domains: List[str] = []

    # Active configuration based on mode
    api_url: str
    api_key: str


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # API Configuration (kept for backward compatibility)
    api_base_url: str = "https://api.tourcube.com"
    api_key: str = "default_key"
    api_timeout: int = 30

    # Application Settings
    app_name: str = "Tourcube Guide Portal"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False

    # Session Configuration
    secret_key: str
    session_cookie_name: str = "guide_portal_session"
    session_max_age: int = 86400  # 24 hours in seconds

    # Security
    ssl_verify: bool = True  # Enable SSL certificate verification (fixed from legacy)
    allowed_origins: List[str] = []  # CORS allow-list (empty = same-origin only)

    # Sentry Configuration
    sentry_enabled: bool = True  # Enable/disable Sentry error tracking
    sentry_dsn: str = "https://48cf3c57b373f08326c0298b1445933a@o4510551040458752.ingest.us.sentry.io/4510551042490368"
    app_env: str = "test"  # Application environment for Sentry (test/production)

    # Company Configuration - Default/Fallback Values
    # These values are used when:
    # 1. User accesses root (/) without parameters
    # 2. Session doesn't contain company_code/mode during logout
    # Can be overridden via environment variables in .env file
    company_code: str = "WTGUIDE"  # Default company code (fallback)
    mode: str = "Test"  # Default mode: "Test" or "Production" (fallback)
    api_key_json_path: str = "./config/apikey.json"

    # Cache for company configurations
    _company_configs: Optional[Dict[str, CompanyConfig]] = None
    _domain_map: Optional[Dict[str, tuple[str, str]]] = None  # host -> (company_id, mode)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def _load_company_configs(self) -> Dict[str, CompanyConfig]:
        """Load all company configurations from apikey.json"""
        if self._company_configs is not None:
            return self._company_configs

        api_key_path = Path(self.api_key_json_path)

        if not api_key_path.exists():
            raise FileNotFoundError(
                f"API key configuration file not found: {self.api_key_json_path}"
            )

        with open(api_key_path, 'r') as f:
            data = json.load(f)

        configs: Dict[str, CompanyConfig] = {}
        domain_map: Dict[str, tuple[str, str]] = {}
        for company in data.get('TourcubeAPIKey', []):
            company_id = company.get('CompanyID')
            if not company_id:
                continue  # Skip entries without CompanyID

            # Determine skin name from SkinName or HTMLHeader
            skin_name = company.get('SkinName', '')
            if not skin_name:
                # Extract theme from HTMLHeader if SkinName is empty
                html_header = company.get('HTMLHeader', '')
                if 'red' in html_header.lower():
                    skin_name = 'theme-red'
                elif 'egyptian' in html_header.lower():
                    skin_name = 'theme-egyptian'
                elif 'green' in html_header.lower():
                    skin_name = 'theme-green'
                elif 'purple' in html_header.lower():
                    skin_name = 'theme-purple'
                elif 'blue' in html_header.lower():
                    skin_name = 'theme-bluelite'
                else:
                    skin_name = 'theme-bluelite'  # Default theme

            company_config = CompanyConfig(
                company_id=company_id,
                logo=company.get('Logo', 'logo.png'),
                tourcube_online=company.get('TourcubeOnline', True),
                skin_name=skin_name,
                test_api_key=company.get('Test', ''),
                test_url=company.get('TestURL', ''),
                production_api_key=company.get('Production', ''),
                production_url=company.get('ProductionURL', ''),
                test_domains=company.get('TestDomains', []),
                production_domains=company.get('ProductionDomains', []),
                # Initialize with Test credentials by default
                api_url=company.get('TestURL', ''),
                api_key=company.get('Test', '')
            )
            configs[company_id] = company_config

            # Map domains to company/mode for lookup by host header
            for domain in company_config.test_domains:
                norm = self._normalize_host(domain)
                if norm:
                    domain_map[norm] = (company_id, "Test")
            for domain in company_config.production_domains:
                norm = self._normalize_host(domain)
                if norm:
                    domain_map[norm] = (company_id, "Production")

        self._company_configs = configs
        self._domain_map = domain_map
        return configs

    def get_company_config(self, company_code: str, mode: Optional[str] = None) -> CompanyConfig:
        """
        Get company configuration by company code and mode

        Args:
            company_code: Company identifier (e.g., "WTGUIDE")
            mode: "Test" or "Production" (defaults to settings.mode)

        Returns:
            CompanyConfig object with all company settings and active API credentials

        Raises:
            ValueError: If company code is not found in apikey.json
        """
        configs = self._load_company_configs()

        if company_code not in configs:
            raise InvalidCompanyCodeError("Invalid company code")

        config = configs[company_code]
        mode = mode or self.mode

        # Set active API credentials based on mode
        if mode == "Production":
            config.api_url = config.production_url
            config.api_key = config.production_api_key
        else:
            config.api_url = config.test_url
            config.api_key = config.test_api_key

        return config

    def resolve_company_and_mode(
        self,
        company_code: Optional[str] = None,
        mode: Optional[str] = None,
        host: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Resolve company_code and mode using precedence:
        1. Explicit parameters if provided
        2. Domain mapping (host header)
        3. Defaults from settings
        """
        # Explicit values win
        if company_code and mode:
            return company_code, mode

        # Try host mapping
        norm_host = self._normalize_host(host)
        if norm_host and self._domain_map and norm_host in self._domain_map:
            mapped_company, mapped_mode = self._domain_map[norm_host]
            return mapped_company, mapped_mode

        # Fall back to defaults
        return company_code or self.company_code, mode or self.mode

    @staticmethod
    def _normalize_host(host: Optional[str]) -> Optional[str]:
        """Normalize host by lowercasing and stripping port."""
        if not host:
            return None
        host = host.strip().lower()
        if ':' in host:
            host = host.split(':', 1)[0]
        return host

    def get_api_credentials(
        self,
        company_code: Optional[str] = None,
        mode: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Get API URL and API key for a specific company and mode

        Args:
            company_code: Company identifier (defaults to settings.company_code)
            mode: "Test" or "Production" (defaults to settings.mode)

        Returns:
            Tuple of (api_url, api_key)
        """
        company_code = company_code or self.company_code
        mode = mode or self.mode

        config = self.get_company_config(company_code)

        if mode == "Production":
            return config.production_url, config.production_api_key
        else:
            return config.test_url, config.test_api_key


# Global settings instance
settings = Settings()
