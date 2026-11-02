from decimal import Decimal

from weatherpulse.etl.models import ValidatedObservation, ValidationStatus
from weatherpulse.etl.transformer import WeatherTransformer
from weatherpulse.ingestion.schemas import WeatherRequestMetadata
from tests.etl.conftest import OBSERVED_AT, REQUESTED_AT, make_observation


def test_field_mapping_and_timestamp_preservation() -> None:
    observation = make_observation(city_name="London", country_code="gb")
    validated = ValidatedObservation(
        city_query="London,GB",
        observation=observation,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="London,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.VALID,
        issues=[],
    )

    transformed = WeatherTransformer().transform(validated)

    assert transformed.city.name == "London"
    assert transformed.city.country_code == "GB"
    assert transformed.observed_at == OBSERVED_AT
    assert transformed.observed_at != transformed.metadata.requested_at
    assert transformed.temperature_c == Decimal("15.50")
    assert transformed.condition.code == "800"
    assert transformed.condition.main == "Clear"


def test_precipitation_mapping_rain_only() -> None:
    observation = make_observation(rain_1h_mm=0.5, snow_1h_mm=None)
    validated = ValidatedObservation(
        city_query="London,GB",
        observation=observation,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="London,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.VALID,
        issues=[],
    )

    transformed = WeatherTransformer().transform(validated)

    assert transformed.precipitation_mm == Decimal("0.50")


def test_precipitation_mapping_combined_rain_and_snow() -> None:
    observation = make_observation(rain_1h_mm=0.5, snow_1h_mm=1.25)
    validated = ValidatedObservation(
        city_query="London,GB",
        observation=observation,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="London,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.VALID,
        issues=[],
    )

    transformed = WeatherTransformer().transform(validated)

    assert transformed.precipitation_mm == Decimal("1.75")


def test_precipitation_mapping_none_when_absent() -> None:
    observation = make_observation(rain_1h_mm=None, snow_1h_mm=None)
    validated = ValidatedObservation(
        city_query="London,GB",
        observation=observation,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="London,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.VALID,
        issues=[],
    )

    transformed = WeatherTransformer().transform(validated)

    assert transformed.precipitation_mm is None
