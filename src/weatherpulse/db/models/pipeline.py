from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from weatherpulse.db.base import Base

if TYPE_CHECKING:
    from weatherpulse.db.models.city import City
    from weatherpulse.db.models.weather import WeatherObservation


class PipelineRun(Base):
    """Execution record for future ingestion and processing workflows."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'partial_success', 'failed')",
            name="pipeline_status",
        ),
        CheckConstraint("records_processed >= 0", name="records_processed_non_negative"),
        CheckConstraint("records_extracted >= 0", name="records_extracted_non_negative"),
        CheckConstraint("records_validated >= 0", name="records_validated_non_negative"),
        CheckConstraint("records_rejected >= 0", name="records_rejected_non_negative"),
        CheckConstraint(
            "execution_time_ms IS NULL OR execution_time_ms >= 0",
            name="execution_time_non_negative",
        ),
        CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name="pipeline_time_order"),
        Index("ix_pipeline_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_extracted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    api_requests: Mapped[list["ApiRequest"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    data_quality_results: Mapped[list["DataQualityResult"]] = relationship(
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ApiRequest(Base):
    """HTTP request metadata for future weather provider calls."""

    __tablename__ = "api_requests"
    __table_args__ = (
        CheckConstraint("status_code IS NULL OR (status_code >= 100 AND status_code <= 599)", name="status_code_range"),
        CheckConstraint("response_ms IS NULL OR response_ms >= 0", name="response_ms_non_negative"),
        Index("ix_api_requests_pipeline_run_id", "pipeline_run_id"),
        Index("ix_api_requests_city_id", "city_id"),
        Index("ix_api_requests_provider_endpoint", "provider", "endpoint"),
        Index("ix_api_requests_started_at", "request_started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="SET NULL"))
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    request_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pipeline_run: Mapped["PipelineRun | None"] = relationship(back_populates="api_requests")
    city: Mapped["City | None"] = relationship(back_populates="api_requests")


class DataQualityResult(Base):
    """Result of a future data quality check over pipeline output."""

    __tablename__ = "data_quality_results"
    __table_args__ = (
        CheckConstraint("status IN ('pass', 'warn', 'fail')", name="quality_status"),
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="quality_severity"),
        Index("ix_data_quality_results_pipeline_status", "pipeline_run_id", "status"),
        Index("ix_data_quality_results_observation_id", "observation_id"),
        Index("ix_data_quality_results_check_name", "check_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id", ondelete="SET NULL"))
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("weather_observations.id", ondelete="CASCADE"))
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    pipeline_run: Mapped["PipelineRun"] = relationship(back_populates="data_quality_results")
    city: Mapped["City | None"] = relationship(back_populates="data_quality_results")
    observation: Mapped["WeatherObservation | None"] = relationship(back_populates="data_quality_results")
