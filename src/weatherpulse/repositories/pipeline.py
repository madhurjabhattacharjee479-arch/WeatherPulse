from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherpulse.db.models import ApiRequest, DataQualityResult, PipelineRun


class PipelineRunRepository:
    """Data-access methods for pipeline run records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        run_type: str,
        status: str,
        started_at: datetime,
        finished_at: datetime | None = None,
        records_processed: int = 0,
        records_extracted: int = 0,
        records_validated: int = 0,
        records_rejected: int = 0,
        execution_time_ms: int | None = None,
        error_message: str | None = None,
    ) -> PipelineRun:
        run = PipelineRun(
            run_type=run_type,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            records_processed=records_processed,
            records_extracted=records_extracted,
            records_validated=records_validated,
            records_rejected=records_rejected,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish(
        self,
        run_id: int,
        *,
        status: str,
        finished_at: datetime,
        records_processed: int,
        records_extracted: int,
        records_validated: int,
        records_rejected: int,
        execution_time_ms: int,
        error_message: str | None = None,
    ) -> PipelineRun:
        run = self.get(run_id)
        if run is None:
            raise ValueError(f"Pipeline run {run_id} not found")
        run.status = status
        run.finished_at = finished_at
        run.records_processed = records_processed
        run.records_extracted = records_extracted
        run.records_validated = records_validated
        run.records_rejected = records_rejected
        run.execution_time_ms = execution_time_ms
        run.error_message = error_message
        self.session.flush()
        return run

    def get(self, run_id: int) -> PipelineRun | None:
        return self.session.get(PipelineRun, run_id)

    def list_recent(self, *, limit: int = 50) -> list[PipelineRun]:
        statement = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())


class ApiRequestRepository:
    """Data-access methods for provider API request metadata."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        provider: str,
        endpoint: str,
        request_started_at: datetime,
        pipeline_run_id: int | None = None,
        city_id: int | None = None,
        response_ms: int | None = None,
        status_code: int | None = None,
        success: bool = False,
        error_message: str | None = None,
    ) -> ApiRequest:
        request = ApiRequest(
            provider=provider,
            endpoint=endpoint,
            request_started_at=request_started_at,
            pipeline_run_id=pipeline_run_id,
            city_id=city_id,
            response_ms=response_ms,
            status_code=status_code,
            success=success,
            error_message=error_message,
        )
        self.session.add(request)
        self.session.flush()
        return request


class DataQualityResultRepository:
    """Data-access methods for data quality results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        pipeline_run_id: int,
        check_name: str,
        status: str,
        severity: str,
        checked_at: datetime,
        city_id: int | None = None,
        observation_id: int | None = None,
        message: str | None = None,
    ) -> DataQualityResult:
        result = DataQualityResult(
            pipeline_run_id=pipeline_run_id,
            city_id=city_id,
            observation_id=observation_id,
            check_name=check_name,
            status=status,
            severity=severity,
            message=message,
            checked_at=checked_at,
        )
        self.session.add(result)
        self.session.flush()
        return result

    def list_for_pipeline_run(self, pipeline_run_id: int) -> list[DataQualityResult]:
        statement = select(DataQualityResult).where(DataQualityResult.pipeline_run_id == pipeline_run_id)
        return list(self.session.execute(statement).scalars())
