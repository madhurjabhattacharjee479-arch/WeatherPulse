
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"



def run_migrations(database_path: Path, revision: str) -> None:
    """Run Alembic against an isolated temporary SQLite database."""
    database_url = f"sqlite:///{database_path.as_posix()}"

    previous_url = os.environ.get("DATABASE_URL")
    previous_weatherpulse_url = os.environ.get("WEATHERPULSE_DATABASE_URL")

    try:
        os.environ["DATABASE_URL"] = database_url
        os.environ.pop("WEATHERPULSE_DATABASE_URL", None)

        config = Config(str(ALEMBIC_INI))
        if revision == "base":
            command.downgrade(config, revision)
        else:
            command.upgrade(config, revision)
    finally:
        if previous_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_url

        if previous_weatherpulse_url is None:
            os.environ.pop("WEATHERPULSE_DATABASE_URL", None)
        else:
            os.environ["WEATHERPULSE_DATABASE_URL"] = previous_weatherpulse_url



def test_migrations_upgrade_downgrade_and_reupgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "migration_test.db"

    run_migrations(database_path, "0001_initial_schema")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "pipeline_runs" in inspector.get_table_names()

        initial_columns = {
            column["name"]
            for column in inspector.get_columns("pipeline_runs")
        }
        assert "records_extracted" not in initial_columns
    finally:
        engine.dispose()

    run_migrations(database_path, "0002_pipeline_run_stats")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {
            column["name"]
            for column in inspector.get_columns("pipeline_runs")
        }

        assert {
            "records_extracted",
            "records_validated",
            "records_rejected",
            "execution_time_ms",
        }.issubset(columns)

        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "0002_pipeline_run_stats"
    finally:
        engine.dispose()

    run_migrations(database_path, "base")
    run_migrations(database_path, "0002_pipeline_run_stats")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "0002_pipeline_run_stats"
    finally:
        engine.dispose()
