from __future__ import annotations

from datetime import UTC, datetime

import pytest

from weatherpulse.ingestion.exceptions import CityNotFoundError
from weatherpulse.ingestion.schemas import (
    CurrentWeatherResult,
    WeatherConditionInfo,
    WeatherObservationData,
    WeatherRequestMetadata,
)

OBSERVED_AT = datetime(2020, 11, 12, 12, 0, tzinfo=UTC)
REQUESTED_AT = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def make_observation(
    *,
    city_name: str = "London",
    country_code: str = "GB",
    observed_at: datetime = OBSERVED_AT,
    temperature_c: float = 15.5,
    humidity_percent: int = 72,
    pressure_hpa: int = 1013,
    wind_speed_mps: float = 3.5,
    rain_1h_mm: float | None = 0.5,
    snow_1h_mm: float | None = None,
) -> WeatherObservationData:
    return WeatherObservationData(
        city_name=city_name,
        country_code=country_code,
        latitude=51.51,
        longitude=-0.13,
        observed_at=observed_at,
        temperature_c=temperature_c,
        feels_like_c=14.2,
        temp_min_c=13.0,
        temp_max_c=17.0,
        pressure_hpa=pressure_hpa,
        humidity_percent=humidity_percent,
        visibility_m=10000,
        wind_speed_mps=wind_speed_mps,
        wind_direction_deg=180,
        cloudiness_percent=20,
        rain_1h_mm=rain_1h_mm,
        snow_1h_mm=snow_1h_mm,
        weather_conditions=[
            WeatherConditionInfo(id=800, main="Clear", description="clear sky", icon="01d"),
        ],
    )


def make_weather_result(
    *,
    city_query: str = "London",
    observation: WeatherObservationData | None = None,
) -> CurrentWeatherResult:
    obs = observation or make_observation(city_name=city_query.split(",")[0])
    return CurrentWeatherResult(
        observation=obs,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city=city_query,
            endpoint="/data/2.5/weather",
            http_status=200,
            response_time_ms=120,
            success=True,
            retry_count=0,
        ),
    )


class MockWeatherClient:
    """Test double for OpenWeatherClient."""

    def __init__(self, responses: dict[str, CurrentWeatherResult | Exception]) -> None:
        self._responses = responses

    def get_current_weather(self, city: str) -> CurrentWeatherResult:
        outcome = self._responses[city]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def sample_observation() -> WeatherObservationData:
    return make_observation()


@pytest.fixture
def sample_weather_result() -> CurrentWeatherResult:
    return make_weather_result()


@pytest.fixture
def city_not_found_error() -> CityNotFoundError:
    return CityNotFoundError(
        "City not found",
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="Unknown",
            endpoint="/data/2.5/weather",
            http_status=404,
            response_time_ms=80,
            success=False,
            error_type="CityNotFoundError",
            error_message="City not found",
        ),
    )
