# WeatherPulse Enterprise

WeatherPulse Enterprise is a Python data engineering project for weather data extraction, validation, transformation, and persistence. This repository contains the foundational data pipeline, database models, and repository layer.

## Architecture & Features

### Ingestion Client (`weatherpulse.ingestion`)
- **OpenWeatherMap Integration:** `OpenWeatherClient` queries the OpenWeatherMap Current Weather API (`GET /data/2.5/weather`) using `httpx`.
- **Resilience:** Automatic retry logic with exponential backoff and jitter for transient errors (HTTP 429, 5xx, timeouts). Permanent errors (400, 401, 404) fail fast without retries.
- **Validation & Security:** External JSON responses are validated into typed Pydantic models. Sensitive query parameters and API keys are redacted from logs and exception messages.

### ETL Pipeline (`weatherpulse.etl`)
Orchestrated by `WeatherETLPipeline` following an Extract → Validate → Transform → Load pattern:
- **Extract:** Queries weather data independently per configured city.
- **Validate:** Evaluates observation metrics against realistic meteorological boundaries (temperature, humidity, pressure, wind speed) prior to database insertion.
- **Transform:** Maps validated observation payloads into repository records, combining separate rain and snow volume readings (`rain.1h` and `snow.1h`) into unified `precipitation_mm`.
- **Load & Idempotency:** Loads records within isolated database transactions per city using `session_scope`. Deduplication is enforced by the unique constraint on `(city_id, observed_at)` in `weather_observations`.
- **Pipeline Execution Tracking:** Records execution metrics in `pipeline_runs`, tracking counts (`records_extracted`, `records_validated`, `records_rejected`, `records_processed`), execution durations, and final status (`pending`, `running`, `success`, `partial_success`, `failed`).

### Database & Migrations (`weatherpulse.db`, `migrations`)
- **SQLAlchemy 2.x Declarative Models:** Core schema covering `cities`, `weather_conditions`, `weather_observations`, `pipeline_runs`, `api_requests`, and `data_quality_results`.
- **Alembic Migrations:**
  - `0001_initial_schema`: Initial relational schema, table structures, and constraints.
  - `0002_pipeline_run_stats`: Pipeline execution statistics columns and support for `partial_success` run status.
- **Dialect Support:** Configured for local SQLite development (`data/weatherpulse.db`) with foreign key enforcement and SQLite batch alter support. PostgreSQL is supported architecturally via `DATABASE_URL` (note: PostgreSQL migrations have not been verified in a production environment).

## Current Limitations

The following components are intentionally not implemented yet:
- FastAPI web service endpoints.
- Automated scheduling (cron / Celery / Airflow orchestrators).
- Interactive dashboard or UI.
- Production telemetry, metrics export, and alerting.

## Project Layout

```text
.
├── alembic.ini              # Alembic migration configuration
├── docs/
│   ├── architecture.md      # Architectural design and boundaries
│   └── development.md       # Developer environment setup
├── migrations/              # Alembic environment and version scripts
├── pyproject.toml           # Package definition and pytest configuration
├── requirements.txt         # Project dependencies
├── src/
│   └── weatherpulse/        # Application package
│       ├── app.py           # Command entrypoint & smoke check
│       ├── config.py        # Environment configuration loader
│       ├── db/              # Engine, session, models, and metadata
│       ├── etl/             # Pipeline orchestration, validation, transformation
│       ├── ingestion/       # OpenWeatherMap API client
│       └── repositories/    # Transaction-aware database repositories
└── tests/                   # Pytest test suite
```

## Quick Start

### 1. Environment Setup

```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Upgrade pip and install dependencies in editable mode
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` for local development:

```powershell
Copy-Item .env.example .env
```

Configure your OpenWeatherMap API key and query cities in `.env`:

```text
OPENWEATHER_API_KEY=your_api_key_here
WEATHERPULSE_ETL_CITIES=London,GB,Kolkata,IN,Delhi,IN
```

### 3. Database Migrations

> [!WARNING]
> **Database Safety Notice:** Do not run migrations blindly against an existing database containing important data. Always verify your target `DATABASE_URL` and ensure a complete external backup exists before applying schema changes.

For a fresh local SQLite development database:

```powershell
# Apply all schema migrations
python -m alembic upgrade head

# Verify the recorded migration revision
python -m alembic current
```

### 4. Run Tests & Smoke Check

```powershell
# Run the test suite (62 tests)
python -m pytest

# Run the foundation smoke check
python -m weatherpulse
```

Expected smoke output:
```text
weatherpulse-enterprise (local): foundation
```

### 5. Running the ETL Pipeline Manually

```python
from weatherpulse.config import load_etl_cities
from weatherpulse.db.session import SessionLocal
from weatherpulse.etl import WeatherETLPipeline
from weatherpulse.ingestion import OpenWeatherClient

pipeline = WeatherETLPipeline(
    client=OpenWeatherClient(),
    session_factory=SessionLocal,
    cities=load_etl_cities(),
)
result = pipeline.run()
print(f"Status: {result.status}, Loaded: {result.records_loaded}, Extracted: {result.records_extracted}")
```

## Documentation

- [Architecture Guide](docs/architecture.md)
- [Development Setup](docs/development.md)
