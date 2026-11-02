"""Typed models for the weather ETL pipeline."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from weatherpulse.ingestion.schemas import WeatherObservationData, WeatherRequestMetadata


class ExtractionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    VALID = "valid"
    WARNING = "warning"
    REJECTED = "rejected"


class LoadStatus(StrEnum):
    LOADED = "loaded"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    message: str
    severity: ValidationStatus


class CityExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_query: str
    status: ExtractionStatus
    weather_result: WeatherObservationData | None = None
    metadata: WeatherRequestMetadata | None = None
    error_type: str | None = None
    error_message: str | None = None


class ExtractionBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[CityExtractionResult]
    records_extracted: int = 0
    records_failed: int = 0


class ValidatedObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_query: str
    observation: WeatherObservationData
    metadata: WeatherRequestMetadata
    status: ValidationStatus
    issues: list[ValidationIssue] = Field(default_factory=list)


class ValidationBatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[ValidatedObservation]
    records_valid: int = 0
    records_warning: int = 0
    records_rejected: int = 0


class TransformedCity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    country_code: str
    region: str
    latitude: Decimal
    longitude: Decimal
    timezone: str


class TransformedCondition(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    main: str
    description: str
    icon: str | None = None


class TransformedObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_query: str
    city: TransformedCity
    condition: TransformedCondition
    observed_at: datetime
    temperature_c: Decimal
    feels_like_c: Decimal | None = None
    humidity_percent: int
    pressure_hpa: int
    wind_speed_mps: Decimal
    wind_direction_deg: int | None = None
    precipitation_mm: Decimal | None = None
    cloud_cover_percent: int | None = None
    metadata: WeatherRequestMetadata
    validation_status: ValidationStatus
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


class CityLoadResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    city_query: str
    status: LoadStatus
    city_id: int | None = None
    observation_id: int | None = None
    api_request_id: int | None = None
    error_message: str | None = None


class PipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: int
    status: PipelineStatus
    records_extracted: int
    records_validated: int
    records_rejected: int
    records_loaded: int
    records_duplicates: int
    records_failed: int
    execution_time_ms: int
    city_results: list[CityLoadResult]
    error_message: str | None = None
