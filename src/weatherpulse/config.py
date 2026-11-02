import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppSettings:
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/weatherpulse.db"


@dataclass(frozen=True)
class OpenWeatherSettings:
    api_key: str
    base_url: str = "https://api.openweathermap.org"
    timeout_seconds: float = 10.0
    max_retries: int = 3
    retry_backoff: float = 2.0


def _read_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _normalize_openweather_base_url(url: str) -> str:
    normalized = url.rstrip("/")
    if normalized.endswith("/data/2.5"):
        normalized = normalized[: -len("/data/2.5")]
    return normalized


def _read_float_env(*names: str, default: float) -> float:
    raw = _read_env(*names)
    if raw is None:
        return default
    return float(raw)


def _read_int_env(*names: str, default: int) -> int:
    raw = _read_env(*names)
    if raw is None:
        return default
    return int(raw)


def load_settings() -> AppSettings:
    """Load foundation settings from environment variables."""
    return AppSettings(
        environment=os.getenv("WEATHERPULSE_ENV", AppSettings.environment),
        log_level=os.getenv("WEATHERPULSE_LOG_LEVEL", AppSettings.log_level),
        database_url=(
            os.getenv("DATABASE_URL")
            or os.getenv("WEATHERPULSE_DATABASE_URL")
            or AppSettings.database_url
        ),
    )


def load_etl_cities() -> list[str]:
    """Load comma-separated OpenWeather city queries for ETL processing."""
    raw = _read_env("WEATHERPULSE_ETL_CITIES")
    if raw is None:
        return []
    return [city.strip() for city in raw.split(",") if city.strip()]


def load_openweather_settings() -> OpenWeatherSettings:
    """Load OpenWeatherMap client settings from environment variables."""
    api_key = _read_env("OPENWEATHER_API_KEY", "OPENWEATHERMAP_API_KEY") or ""
    base_url = _normalize_openweather_base_url(
        _read_env("OPENWEATHER_BASE_URL", "OPENWEATHERMAP_BASE_URL")
        or OpenWeatherSettings.base_url
    )
    return OpenWeatherSettings(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=_read_float_env(
            "OPENWEATHER_TIMEOUT_SECONDS",
            default=OpenWeatherSettings.timeout_seconds,
        ),
        max_retries=_read_int_env(
            "OPENWEATHER_MAX_RETRIES",
            default=OpenWeatherSettings.max_retries,
        ),
        retry_backoff=_read_float_env(
            "OPENWEATHER_RETRY_BACKOFF",
            default=OpenWeatherSettings.retry_backoff,
        ),
    )
