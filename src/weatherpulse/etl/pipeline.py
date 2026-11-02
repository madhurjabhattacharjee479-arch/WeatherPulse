"""Orchestrate Extract → Validate → Transform → Load for weather data."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from weatherpulse.db.session import session_scope
from weatherpulse.etl.extractor import WeatherExtractor
from weatherpulse.etl.loader import WeatherLoader
from weatherpulse.etl.models import (
    CityLoadResult,
    ExtractionStatus,
    LoadStatus,
    PipelineResult,
    PipelineStatus,
    ValidationStatus,
)
from weatherpulse.etl.transformer import WeatherTransformer
from weatherpulse.etl.validator import WeatherValidator
from weatherpulse.ingestion.openweather_client import OpenWeatherClient
from weatherpulse.repositories import PipelineRunRepository

logger = logging.getLogger(__name__)

RUN_TYPE = "weather_etl"


class WeatherETLPipeline:
    """Enterprise ETL pipeline for OpenWeatherMap current weather data."""

    def __init__(
        self,
        *,
        client: OpenWeatherClient,
        session_factory: sessionmaker[Session],
        cities: list[str],
        extractor: WeatherExtractor | None = None,
        validator: WeatherValidator | None = None,
        transformer: WeatherTransformer | None = None,
        loader: WeatherLoader | None = None,
    ) -> None:
        self._cities = cities
        self._extractor = extractor or WeatherExtractor(client)
        self._validator = validator or WeatherValidator()
        self._transformer = transformer or WeatherTransformer()
        self._loader = loader or WeatherLoader(session_factory)
        self._session_factory = session_factory

    def run(self) -> PipelineResult:
        started_perf = time.perf_counter()
        started_at = datetime.now(tz=UTC)

        with session_scope(self._session_factory) as session:
            pipeline_repo = PipelineRunRepository(session)
            pipeline_run = pipeline_repo.create(
                run_type=RUN_TYPE,
                status="running",
                started_at=started_at,
            )
            run_id = pipeline_run.id

        logger.info("ETL pipeline started run_id=%s cities=%s", run_id, len(self._cities))

        extraction_batch = self._extractor.extract_cities(self._cities)
        validation_batch = self._validator.validate_batch(extraction_batch.results)
        transformed = self._transformer.transform_batch(validation_batch.results)

        city_results: list[CityLoadResult] = []

        for extraction in extraction_batch.results:
            if extraction.status == ExtractionStatus.FAILED:
                city_results.append(
                    self._loader.record_extraction_failure(
                        extraction=extraction,
                        pipeline_run_id=run_id,
                    )
                )

        for validated in validation_batch.results:
            if validated.status == ValidationStatus.REJECTED:
                city_results.append(
                    self._loader.record_validation_rejection(
                        validated=validated,
                        pipeline_run_id=run_id,
                    )
                )

        for item in transformed:
            city_results.append(
                self._loader.load_observation(
                    transformed=item,
                    pipeline_run_id=run_id,
                )
            )

        records_loaded = sum(1 for result in city_results if result.status == LoadStatus.LOADED)
        records_duplicates = sum(1 for result in city_results if result.status == LoadStatus.DUPLICATE)
        records_failed = sum(1 for result in city_results if result.status == LoadStatus.FAILED)
        records_failed += extraction_batch.records_failed

        execution_time_ms = int((time.perf_counter() - started_perf) * 1000)
        finished_at = datetime.now(tz=UTC)
        final_status = _resolve_pipeline_status(
            records_extracted=extraction_batch.records_extracted,
            records_loaded=records_loaded,
            records_duplicates=records_duplicates,
            records_rejected=validation_batch.records_rejected,
            records_failed=records_failed,
        )
        error_message = _build_error_message(city_results, final_status)

        with session_scope(self._session_factory) as session:
            pipeline_repo = PipelineRunRepository(session)
            pipeline_repo.finish(
                run_id,
                status=final_status.value,
                finished_at=finished_at,
                records_processed=records_loaded,
                records_extracted=extraction_batch.records_extracted,
                records_validated=validation_batch.records_valid + validation_batch.records_warning,
                records_rejected=validation_batch.records_rejected,
                execution_time_ms=execution_time_ms,
                error_message=error_message,
            )

        logger.info(
            "ETL pipeline completed run_id=%s status=%s loaded=%s rejected=%s failed=%s duration_ms=%s",
            run_id,
            final_status.value,
            records_loaded,
            validation_batch.records_rejected,
            records_failed,
            execution_time_ms,
        )

        return PipelineResult(
            run_id=run_id,
            status=final_status,
            records_extracted=extraction_batch.records_extracted,
            records_validated=validation_batch.records_valid + validation_batch.records_warning,
            records_rejected=validation_batch.records_rejected,
            records_loaded=records_loaded,
            records_duplicates=records_duplicates,
            records_failed=records_failed,
            execution_time_ms=execution_time_ms,
            city_results=city_results,
            error_message=error_message,
        )


def _resolve_pipeline_status(
    *,
    records_extracted: int,
    records_loaded: int,
    records_duplicates: int,
    records_rejected: int,
    records_failed: int,
) -> PipelineStatus:
    successful_outcomes = records_loaded + records_duplicates
    had_failures = records_failed > 0 or records_rejected > 0

    if records_extracted == 0 or (successful_outcomes == 0 and had_failures):
        return PipelineStatus.FAILED
    if had_failures:
        return PipelineStatus.PARTIAL_SUCCESS
    return PipelineStatus.SUCCESS


def _build_error_message(city_results: list[CityLoadResult], status: PipelineStatus) -> str | None:
    failures = [
        f"{result.city_query}: {result.error_message}"
        for result in city_results
        if result.error_message and result.status in {LoadStatus.FAILED, LoadStatus.SKIPPED}
    ]
    if status == PipelineStatus.SUCCESS and not failures:
        return None
    if not failures:
        return f"Pipeline finished with status {status.value}"
    return "; ".join(failures)
