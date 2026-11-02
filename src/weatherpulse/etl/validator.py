"""Validate extracted weather observations before transformation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from weatherpulse.etl.models import (
    CityExtractionResult,
    ExtractionStatus,
    ValidatedObservation,
    ValidationBatchResult,
    ValidationIssue,
    ValidationStatus,
)
from weatherpulse.ingestion.schemas import WeatherObservationData

logger = logging.getLogger(__name__)

TEMPERATURE_MIN_C = -100.0
TEMPERATURE_MAX_C = 80.0
PRESSURE_MIN_HPA = 300
PRESSURE_MAX_HPA = 1200
WIND_SPEED_MAX_MPS = 150.0


class WeatherValidator:
    """Apply ETL validation rules beyond Step 4 Pydantic parsing."""

    def validate_batch(self, extractions: list[CityExtractionResult]) -> ValidationBatchResult:
        results: list[ValidatedObservation] = []
        records_valid = 0
        records_warning = 0
        records_rejected = 0

        for extraction in extractions:
            if extraction.status != ExtractionStatus.SUCCESS:
                continue
            if extraction.weather_result is None or extraction.metadata is None:
                continue

            validated = self.validate(
                city_query=extraction.city_query,
                observation=extraction.weather_result,
                metadata=extraction.metadata,
            )
            results.append(validated)

            if validated.status == ValidationStatus.VALID:
                records_valid += 1
            elif validated.status == ValidationStatus.WARNING:
                records_warning += 1
            else:
                records_rejected += 1

            logger.info(
                "ETL validation city=%s status=%s issues=%s",
                extraction.city_query,
                validated.status,
                len(validated.issues),
            )

        return ValidationBatchResult(
            results=results,
            records_valid=records_valid,
            records_warning=records_warning,
            records_rejected=records_rejected,
        )

    def validate(
        self,
        *,
        city_query: str,
        observation: WeatherObservationData,
        metadata: object,
    ) -> ValidatedObservation:
        from weatherpulse.ingestion.schemas import WeatherRequestMetadata

        if not isinstance(metadata, WeatherRequestMetadata):
            raise TypeError("metadata must be WeatherRequestMetadata")

        issues = self._collect_issues(observation)
        status = self._resolve_status(issues)

        return ValidatedObservation(
            city_query=city_query,
            observation=observation,
            metadata=metadata,
            status=status,
            issues=issues,
        )

    def _collect_issues(self, observation: WeatherObservationData) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if not observation.city_name.strip():
            issues.append(
                ValidationIssue(
                    field="city_name",
                    message="City name is required",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if not observation.country_code.strip() or len(observation.country_code.strip()) != 2:
            issues.append(
                ValidationIssue(
                    field="country_code",
                    message="Country code must be a 2-letter ISO code",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.observed_at.tzinfo is None:
            issues.append(
                ValidationIssue(
                    field="observed_at",
                    message="Observation timestamp must be timezone-aware",
                    severity=ValidationStatus.REJECTED,
                )
            )
        elif observation.observed_at > datetime.now(tz=UTC):
            issues.append(
                ValidationIssue(
                    field="observed_at",
                    message="Observation timestamp is in the future",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.temperature_c < TEMPERATURE_MIN_C or observation.temperature_c > TEMPERATURE_MAX_C:
            issues.append(
                ValidationIssue(
                    field="temperature_c",
                    message=f"Temperature must be between {TEMPERATURE_MIN_C} and {TEMPERATURE_MAX_C} °C",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.humidity_percent < 0 or observation.humidity_percent > 100:
            issues.append(
                ValidationIssue(
                    field="humidity_percent",
                    message="Humidity must be between 0 and 100",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.pressure_hpa < PRESSURE_MIN_HPA or observation.pressure_hpa > PRESSURE_MAX_HPA:
            issues.append(
                ValidationIssue(
                    field="pressure_hpa",
                    message=f"Pressure must be between {PRESSURE_MIN_HPA} and {PRESSURE_MAX_HPA} hPa",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.wind_speed_mps is None:
            issues.append(
                ValidationIssue(
                    field="wind_speed_mps",
                    message="Wind speed is required for database loading",
                    severity=ValidationStatus.REJECTED,
                )
            )
        elif observation.wind_speed_mps < 0 or observation.wind_speed_mps > WIND_SPEED_MAX_MPS:
            issues.append(
                ValidationIssue(
                    field="wind_speed_mps",
                    message=f"Wind speed must be between 0 and {WIND_SPEED_MAX_MPS} m/s",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.wind_direction_deg is not None and (
            observation.wind_direction_deg < 0 or observation.wind_direction_deg > 360
        ):
            issues.append(
                ValidationIssue(
                    field="wind_direction_deg",
                    message="Wind direction must be between 0 and 360 degrees",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.cloudiness_percent is not None and (
            observation.cloudiness_percent < 0 or observation.cloudiness_percent > 100
        ):
            issues.append(
                ValidationIssue(
                    field="cloudiness_percent",
                    message="Cloudiness must be between 0 and 100",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.visibility_m is not None and observation.visibility_m < 0:
            issues.append(
                ValidationIssue(
                    field="visibility_m",
                    message="Visibility must be non-negative",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.rain_1h_mm is not None and observation.rain_1h_mm < 0:
            issues.append(
                ValidationIssue(
                    field="rain_1h_mm",
                    message="Rain volume must be non-negative",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.snow_1h_mm is not None and observation.snow_1h_mm < 0:
            issues.append(
                ValidationIssue(
                    field="snow_1h_mm",
                    message="Snow volume must be non-negative",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if not observation.weather_conditions:
            issues.append(
                ValidationIssue(
                    field="weather_conditions",
                    message="At least one weather condition is required",
                    severity=ValidationStatus.REJECTED,
                )
            )

        if observation.feels_like_c is not None and (
            observation.feels_like_c < TEMPERATURE_MIN_C or observation.feels_like_c > TEMPERATURE_MAX_C
        ):
            issues.append(
                ValidationIssue(
                    field="feels_like_c",
                    message="Feels-like temperature is outside expected range",
                    severity=ValidationStatus.WARNING,
                )
            )

        return issues

    def _resolve_status(self, issues: list[ValidationIssue]) -> ValidationStatus:
        if any(issue.severity == ValidationStatus.REJECTED for issue in issues):
            return ValidationStatus.REJECTED
        if any(issue.severity == ValidationStatus.WARNING for issue in issues):
            return ValidationStatus.WARNING
        return ValidationStatus.VALID
