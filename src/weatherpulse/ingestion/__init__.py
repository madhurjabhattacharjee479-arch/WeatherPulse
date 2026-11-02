"""Weather provider ingestion clients."""

from weatherpulse.ingestion.exceptions import (
    AuthenticationError,
    CityNotFoundError,
    InvalidRequestError,
    RateLimitError,
    WeatherAPIError,
    WeatherAPIResponseError,
    WeatherAPIRetryExhaustedError,
    WeatherAPIServerError,
    WeatherPulseError,
)
from weatherpulse.ingestion.openweather_client import OpenWeatherClient
from weatherpulse.ingestion.schemas import (
    CurrentWeatherResult,
    WeatherConditionInfo,
    WeatherObservationData,
    WeatherRequestMetadata,
)

__all__ = [
    "AuthenticationError",
    "CityNotFoundError",
    "CurrentWeatherResult",
    "InvalidRequestError",
    "OpenWeatherClient",
    "RateLimitError",
    "WeatherAPIError",
    "WeatherAPIResponseError",
    "WeatherAPIRetryExhaustedError",
    "WeatherAPIServerError",
    "WeatherConditionInfo",
    "WeatherObservationData",
    "WeatherPulseError",
    "WeatherRequestMetadata",
]
