"""
Lumen Configuration
Loaded from environment variables via pydantic-settings.
All values have sensible defaults for local development.
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Application
    app_name: str = "Lumen"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://lumen:lumen@localhost:5432/lumen"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_64_CHAR_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days

    # AI APIs
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None  # Used for Gemini + all Google AI APIs
    ai_enabled: bool = True
    ai_timeout_seconds: int = 30

    # Firebase Admin SDK
    firebase_credentials_path: Optional[str] = None  # Path to serviceAccount.json
    fcm_enabled: bool = False

    # Media
    media_path: str = "./media"
    max_photo_size_mb: int = 10
    max_video_size_mb: int = 50
    max_video_duration_seconds: int = 30

    # Rate Limiting
    rate_limit_anonymous_per_hour: int = 10
    rate_limit_user_per_hour: int = 50

    # Frontend
    frontend_url: str = "http://localhost:5173"

    # CORS — comma-separated list of allowed origins.
    # Override in production: CORS_ORIGINS=https://yourapp.com,https://admin.yourapp.com
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        """Returns the parsed list of allowed CORS origins."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Notifications
    push_vapid_private_key: Optional[str] = None
    push_vapid_public_key: Optional[str] = None
    push_vapid_email: str = "admin@lumen.civic"

    # Geo
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    geocoding_user_agent: str = "lumen-civic-app/1.0"

    # Feature Flags
    predictive_enabled: bool = True
    gamification_enabled: bool = True
    emergency_alerts_enabled: bool = True

    # Gamification thresholds
    dispute_reopen_threshold: int = 3
    hard_verification_radius_meters: float = 100.0

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
