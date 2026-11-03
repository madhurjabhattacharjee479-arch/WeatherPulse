
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tests.etl.conftest import OBSERVED_AT, REQUESTED_AT
from weatherpulse.db.models import ApiRequest
from weatherpulse.etl.loader import (
    WeatherLoader,
    _is_observation_duplicate_error,
)
from weatherpulse.etl.models import (
    CityExtractionResult,
    ExtractionStatus,
    LoadStatus,
    TransformedCity,
    TransformedCondition,
    TransformedObservation,
    ValidatedObservation,
    ValidationIssue,
    ValidationStatus,
)
from weatherpulse.ingestion.schemas import WeatherRequestMetadata
from weatherpulse.repositories import (
    CityRepository,
    PipelineRunRepository,
    WeatherObservationRepository,
)


def _make_transformed(
    *,
    city_query: str = "London,GB",
    observed_at: datetime = OBSERVED_AT,
):
    return TransformedObservation(
        city_query=city_query,
        city=TransformedCity(
            name="London",
            country_code="GB",
            region="",
            latitude=Decimal("51.51000"),
            longitude=Decimal("-0.13000"),
            timezone="UTC",
        ),
        condition=TransformedCondition(
            code="800",
            main="Clear",
            description="clear sky",
            icon="01d",
        ),
        observed_at=observed_at,
        temperature_c=Decimal("15.50"),
        feels_like_c=Decimal("14.20"),
        humidity_percent=72,
        pressure_hpa=1013,
        wind_speed_mps=Decimal("3.50"),
        wind_direction_deg=180,
        precipitation_mm=Decimal("0.50"),
        cloud_cover_percent=20,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city=city_query,
            endpoint="/data/2.5/weather",
            http_status=200,
            response_time_ms=100,
            success=True,
        ),
        validation_status=ValidationStatus.VALID,
        validation_issues=[],
    )


def _create_pipeline_run(session: Session) -> int:
    run = PipelineRunRepository(session).create(
        run_type="weather_etl",
        status="running",
        started_at=datetime.now(tz=UTC),
    )
    session.flush()
    return run.id


def test_load_new_city_and_observation(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    loader = WeatherLoader(session_factory)
    result = loader.load_observation(
        transformed=_make_transformed(),
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.LOADED
    assert result.city_id is not None
    assert result.observation_id is not None
    assert result.api_request_id is not None

    with session_factory() as session:
        city = CityRepository(session).get_by_identity(
            name="London",
            country_code="GB",
        )
        observation = WeatherObservationRepository(session).get(
            result.observation_id
        )
        api_request = session.get(ApiRequest, result.api_request_id)

    assert city is not None
    assert observation is not None
    assert api_request is not None
    assert api_request.success is True
    assert api_request.endpoint == "/data/2.5/weather"
    assert api_request.pipeline_run_id == run_id


def test_reuse_existing_city(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    CityRepository(db_session).create(
        name="London",
        country_code="GB",
        latitude=Decimal("51.51000"),
        longitude=Decimal("-0.13000"),
    )
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    loader = WeatherLoader(session_factory)
    result = loader.load_observation(
        transformed=_make_transformed(),
        pipeline_run_id=run_id,
    )

    with session_factory() as session:
        cities = CityRepository(session).list_by_country("GB")

    assert result.status == LoadStatus.LOADED
    assert len(cities) == 1


def test_duplicate_observation_is_idempotent(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    loader = WeatherLoader(session_factory)
    transformed = _make_transformed()

    first = loader.load_observation(
        transformed=transformed,
        pipeline_run_id=run_id,
    )
    second = loader.load_observation(
        transformed=transformed,
        pipeline_run_id=run_id,
    )

    assert first.status == LoadStatus.LOADED
    assert second.status == LoadStatus.DUPLICATE
    assert first.observation_id == second.observation_id

    with session_factory() as session:
        observations = WeatherObservationRepository(session).list_for_city(
            city_id=first.city_id
        )

    assert len(observations) == 1


def test_concurrent_duplicate_insert_is_recovered(
    db_session: Session,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    original_create = WeatherObservationRepository.create

    def simulate_concurrent_insert(self, **kwargs):
        # Simulate another transaction having inserted the observation.
        observation = original_create(self, **kwargs)
        self.session.commit()

        original = sqlite3.IntegrityError(
            "UNIQUE constraint failed: "
            "weather_observations.city_id, weather_observations.observed_at"
        )
        raise IntegrityError("insert", {}, original)

    monkeypatch.setattr(
        "weatherpulse.etl.loader.WeatherObservationRepository.create",
        simulate_concurrent_insert,
    )

    loader = WeatherLoader(session_factory)
    result = loader.load_observation(
        transformed=_make_transformed(),
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.DUPLICATE
    assert result.city_id is not None
    assert result.observation_id is not None
    assert result.error_message is None

    with session_factory() as session:
        observation = WeatherObservationRepository(session).get(
            result.observation_id
        )

    assert observation is not None


def test_record_extraction_failure_persists_api_request(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    loader = WeatherLoader(session_factory)
    extraction = CityExtractionResult(
        city_query="Unknown",
        status=ExtractionStatus.FAILED,
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="Unknown",
            endpoint="/data/2.5/weather",
            http_status=404,
            response_time_ms=90,
            success=False,
            error_type="CityNotFoundError",
            error_message="City not found",
        ),
        error_type="CityNotFoundError",
        error_message="City not found",
    )

    result = loader.record_extraction_failure(
        extraction=extraction,
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.FAILED
    assert result.api_request_id is not None


def test_record_validation_rejection(
    db_session: Session,
    session_factory: sessionmaker[Session],
) -> None:
    from tests.etl.conftest import make_observation

    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    validated = ValidatedObservation(
        city_query="Bad,GB",
        observation=make_observation(humidity_percent=200),
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="Bad,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.REJECTED,
        issues=[
            ValidationIssue(
                field="humidity_percent",
                message="Humidity must be between 0 and 100",
                severity=ValidationStatus.REJECTED,
            )
        ],
    )

    loader = WeatherLoader(session_factory)
    result = loader.record_validation_rejection(
        validated=validated,
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.SKIPPED
    assert result.api_request_id is not None


def test_validation_rejection_persistence_failure_returns_safe_error(
    db_session: Session,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.etl.conftest import make_observation

    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    validated = ValidatedObservation(
        city_query="Bad,GB",
        observation=make_observation(humidity_percent=200),
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="Bad,GB",
            endpoint="/data/2.5/weather",
            success=True,
        ),
        status=ValidationStatus.REJECTED,
        issues=[
            ValidationIssue(
                field="humidity_percent",
                message="Humidity must be between 0 and 100",
                severity=ValidationStatus.REJECTED,
            )
        ],
    )

    def raise_sensitive_error(*args, **kwargs):
        raise RuntimeError(
            "postgres://user:secret-password@internal-db/private"
        )

    monkeypatch.setattr(
        "weatherpulse.etl.loader.ApiRequestRepository.create",
        raise_sensitive_error,
    )

    loader = WeatherLoader(session_factory)
    result = loader.record_validation_rejection(
        validated=validated,
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.FAILED
    assert result.error_message == (
        "Unexpected error while persisting validation rejection"
    )
    assert "secret-password" not in (result.error_message or "")
    assert "internal-db" not in (result.error_message or "")


def test_detects_sqlite_observation_duplicate_constraint() -> None:
    original = sqlite3.IntegrityError(
        "UNIQUE constraint failed: "
        "weather_observations.city_id, weather_observations.observed_at"
    )
    error = IntegrityError("insert", {}, original)

    assert _is_observation_duplicate_error(error) is True


def test_does_not_misclassify_other_integrity_errors_as_duplicates() -> None:
    original = sqlite3.IntegrityError(
        "UNIQUE constraint failed: weather_observations.id"
    )
    error = IntegrityError("insert", {}, original)

    assert _is_observation_duplicate_error(error) is False


def test_load_observation_does_not_expose_database_exception_details(
    db_session: Session,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    def raise_sensitive_error(*args, **kwargs):
        raise RuntimeError(
            "postgres://user:secret-password@internal-db/private"
        )

    monkeypatch.setattr(
        "weatherpulse.etl.loader.CityRepository.get_by_identity",
        raise_sensitive_error,
    )

    loader = WeatherLoader(session_factory)
    result = loader.load_observation(
        transformed=_make_transformed(),
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.FAILED
    assert result.error_message == "Unexpected error during database load"
    assert "secret-password" not in (result.error_message or "")
    assert "internal-db" not in (result.error_message or "")


def test_duplicate_recovery_failure_returns_safe_error(
    db_session: Session,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id = _create_pipeline_run(db_session)
    db_session.commit()

    def raise_integrity_error(*args, **kwargs):
        original = sqlite3.IntegrityError(
            "UNIQUE constraint failed: "
            "weather_observations.city_id, weather_observations.observed_at"
        )
        raise IntegrityError("insert", {}, original)

    lookup_calls = 0

    def fail_recovery(*args, **kwargs):
        nonlocal lookup_calls
        lookup_calls += 1

        if lookup_calls == 1:
            return None

        raise RuntimeError("internal-db-secret")

    monkeypatch.setattr(
        "weatherpulse.etl.loader.WeatherObservationRepository.create",
        raise_integrity_error,
    )
    monkeypatch.setattr(
        "weatherpulse.etl.loader.WeatherObservationRepository.get_for_city_at",
        fail_recovery,
    )

    loader = WeatherLoader(session_factory)
    result = loader.load_observation(
        transformed=_make_transformed(),
        pipeline_run_id=run_id,
    )

    assert result.status == LoadStatus.FAILED
    assert result.error_message == (
        "Unable to verify duplicate observation after database conflict"
    )
    assert "internal-db-secret" not in (result.error_message or "")
