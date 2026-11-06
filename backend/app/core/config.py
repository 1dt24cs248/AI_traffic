"""
Centralized application settings.
Reads from environment variables / .env — never hardcode secrets here.
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # External routing service — override in .env for self-hosted OSRM
    OSRM_BASE_URL: str = "https://router.project-osrm.org"

    # Nominatim User-Agent (OSM policy: identify yourself)
    GEOCODING_USER_AGENT: str = (
        "AI-Traffic-Flow-Predictor/1.0 "
        "(college student project; contact via GitHub)"
    )

    # Open-Meteo base URL (free, no API key needed)
    WEATHER_BASE_URL: str = "https://api.open-meteo.com/v1"

    # Optional TomTom Traffic Flow API key; used only by the backend.
    TOMTOM_API_KEY: str | None = None
    # Number of evenly spaced route points checked for current flow (hard capped at six).
    TOMTOM_ROUTE_SAMPLE_COUNT: int = Field(default=5, ge=2, le=6)
    # Optional scheduled traffic collection; disabled unless explicitly enabled.
    TOMTOM_COLLECTOR_ENABLED: bool = False
    TOMTOM_COLLECTOR_INTERVAL_SECONDS: int = Field(default=900, ge=300, le=86400)


settings = Settings()
