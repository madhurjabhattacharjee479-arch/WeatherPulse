from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from weatherpulse.config import OpenWeatherSettings
from weatherpulse.ingestion.exceptions import (
    AuthenticationError,
    CityNotFoundError,
    InvalidRequestError,
    RateLimitError,
    WeatherAPIResponseError,
    WeatherAPIRetryExhaustedError,
    WeatherAPIServerError,
)
from weatherpulse.ingestion.openweather_client import OpenWeatherClient

TEST_API_KEY = "test-api-key-secret-do-not-log"
OBSERVED_UNIX = 1_605_182_400

VALID_RESPONSE = {
    "coord": {"lon": -0.13, "lat": 51.51},
    "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
    "main": {
        "temp": 15.5,
        "feels_like": 14.2,
        "temp_min": 13.0,
        "temp_max": 17.0,
        "pressure": 1013,
        "humidity": 72,
    },
    "visibility": 10000,
    "wind": {"speed": 3.5, "deg": 180},
    "clouds": {"all": 20},
    "rain": {"1h": 0.5},
    "dt": OBSERVED_UNIX,
    "sys": {"country": "GB"},
    "name": "London",
}


@pytest.fixture
def settings() -> OpenWeatherSettings:
    return OpenWeatherSettings(
        api_key=TEST_API_KEY,
        base_url="https://api.openweathermap.org",
        timeout_seconds=1.0,
        max_retries=2,
        retry_backoff=0.01,
    )


def _build_client(
    settings: OpenWeatherSettings,
    handler,
) -> OpenWeatherClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url=settings.base_url,
        transport=transport,
        timeout=settings.timeout_seconds,
    )
    return OpenWeatherClient(settings, http_client=http_client)


def test_successful_response(settings: OpenWeatherSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/data/2.5/weather"
        assert request.url.params["q"] == "London"
        assert request.url.params["appid"] == TEST_API_KEY
        assert request.url.params["units"] == "metric"
        return httpx.Response(200, json=VALID_RESPONSE)

    client = _build_client(settings, handler)
    result = client.get_current_weather("London")

    assert result.metadata.success is True
    assert result.metadata.http_status == 200
    assert result.metadata.city == "London"
    assert result.metadata.endpoint == "/data/2.5/weather"
    assert result.metadata.retry_count == 0
    assert result.metadata.response_time_ms is not None


def test_valid_response_conversion(settings: OpenWeatherSettings) -> None:
    client = _build_client(settings, lambda _request: httpx.Response(200, json=VALID_RESPONSE))
    result = client.get_current_weather("London")
    observation = result.observation

    assert observation.city_name == "London"
    assert observation.country_code == "GB"
    assert observation.latitude == pytest.approx(51.51)
    assert observation.longitude == pytest.approx(-0.13)
    assert observation.temperature_c == pytest.approx(15.5)
    assert observation.feels_like_c == pytest.approx(14.2)
    assert observation.temp_min_c == pytest.approx(13.0)
    assert observation.temp_max_c == pytest.approx(17.0)
    assert observation.pressure_hpa == 1013
    assert observation.humidity_percent == 72
    assert observation.visibility_m == 10000
    assert observation.wind_speed_mps == pytest.approx(3.5)
    assert observation.wind_direction_deg == 180
    assert observation.cloudiness_percent == 20
    assert observation.rain_1h_mm == pytest.approx(0.5)
    assert observation.snow_1h_mm is None
    assert len(observation.weather_conditions) == 1
    assert observation.weather_conditions[0].main == "Clear"


def test_timezone_aware_observed_at(settings: OpenWeatherSettings) -> None:
    client = _build_client(settings, lambda _request: httpx.Response(200, json=VALID_RESPONSE))
    result = client.get_current_weather("London")

    assert result.observation.observed_at == datetime.fromtimestamp(OBSERVED_UNIX, tz=UTC)
    assert result.observation.observed_at.tzinfo is UTC
    assert result.metadata.requested_at.tzinfo is UTC
    assert result.metadata.requested_at != result.observation.observed_at


def test_optional_rain_and_snow_fields(settings: OpenWeatherSettings) -> None:
    snow_response = {key: value for key, value in VALID_RESPONSE.items() if key != "rain"}
    snow_response["snow"] = {"1h": 1.25}

    client = _build_client(settings, lambda _request: httpx.Response(200, json=snow_response))
    result = client.get_current_weather("London")

    assert result.observation.rain_1h_mm is None
    assert result.observation.snow_1h_mm == pytest.approx(1.25)


def test_missing_required_fields(settings: OpenWeatherSettings) -> None:
    invalid_response = {**VALID_RESPONSE}
    del invalid_response["main"]

    client = _build_client(settings, lambda _request: httpx.Response(200, json=invalid_response))

    with pytest.raises(WeatherAPIResponseError, match="validation failed"):
        client.get_current_weather("London")


def test_malformed_json(settings: OpenWeatherSettings) -> None:
    client = _build_client(
        settings,
        lambda _request: httpx.Response(200, content=b"not-json"),
    )

    with pytest.raises(WeatherAPIResponseError, match="malformed JSON"):
        client.get_current_weather("London")


def test_timeout(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    client = _build_client(settings, handler)

    with pytest.raises(WeatherAPIRetryExhaustedError, match="failed after 2 retries"):
        client.get_current_weather("London")


def test_connection_error(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _build_client(settings, handler)

    with pytest.raises(WeatherAPIRetryExhaustedError, match="failed after 2 retries"):
        client.get_current_weather("London")


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (400, InvalidRequestError),
        (401, AuthenticationError),
        (404, CityNotFoundError),
    ],
)
def test_non_retryable_http_errors(
    settings: OpenWeatherSettings,
    status_code: int,
    exception_type: type[Exception],
) -> None:
    client = _build_client(
        settings,
        lambda _request: httpx.Response(status_code, json={"message": "provider error"}),
    )

    with pytest.raises(exception_type):
        client.get_current_weather("London")


def test_http_429(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(429, json={"message": "rate limit"})
        return httpx.Response(200, json=VALID_RESPONSE)

    client = _build_client(settings, handler)
    result = client.get_current_weather("London")

    assert attempts["count"] == 2
    assert result.metadata.success is True
    assert result.metadata.retry_count == 1


def test_http_500(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            return httpx.Response(500, json={"message": "server error"})
        return httpx.Response(200, json=VALID_RESPONSE)

    client = _build_client(settings, handler)
    result = client.get_current_weather("London")

    assert attempts["count"] == 3
    assert result.metadata.retry_count == 2
    assert result.metadata.success is True


def test_successful_retry_after_transient_failure(
    settings: OpenWeatherSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("temporary outage")
        return httpx.Response(200, json=VALID_RESPONSE)

    client = _build_client(settings, handler)
    result = client.get_current_weather("London")

    assert attempts["count"] == 2
    assert result.metadata.retry_count == 1


def test_retry_exhaustion(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("weatherpulse.ingestion.openweather_client.time.sleep", lambda _seconds: None)

    client = _build_client(
        settings,
        lambda _request: httpx.Response(500, json={"message": "server error"}),
    )

    with pytest.raises(WeatherAPIRetryExhaustedError) as exc_info:
        client.get_current_weather("London")

    assert exc_info.value.metadata is not None
    assert exc_info.value.metadata.retry_count == 2
    assert exc_info.value.metadata.http_status == 500


def test_retry_after_header(settings: OpenWeatherSettings, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(
        "weatherpulse.ingestion.openweather_client.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    attempts = {"count": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                429,
                json={"message": "rate limit"},
                headers={"Retry-After": "7"},
            )
        return httpx.Response(200, json=VALID_RESPONSE)

    client = _build_client(settings, handler)
    result = client.get_current_weather("London")

    assert result.metadata.success is True
    assert sleeps == [7.0]


def test_api_key_not_exposed_in_errors(settings: OpenWeatherSettings) -> None:
    client = _build_client(
        settings,
        lambda _request: httpx.Response(401, json={"message": "Invalid API key"}),
    )

    with pytest.raises(AuthenticationError) as exc_info:
        client.get_current_weather("London")

    error_text = str(exc_info.value)
    assert TEST_API_KEY not in error_text
    if exc_info.value.metadata is not None and exc_info.value.metadata.error_message:
        assert TEST_API_KEY not in exc_info.value.metadata.error_message


def test_api_key_not_exposed_in_logs(
    settings: OpenWeatherSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="weatherpulse.ingestion.openweather_client")
    client = _build_client(settings, lambda _request: httpx.Response(200, json=VALID_RESPONSE))
    client.get_current_weather("London")

    for record in caplog.records:
        assert TEST_API_KEY not in record.getMessage()
        assert TEST_API_KEY not in json.dumps(record.__dict__, default=str)


def test_missing_api_key_raises_authentication_error() -> None:
    settings = OpenWeatherSettings(api_key="", max_retries=0, retry_backoff=0.01, timeout_seconds=1.0)
    client = OpenWeatherClient(settings, http_client=httpx.Client())

    with pytest.raises(AuthenticationError, match="API key is not configured"):
        client.get_current_weather("London")


def test_http_500_raises_server_error_without_retries() -> None:
    settings = OpenWeatherSettings(
        api_key=TEST_API_KEY,
        max_retries=0,
        retry_backoff=0.01,
        timeout_seconds=1.0,
    )
    client = _build_client(
        settings,
        lambda _request: httpx.Response(500, json={"message": "server error"}),
    )

    with pytest.raises(WeatherAPIRetryExhaustedError):
        client.get_current_weather("London")
