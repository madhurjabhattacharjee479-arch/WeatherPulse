from datetime import UTC, datetime, timedelta

import pytest

from weatherpulse.etl.models import ExtractionStatus, ValidationStatus
from weatherpulse.etl.validator import WeatherValidator
from weatherpulse.ingestion.schemas import WeatherRequestMetadata
from tests.etl.conftest import make_observation, REQUESTED_AT


@pytest.fixture
def validator() -> WeatherValidator:
    return WeatherValidator()


def test_valid_observation(validator: WeatherValidator) -> None:
    observation = make_observation()
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.VALID
    assert result.issues == []


def test_missing_wind_speed_rejected(validator: WeatherValidator) -> None:
    base = make_observation()
    observation = base.model_copy(update={"wind_speed_mps": None})
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.REJECTED


def test_invalid_humidity(validator: WeatherValidator) -> None:
    observation = make_observation(humidity_percent=150)
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.REJECTED


def test_invalid_pressure(validator: WeatherValidator) -> None:
    observation = make_observation(pressure_hpa=50)
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.REJECTED


def test_invalid_temperature(validator: WeatherValidator) -> None:
    observation = make_observation(temperature_c=120.0)
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.REJECTED


def test_invalid_timestamp(validator: WeatherValidator) -> None:
    observation = make_observation(observed_at=datetime.now(tz=UTC) + timedelta(days=1))
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.REJECTED


def test_optional_rain_and_snow(validator: WeatherValidator) -> None:
    observation = make_observation(rain_1h_mm=None, snow_1h_mm=1.25)
    metadata = WeatherRequestMetadata(
        requested_at=REQUESTED_AT,
        city="London,GB",
        endpoint="/data/2.5/weather",
        success=True,
    )

    result = validator.validate(city_query="London,GB", observation=observation, metadata=metadata)

    assert result.status == ValidationStatus.VALID


def test_validation_batch_statistics(validator: WeatherValidator) -> None:
    from weatherpulse.etl.models import CityExtractionResult

    batch = validator.validate_batch(
        [
            CityExtractionResult(
                city_query="London,GB",
                status=ExtractionStatus.SUCCESS,
                weather_result=make_observation(),
                metadata=WeatherRequestMetadata(
                    requested_at=REQUESTED_AT,
                    city="London,GB",
                    endpoint="/data/2.5/weather",
                    success=True,
                ),
            ),
            CityExtractionResult(
                city_query="Bad,GB",
                status=ExtractionStatus.SUCCESS,
                weather_result=make_observation(humidity_percent=200),
                metadata=WeatherRequestMetadata(
                    requested_at=REQUESTED_AT,
                    city="Bad,GB",
                    endpoint="/data/2.5/weather",
                    success=True,
                ),
            ),
        ]
    )

    assert batch.records_valid == 1
    assert batch.records_rejected == 1
