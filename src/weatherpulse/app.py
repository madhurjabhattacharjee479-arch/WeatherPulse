"""Command-line entry point for WeatherPulse."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from weatherpulse.config import (
    load_etl_cities,
    load_openweather_settings,
    load_settings,
)


def application_status() -> dict[str, str]:
    """Return a minimal status payload for local foundation checks."""
    settings = load_settings()
    return {
        "service": "weatherpulse-enterprise",
        "environment": settings.environment,
        "status": "foundation",
    }


def _configure_logging() -> None:
    """Configure application logging from environment settings."""
    settings = load_settings()
    level = getattr(logging, settings.log_level.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _run_etl() -> int:
    """Validate configuration and execute the weather ETL pipeline."""
    from weatherpulse.db.engine import create_engine_from_url
    from weatherpulse.db.session import get_session_factory
    from weatherpulse.etl.models import PipelineStatus
    from weatherpulse.etl.pipeline import WeatherETLPipeline
    from weatherpulse.ingestion.openweather_client import OpenWeatherClient

    settings = load_settings()
    weather_settings = load_openweather_settings()
    cities = load_etl_cities()

    if not weather_settings.api_key:
        print(
            "Configuration error: set OPENWEATHER_API_KEY before running ETL.",
            file=sys.stderr,
        )
        return 2

    if not cities:
        print(
            "Configuration error: set WEATHERPULSE_ETL_CITIES "
            "to a comma-separated list of cities.",
            file=sys.stderr,
        )
        return 2

    engine = create_engine_from_url(settings.database_url)

    try:
        session_factory = get_session_factory(engine)

        with OpenWeatherClient(settings=weather_settings) as client:
            pipeline = WeatherETLPipeline(
                client=client,
                session_factory=session_factory,
                cities=cities,
            )
            result = pipeline.run()

        print(
            f"ETL run {result.run_id}: {result.status.value} | "
            f"extracted={result.records_extracted} | "
            f"validated={result.records_validated} | "
            f"rejected={result.records_rejected} | "
            f"loaded={result.records_loaded} | "
            f"duplicates={result.records_duplicates} | "
            f"failed={result.records_failed} | "
            f"duration={result.execution_time_ms}ms"
        )

        if result.error_message:
            print(f"Details: {result.error_message}")

        return 0 if result.status == PipelineStatus.SUCCESS else 1
    finally:
        engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the WeatherPulse command-line interface."""
    parser = argparse.ArgumentParser(
        prog="weatherpulse",
        description="WeatherPulse weather data pipeline",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("status", help="show application foundation status")
    subparsers.add_parser("run", help="execute the weather ETL pipeline")

    args = parser.parse_args(argv)
    _configure_logging()

    if args.command == "run":
        return _run_etl()

    status = application_status()
    print(
        f"{status['service']} "
        f"({status['environment']}): {status['status']}"
    )
    return 0
