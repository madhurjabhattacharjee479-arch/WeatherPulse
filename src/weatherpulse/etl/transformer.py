"""Transform validated observations into database-ready structures."""

from __future__ import annotations

import logging
from decimal import Decimal

from weatherpulse.etl.models import (
    TransformedCity,
    TransformedCondition,
    TransformedObservation,
    ValidatedObservation,
    ValidationStatus,
)
from weatherpulse.ingestion.schemas import WeatherObservationData

logger = logging.getLogger(__name__)


class WeatherTransformer:
    """Map ingestion models to repository input structures."""

    def transform_batch(self, validated: list[ValidatedObservation]) -> list[TransformedObservation]:
        transformed: list[TransformedObservation] = []
        for item in validated:
            if item.status == ValidationStatus.REJECTED:
                continue
            transformed.append(self.transform(item))
        return transformed

    def transform(self, validated: ValidatedObservation) -> TransformedObservation:
        observation = validated.observation
        primary_condition = observation.weather_conditions[0]

        transformed = TransformedObservation(
            city_query=validated.city_query,
            city=self._transform_city(observation),
            condition=self._transform_condition(primary_condition),
            observed_at=observation.observed_at,
            temperature_c=_to_decimal(observation.temperature_c, precision="0.01"),
            feels_like_c=_optional_decimal(observation.feels_like_c, precision="0.01"),
            humidity_percent=observation.humidity_percent,
            pressure_hpa=observation.pressure_hpa,
            wind_speed_mps=_to_decimal(observation.wind_speed_mps or 0.0, precision="0.01"),
            wind_direction_deg=observation.wind_direction_deg,
            precipitation_mm=_combine_precipitation(observation),
            cloud_cover_percent=observation.cloudiness_percent,
            metadata=validated.metadata,
            validation_status=validated.status,
            validation_issues=validated.issues,
        )

        logger.info(
            "ETL transformation city=%s observed_at=%s precipitation_mm=%s",
            validated.city_query,
            transformed.observed_at.isoformat(),
            transformed.precipitation_mm,
        )
        return transformed

    def _transform_city(self, observation: WeatherObservationData) -> TransformedCity:
        return TransformedCity(
            name=observation.city_name.strip(),
            country_code=observation.country_code.strip().upper(),
            region="",
            latitude=_to_decimal(observation.latitude, precision="0.00001"),
            longitude=_to_decimal(observation.longitude, precision="0.00001"),
            timezone="UTC",
        )

    def _transform_condition(self, condition) -> TransformedCondition:
        return TransformedCondition(
            code=str(condition.id),
            main=condition.main,
            description=condition.description,
            icon=condition.icon,
        )


def _combine_precipitation(observation: WeatherObservationData) -> Decimal | None:
    """Combine 1h rain and snow into the single precipitation_mm database field.

    OpenWeatherMap reports rain and snow separately. The weather_observations table
    stores a single precipitation_mm column, so both volumes are summed when present.
    """
    rain = observation.rain_1h_mm
    snow = observation.snow_1h_mm

    if rain is None and snow is None:
        return None
    if rain is not None and snow is not None:
        return _to_decimal(rain + snow, precision="0.01")
    value = rain if rain is not None else snow
    assert value is not None
    return _to_decimal(value, precision="0.01")


def _to_decimal(value: float, *, precision: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(precision))


def _optional_decimal(value: float | None, *, precision: str) -> Decimal | None:
    if value is None:
        return None
    return _to_decimal(value, precision=precision)
