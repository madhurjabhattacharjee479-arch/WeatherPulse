"""Domain exceptions for weather provider ingestion."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weatherpulse.ingestion.schemas import WeatherRequestMetadata


class WeatherPulseError(Exception):
    """Base exception for WeatherPulse ingestion errors."""


class WeatherAPIError(WeatherPulseError):
    """Raised when an external weather API request fails."""

    def __init__(
        self,
        message: str,
        *,
        metadata: WeatherRequestMetadata | None = None,
    ) -> None:
        super().__init__(message)
        self.metadata = metadata


class AuthenticationError(WeatherAPIError):
    """Raised when the provider rejects API credentials."""


class InvalidRequestError(WeatherAPIError):
    """Raised when the provider rejects the request parameters."""


class CityNotFoundError(WeatherAPIError):
    """Raised when the requested city cannot be found."""


class RateLimitError(WeatherAPIError):
    """Raised when the provider rate-limits the request."""

    def __init__(
        self,
        message: str,
        *,
        metadata: WeatherRequestMetadata | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, metadata=metadata)
        self.retry_after_seconds = retry_after_seconds


class WeatherAPIServerError(WeatherAPIError):
    """Raised when the provider returns a server-side HTTP error."""


class WeatherAPIRetryExhaustedError(WeatherAPIError):
    """Raised when transient failures exceed the configured retry limit."""


class WeatherAPIResponseError(WeatherPulseError):
    """Raised when a provider response is malformed or fails validation."""

    def __init__(
        self,
        message: str,
        *,
        metadata: WeatherRequestMetadata | None = None,
    ) -> None:
        super().__init__(message)
        self.metadata = metadata
