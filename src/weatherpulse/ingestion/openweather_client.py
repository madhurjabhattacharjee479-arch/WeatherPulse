"""OpenWeatherMap current weather ingestion client."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

import httpx

from weatherpulse.config import OpenWeatherSettings, load_openweather_settings
from weatherpulse.ingestion.exceptions import (
    AuthenticationError,
    CityNotFoundError,
    InvalidRequestError,
    RateLimitError,
    WeatherAPIError,
    WeatherAPIResponseError,
    WeatherAPIRetryExhaustedError,
    WeatherAPIServerError,
)
from weatherpulse.ingestion.schemas import (
    CurrentWeatherResult,
    WeatherRequestMetadata,
    parse_openweather_response,
)

logger = logging.getLogger(__name__)

CURRENT_WEATHER_PATH = "/data/2.5/weather"


class OpenWeatherClient:
    """HTTP client for OpenWeatherMap current weather ingestion."""

    def __init__(
        self,
        settings: OpenWeatherSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or load_openweather_settings()
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=self._settings.base_url.rstrip("/"),
            timeout=self._settings.timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenWeatherClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    @property
    def endpoint(self) -> str:
        return CURRENT_WEATHER_PATH

    def get_current_weather(self, city: str) -> CurrentWeatherResult:
        """Fetch and validate current weather for a city."""
        if not self._settings.api_key:
            raise AuthenticationError("OpenWeatherMap API key is not configured")

        requested_at = datetime.now(tz=UTC)
        retry_count = 0
        last_error: WeatherAPIError | None = None

        while True:
            attempt_number = retry_count + 1
            try:
                return self._execute_request(
                    city=city,
                    requested_at=requested_at,
                    retry_count=retry_count,
                )
            except (RateLimitError, WeatherAPIServerError) as exc:
                last_error = exc
            except httpx.TimeoutException as exc:
                last_error = WeatherAPIRetryExhaustedError(
                    f"OpenWeather request timed out for city '{city}'",
                    metadata=WeatherRequestMetadata(
                        requested_at=requested_at,
                        city=city,
                        endpoint=self.endpoint,
                        success=False,
                        retry_count=retry_count,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
            except httpx.RequestError as exc:
                last_error = WeatherAPIRetryExhaustedError(
                    f"OpenWeather connection failed for city '{city}'",
                    metadata=WeatherRequestMetadata(
                        requested_at=requested_at,
                        city=city,
                        endpoint=self.endpoint,
                        success=False,
                        retry_count=retry_count,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
            except WeatherAPIError:
                raise
            except WeatherAPIResponseError:
                raise

            if retry_count >= self._settings.max_retries:
                break

            delay = _retry_delay_seconds(
                retry_count=retry_count,
                backoff=self._settings.retry_backoff,
                retry_after=(
                    last_error.retry_after_seconds
                    if isinstance(last_error, RateLimitError)
                    else None
                ),
            )
            logger.warning(
                "OpenWeather transient failure for city=%s attempt=%s retry_in=%ss error=%s",
                city,
                attempt_number,
                delay,
                type(last_error).__name__,
            )
            time.sleep(delay)
            retry_count += 1

        assert last_error is not None
        raise WeatherAPIRetryExhaustedError(
            f"OpenWeather request failed after {retry_count} retries for city '{city}'",
            metadata=_with_retry_count(last_error.metadata, retry_count),
        ) from last_error

    def _execute_request(
        self,
        *,
        city: str,
        requested_at: datetime,
        retry_count: int,
    ) -> CurrentWeatherResult:
        params = {
            "q": city,
            "appid": self._settings.api_key,
            "units": "metric",
        }
        started = time.perf_counter()
        response = self._client.get(self.endpoint, params=params)
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        metadata = WeatherRequestMetadata(
            requested_at=requested_at,
            city=city,
            endpoint=self.endpoint,
            http_status=response.status_code,
            response_time_ms=elapsed_ms,
            success=response.is_success,
            retry_count=retry_count,
        )

        logger.info(
            "OpenWeather request city=%s status=%s response_ms=%s retry_count=%s success=%s",
            city,
            response.status_code,
            elapsed_ms,
            retry_count,
            response.is_success,
        )

        if response.status_code == 400:
            raise InvalidRequestError(
                _safe_error_message(response, city),
                metadata=_failure_metadata(metadata, "InvalidRequestError"),
            )
        if response.status_code == 401:
            raise AuthenticationError(
                "OpenWeatherMap rejected the API credentials",
                metadata=_failure_metadata(metadata, "AuthenticationError"),
            )
        if response.status_code == 404:
            raise CityNotFoundError(
                f"City '{city}' was not found by OpenWeatherMap",
                metadata=_failure_metadata(metadata, "CityNotFoundError"),
            )
        if response.status_code == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise RateLimitError(
                "OpenWeatherMap rate limit exceeded",
                metadata=_failure_metadata(metadata, "RateLimitError"),
                retry_after_seconds=retry_after,
            )
        if 500 <= response.status_code <= 599:
            raise WeatherAPIServerError(
                _safe_error_message(response, city),
                metadata=_failure_metadata(metadata, "WeatherAPIServerError"),
            )
        if not response.is_success:
            raise WeatherAPIError(
                _safe_error_message(response, city),
                metadata=_failure_metadata(metadata, "WeatherAPIError"),
            )

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise WeatherAPIResponseError(
                "OpenWeatherMap returned malformed JSON",
                metadata=_failure_metadata(
                    metadata,
                    "WeatherAPIResponseError",
                    error_message=str(exc),
                ),
            ) from exc

        if not isinstance(payload, dict):
            raise WeatherAPIResponseError(
                "OpenWeatherMap returned a non-object JSON payload",
                metadata=_failure_metadata(metadata, "WeatherAPIResponseError"),
            )

        try:
            observation = parse_openweather_response(payload)
        except Exception as exc:
            raise WeatherAPIResponseError(
                f"OpenWeatherMap response validation failed: {exc}",
                metadata=_failure_metadata(
                    metadata,
                    "WeatherAPIResponseError",
                    error_message=str(exc),
                ),
            ) from exc

        return CurrentWeatherResult(
            observation=observation,
            metadata=metadata.model_copy(update={"success": True}),
        )


def _retry_delay_seconds(
    *,
    retry_count: int,
    backoff: float,
    retry_after: float | None = None,
) -> float:
    if retry_after is not None:
        return max(retry_after, 0.0)
    return backoff * (2**retry_count)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _safe_error_message(response: httpx.Response, city: str) -> str:
    message = f"OpenWeatherMap request failed for city '{city}' with status {response.status_code}"
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return message

    if isinstance(payload, dict):
        provider_message = payload.get("message")
        if isinstance(provider_message, str) and provider_message:
            sanitized = _redact_secrets(provider_message)
            return f"{message}: {sanitized}"
    return message


def _redact_secrets(text: str) -> str:
    lowered = text.lower()
    for secret_marker in ("appid=", "api_key=", "apikey="):
        if secret_marker in lowered:
            index = lowered.index(secret_marker)
            return text[:index].rstrip()
    return text


def _failure_metadata(
    metadata: WeatherRequestMetadata,
    error_type: str,
    *,
    error_message: str | None = None,
) -> WeatherRequestMetadata:
    return metadata.model_copy(
        update={
            "success": False,
            "error_type": error_type,
            "error_message": error_message,
        }
    )


def _with_retry_count(
    metadata: WeatherRequestMetadata | None,
    retry_count: int,
) -> WeatherRequestMetadata | None:
    if metadata is None:
        return None
    return metadata.model_copy(update={"retry_count": retry_count})
