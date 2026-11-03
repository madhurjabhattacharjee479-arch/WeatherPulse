"""Load transformed weather observations into the database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from weatherpulse.db.session import session_scope
from weatherpulse.etl.models import (
    CityExtractionResult,
    CityLoadResult,
    ExtractionStatus,
    LoadStatus,
    TransformedObservation,
    ValidatedObservation,
    ValidationStatus,
)
from weatherpulse.ingestion.schemas import WeatherRequestMetadata
from weatherpulse.repositories import (
    ApiRequestRepository,
    CityRepository,
    DataQualityResultRepository,
    WeatherConditionRepository,
    WeatherObservationRepository,
)

logger = logging.getLogger(__name__)

PROVIDER_NAME = "openweathermap"
OBSERVATION_UNIQUE_CONSTRAINT = "uq_weather_observations_city_time"


def _is_observation_duplicate_error(exc: IntegrityError) -> bool:
    """Return True only for the weather observation city/timestamp constraint."""
    original = exc.orig

    # PostgreSQL (psycopg): use structured diagnostic metadata.
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)

    if constraint_name == OBSERVATION_UNIQUE_CONSTRAINT:
        return True

    # SQLite: identify the unique constraint by its affected columns.
    message = str(original).lower()

    return (
        "unique constraint failed" in message
        and "weather_observations.city_id" in message
        and "weather_observations.observed_at" in message
    )


class WeatherLoader:
    """Persist cities, conditions, observations, and API request metadata."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load_observation(
        self,
        *,
        transformed: TransformedObservation,
        pipeline_run_id: int,
    ) -> CityLoadResult:
        city_query = transformed.city_query
        city_id: int | None = None

        try:
            with session_scope(self._session_factory) as session:
                city_repo = CityRepository(session)
                condition_repo = WeatherConditionRepository(session)
                observation_repo = WeatherObservationRepository(session)
                api_repo = ApiRequestRepository(session)
                quality_repo = DataQualityResultRepository(session)

                city = self._resolve_city(city_repo, transformed)
                city_id = city.id

                condition = self._resolve_condition(
                    condition_repo,
                    transformed,
                )

                existing = observation_repo.get_for_city_at(
                    city_id=city_id,
                    observed_at=transformed.observed_at,
                )

                api_request = self._persist_api_request(
                    api_repo,
                    metadata=transformed.metadata,
                    pipeline_run_id=pipeline_run_id,
                    city_id=city_id,
                )

                if existing is not None:
                    logger.info(
                        "ETL duplicate detected city=%s observed_at=%s observation_id=%s",
                        city_query,
                        transformed.observed_at.isoformat(),
                        existing.id,
                    )

                    self._record_validation_quality(
                        quality_repo,
                        pipeline_run_id=pipeline_run_id,
                        city_id=city_id,
                        observation_id=existing.id,
                        transformed=transformed,
                    )

                    return CityLoadResult(
                        city_query=city_query,
                        status=LoadStatus.DUPLICATE,
                        city_id=city_id,
                        observation_id=existing.id,
                        api_request_id=api_request.id,
                    )

                observation = observation_repo.create(
                    city_id=city_id,
                    condition_id=condition.id,
                    observed_at=transformed.observed_at,
                    temperature_c=transformed.temperature_c,
                    feels_like_c=transformed.feels_like_c,
                    humidity_percent=transformed.humidity_percent,
                    pressure_hpa=transformed.pressure_hpa,
                    wind_speed_mps=transformed.wind_speed_mps,
                    wind_direction_deg=transformed.wind_direction_deg,
                    precipitation_mm=transformed.precipitation_mm,
                    cloud_cover_percent=transformed.cloud_cover_percent,
                )

                self._record_validation_quality(
                    quality_repo,
                    pipeline_run_id=pipeline_run_id,
                    city_id=city_id,
                    observation_id=observation.id,
                    transformed=transformed,
                )

                logger.info(
                    "ETL load completed city=%s observation_id=%s",
                    city_query,
                    observation.id,
                )

                return CityLoadResult(
                    city_query=city_query,
                    status=LoadStatus.LOADED,
                    city_id=city_id,
                    observation_id=observation.id,
                    api_request_id=api_request.id,
                )

        except IntegrityError as exc:
            if (
                _is_observation_duplicate_error(exc)
                and city_id is not None
            ):
                try:
                    with session_scope(self._session_factory) as session:
                        existing = WeatherObservationRepository(
                            session
                        ).get_for_city_at(
                            city_id=city_id,
                            observed_at=transformed.observed_at,
                        )

                        existing_id = (
                            existing.id if existing is not None else None
                        )

                except Exception as recovery_exc:
                    logger.warning(
                        "ETL duplicate recovery failed city=%s error_type=%s",
                        city_query,
                        type(recovery_exc).__name__,
                    )

                    return CityLoadResult(
                        city_query=city_query,
                        status=LoadStatus.FAILED,
                        error_message=(
                            "Unable to verify duplicate observation "
                            "after database conflict"
                        ),
                    )

                if existing_id is not None:
                    logger.info(
                        "ETL concurrent duplicate detected city=%s observed_at=%s observation_id=%s",
                        city_query,
                        transformed.observed_at.isoformat(),
                        existing_id,
                    )

                    return CityLoadResult(
                        city_query=city_query,
                        status=LoadStatus.DUPLICATE,
                        city_id=city_id,
                        observation_id=existing_id,
                    )

            logger.warning(
                "ETL load integrity error city=%s error_type=%s",
                city_query,
                type(exc).__name__,
            )

            return CityLoadResult(
                city_query=city_query,
                status=LoadStatus.FAILED,
                error_message="Database integrity error during load",
            )

        except Exception as exc:
            logger.warning(
                "ETL load failed city=%s error_type=%s",
                city_query,
                type(exc).__name__,
            )

            return CityLoadResult(
                city_query=city_query,
                status=LoadStatus.FAILED,
                error_message="Unexpected error during database load",
            )

    def record_extraction_failure(
        self,
        *,
        extraction: CityExtractionResult,
        pipeline_run_id: int,
    ) -> CityLoadResult:
        if extraction.status != ExtractionStatus.FAILED:
            return CityLoadResult(
                city_query=extraction.city_query,
                status=LoadStatus.SKIPPED,
            )

        try:
            with session_scope(self._session_factory) as session:
                api_repo = ApiRequestRepository(session)
                api_request_id = None

                if extraction.metadata is not None:
                    api_request = self._persist_api_request(
                        api_repo,
                        metadata=extraction.metadata,
                        pipeline_run_id=pipeline_run_id,
                        city_id=None,
                        override_success=False,
                        override_error_type=extraction.error_type,
                        override_error_message=extraction.error_message,
                    )

                    api_request_id = api_request.id

        except Exception as exc:
            logger.warning(
                "ETL failed to persist extraction failure metadata "
                "city=%s error_type=%s",
                extraction.city_query,
                type(exc).__name__,
            )

            return CityLoadResult(
                city_query=extraction.city_query,
                status=LoadStatus.FAILED,
                error_message=extraction.error_message,
            )

        return CityLoadResult(
            city_query=extraction.city_query,
            status=LoadStatus.FAILED,
            api_request_id=api_request_id,
            error_message=extraction.error_message,
        )

    def record_validation_rejection(
        self,
        *,
        validated: ValidatedObservation,
        pipeline_run_id: int,
    ) -> CityLoadResult:
        try:
            with session_scope(self._session_factory) as session:
                api_repo = ApiRequestRepository(session)
                quality_repo = DataQualityResultRepository(session)

                api_request = self._persist_api_request(
                    api_repo,
                    metadata=validated.metadata,
                    pipeline_run_id=pipeline_run_id,
                    city_id=None,
                )

                message = (
                    "; ".join(issue.message for issue in validated.issues)
                    or "Validation rejected"
                )

                quality_repo.create(
                    pipeline_run_id=pipeline_run_id,
                    check_name="etl_validation",
                    status="fail",
                    severity="critical",
                    checked_at=datetime.now(tz=UTC),
                    message=message,
                )

                return CityLoadResult(
                    city_query=validated.city_query,
                    status=LoadStatus.SKIPPED,
                    api_request_id=api_request.id,
                    error_message=message,
                )

        except Exception as exc:
            logger.warning(
                "ETL validation rejection persistence failed "
                "city=%s error_type=%s",
                validated.city_query,
                type(exc).__name__,
            )

            return CityLoadResult(
                city_query=validated.city_query,
                status=LoadStatus.FAILED,
                error_message=(
                    "Unexpected error while persisting validation rejection"
                ),
            )

    def _resolve_city(
        self,
        city_repo: CityRepository,
        transformed: TransformedObservation,
    ):
        city_data = transformed.city

        existing = city_repo.get_by_identity(
            name=city_data.name,
            country_code=city_data.country_code,
            region=city_data.region,
        )

        if existing is not None:
            return existing

        try:
            # A savepoint allows recovery from a concurrent city insert
            # without invalidating the outer transaction.
            with city_repo.session.begin_nested():
                return city_repo.create(
                    name=city_data.name,
                    country_code=city_data.country_code,
                    region=city_data.region,
                    latitude=city_data.latitude,
                    longitude=city_data.longitude,
                    timezone=city_data.timezone,
                )

        except IntegrityError:
            existing = city_repo.get_by_identity(
                name=city_data.name,
                country_code=city_data.country_code,
                region=city_data.region,
            )

            if existing is None:
                raise

            return existing

    def _resolve_condition(
        self,
        condition_repo: WeatherConditionRepository,
        transformed: TransformedObservation,
    ):
        condition_data = transformed.condition

        existing = condition_repo.get_by_code(condition_data.code)

        if existing is not None:
            return existing

        return condition_repo.create(
            code=condition_data.code,
            main=condition_data.main,
            description=condition_data.description,
            icon=condition_data.icon,
        )

    def _persist_api_request(
        self,
        api_repo: ApiRequestRepository,
        *,
        metadata: WeatherRequestMetadata,
        pipeline_run_id: int,
        city_id: int | None,
        override_success: bool | None = None,
        override_error_type: str | None = None,
        override_error_message: str | None = None,
    ):
        error_message = override_error_message or metadata.error_message

        if override_error_type:
            error_message = _format_api_error_message(
                override_error_type,
                error_message,
            )

        return api_repo.create(
            provider=PROVIDER_NAME,
            endpoint=metadata.endpoint,
            request_started_at=metadata.requested_at,
            pipeline_run_id=pipeline_run_id,
            city_id=city_id,
            response_ms=metadata.response_time_ms,
            status_code=metadata.http_status,
            success=(
                metadata.success
                if override_success is None
                else override_success
            ),
            error_message=error_message,
        )

    def _record_validation_quality(
        self,
        quality_repo: DataQualityResultRepository,
        *,
        pipeline_run_id: int,
        city_id: int,
        observation_id: int,
        transformed: TransformedObservation,
    ) -> None:
        if transformed.validation_status != ValidationStatus.WARNING:
            return

        message = "; ".join(
            issue.message for issue in transformed.validation_issues
        )

        quality_repo.create(
            pipeline_run_id=pipeline_run_id,
            city_id=city_id,
            observation_id=observation_id,
            check_name="etl_validation",
            status="warn",
            severity="warning",
            checked_at=datetime.now(tz=UTC),
            message=message or "Validation warning",
        )


def _format_api_error_message(
    error_type: str | None,
    error_message: str | None,
) -> str | None:
    if error_type and error_message:
        return f"{error_type}: {error_message}"

    return error_type or error_message
