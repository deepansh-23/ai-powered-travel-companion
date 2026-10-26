"""Configuration management for the AI Powered Travel Companion backend.
Loads configuration from environment variables with safe defaults.
Never contains hardcoded secrets or API keys.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from pathlib import Path


class Settings(BaseSettings):
    # App Information
    APP_NAME: str = "AI Powered Travel Companion"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:3000",
    ]

    # Operation Mode
    # True  = use mock JSON, no external API calls required
    # False = use real Geoapify + Gemini APIs; never silently fall back to mock data
    MOCK_MODE: bool = True

    # Website validation
    VERIFY_WEBSITES: bool = False
    WEBSITE_CHECK_TIMEOUT_SECONDS: float = 3.0

    # Routing
    ROUTING_PROVIDER: str = "osrm"
    ROUTING_BASE_URL: str = "https://router.project-osrm.org"
    ROUTING_TIMEOUT_SECONDS: float = 5.0

    # ------------------------------------------------------------------
    # External API Keys
    GEOAPIFY_API_KEY: Optional[str] = None   # for geocoding + places
    GEMINI_API_KEY: Optional[str] = None     # for AI itinerary / area guide
    SERPAPI_API_KEY: Optional[str] = None    # for Google Flights & Google Hotels
    SERP_API_KEY2: Optional[str] = None      # backup SerpApi key, used automatically when the first is out of searches
    RAILRADAR_API_KEY: Optional[str] = None  # for RailRadar train searches
    RECAPTCHA_SITE_KEY: Optional[str] = None # public site key for frontend reCAPTCHA
    RECAPTCHA_SECRET_KEY: Optional[str] = None # private secret key for server verification
    # Which human-verification provider the two keys above belong to:
    #   "recaptcha"  -> Google reCAPTCHA v2 checkbox (siteverify)
    #   "turnstile"  -> Cloudflare Turnstile (same site key + secret key idea)
    CAPTCHA_PROVIDER: str = "recaptcha"
    CAPTCHA_SESSION_HOURS: int = 12

    # ------------------------------------------------------------------
    # PostgreSQL (Aiven) for user accounts, sessions, history and reviews.
    # Leave DB_HOST empty to run without accounts (public features still work).
    DB_HOST: Optional[str] = None
    DB_PORT: int = 5432
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_SSL_CA: str = "ca.pem"          # Aiven CA certificate (relative to the project root)
    DATABASE_URL: Optional[str] = None  # full SQLAlchemy URL override (used by tests)

    # Login sessions
    AUTH_COOKIE_NAME: str = "slg_session"
    AUTH_SESSION_DAYS: int = 14
    AUTH_MAX_FAILED_ATTEMPTS: int = 5
    AUTH_LOCKOUT_MINUTES: int = 15

    # Guest sessions (use the planner without an account; nothing is saved to a profile)
    GUEST_COOKIE_NAME: str = "slg_guest"
    GUEST_SESSION_HOURS: int = 24
    GUEST_MAX_STARTS_PER_HOUR_PER_IP: int = 30
    # Secret used to sign guest cookies. If empty, a random one is made at start-up
    # (guests then simply start a new guest session after a server restart).
    AUTH_SECRET: Optional[str] = None

    # Legacy aliases kept for backward compatibility with old .env files;
    # they are ignored in production — only the canonical names above matter.
    AI_API_KEY: Optional[str] = None         # not used; kept so old .env files don't crash
    PLACES_API_KEY: Optional[str] = None     # not used; kept so old .env files don't crash
    PLACES_PROVIDER: str = "geoapify"
    SEARCH_API_KEY: Optional[str] = None
    GEOCODING_API_KEY: Optional[str] = None
    AI_MODEL: str = "gemini-3.5-flash"

    # Base Paths
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    DATA_MOCK_DIR: Path = PROJECT_ROOT / "data" / "mock"
    FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"

    @field_validator(
        "GEOAPIFY_API_KEY",
        "GEMINI_API_KEY",
        "SERPAPI_API_KEY",
        "SERP_API_KEY2",
        "RAILRADAR_API_KEY",
        "RECAPTCHA_SITE_KEY",
        "RECAPTCHA_SECRET_KEY",
        "DB_HOST",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "DATABASE_URL",
        "AUTH_SECRET",
        mode="before"
    )
    @classmethod
    def sanitize_api_keys(cls, v):
        if isinstance(v, str):
            v = v.strip().strip("'\"")
            return v if v else None
        return v

    @field_validator("CAPTCHA_PROVIDER", mode="before")
    @classmethod
    def sanitize_captcha_provider(cls, v):
        clean = (v or "recaptcha").strip().strip("'\"").lower() if isinstance(v, str) else "recaptcha"
        return clean if clean in ("recaptcha", "turnstile") else "recaptcha"

    @field_validator("AI_MODEL", mode="before")
    @classmethod
    def sanitize_ai_model(cls, v):
        if isinstance(v, str):
            v = v.strip().strip("'\"")
            # Strip models/ prefix if present
            if v.startswith("models/"):
                v = v[len("models/"):]
            return v if v else "gemini-3.5-flash"
        return v or "gemini-3.5-flash"

    @field_validator("MOCK_MODE", mode="before")
    @classmethod
    def sanitize_mock_mode(cls, v):
        if isinstance(v, str):
            clean = v.strip().strip("'\"").lower()
            if clean in ("false", "0", "no", "off"):
                return False
            if clean in ("true", "1", "yes", "on"):
                return True
        return v

    class Config:
        # Always the project-root .env, whatever folder the server is started from
        env_file = str(Path(__file__).resolve().parent.parent.parent / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
