# Architecture

This document describes the initial project foundation only. It does not claim that WeatherPulse Enterprise is production ready.

## Current Foundation

The repository uses a `src`-based Python package layout:

```text
src/
└── weatherpulse/
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── config.py
    ├── ingestion/
    ├── etl/
    └── db/
```

Current responsibilities:

- `weatherpulse.config` loads basic environment-backed settings with safe local defaults.
- `weatherpulse.app` exposes a minimal application status function and command entrypoint.
- `weatherpulse.ingestion` contains the OpenWeatherMap HTTP client, response validation, and domain exceptions.
- `weatherpulse.etl` orchestrates Extract → Validate → Transform → Load using the ingestion client and repositories.
- `weatherpulse.db` contains SQLAlchemy engine/session setup, SQLite foreign-key enforcement, and declarative models.
- `weatherpulse.repositories` contains transaction-aware repository classes for database access.
- `migrations` contains Alembic configuration and the initial schema migration.
- `tests/` verifies that the foundation can be imported and run locally.

## Database Foundation

The Step 3 database foundation uses:

- SQLAlchemy 2.x declarative models.
- Alembic migrations.
- SQLite for local development and repeatable tests.
- PostgreSQL-compatible configuration through `DATABASE_URL`.
- Repository classes that operate inside caller-managed SQLAlchemy sessions.

The current schema includes:

- `cities`
- `weather_conditions`
- `weather_observations`
- `pipeline_runs`
- `api_requests`
- `data_quality_results`

Repositories flush writes but do not commit them. Use `weatherpulse.db.session.session_scope` when a unit of work should commit atomically or roll back on failure.

## Planned Boundaries

Future implementation should keep major responsibilities separated:

- Weather provider clients should live behind explicit interfaces.
- ETL orchestration should be isolated from API and dashboard layers.
- Persistence code should be separated from transformation logic.
- Scheduling should trigger existing workflows rather than contain business logic.
- Monitoring should observe system behavior without changing pipeline outcomes.

## Ingestion Client

The Step 4 ingestion client lives in `weatherpulse.ingestion.openweather_client`.

Responsibilities:

- Call OpenWeatherMap `GET /data/2.5/weather` using `httpx`.
- Load credentials and retry settings from environment-backed configuration.
- Validate external JSON with Pydantic before exposing internal observation objects.
- Return safe request metadata for future pipeline persistence.
- Apply controlled retries for transient failures with exponential backoff.

The ingestion client does not write to the database, run ETL, or schedule jobs.

## ETL Pipeline

The Step 5 ETL pipeline lives in `weatherpulse.etl`.

Flow:

```text
OpenWeatherClient → Extract → Validate → Transform → Load → Repositories → Database
```

Key behaviors:

- Each city is extracted independently through the Step 4 client.
- Validation rejects out-of-range values before loading.
- Transformation maps ingestion models to repository inputs.
- Idempotency uses the existing `UNIQUE(city_id, observed_at)` constraint on `weather_observations`.
- Each city load runs in its own `session_scope` transaction for failure isolation.
- Pipeline runs are tracked in `pipeline_runs` with `success`, `partial_success`, or `failed` status.
- Safe API request metadata is persisted to `api_requests`.

Precipitation mapping: OpenWeatherMap `rain.1h` and `snow.1h` are combined into `weather_observations.precipitation_mm` when both are present.

## Not Implemented Yet

The following areas are deliberately absent from the foundation:

- FastAPI routes.
- Scheduler.
- Dashboard.
- Monitoring.
