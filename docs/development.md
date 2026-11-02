# Development Setup

## Requirements

- Python 3.11 or newer.
- `pip`.

## Local Environment

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e . -r requirements.txt
```

## Configuration

Copy `.env.example` to `.env` for local development when configuration is needed.

```powershell
Copy-Item .env.example .env
```

The checked-in `.env.example` contains placeholders only. Do not store real API keys, tokens, or secrets in committed files.

OpenWeatherMap ingestion configuration:

```text
OPENWEATHER_API_KEY=replace-with-your-api-key
OPENWEATHER_BASE_URL=https://api.openweathermap.org
OPENWEATHER_TIMEOUT_SECONDS=10
OPENWEATHER_MAX_RETRIES=3
OPENWEATHER_RETRY_BACKOFF=2
```

The client calls `GET /data/2.5/weather` with `units=metric`. Transient failures such as timeouts, connection errors, HTTP 429, and HTTP 500-599 are retried with exponential backoff. HTTP 400, 401, and 404 are not retried.

Database configuration uses `DATABASE_URL`. Local development defaults to SQLite:

```text
DATABASE_URL=sqlite:///./data/weatherpulse.db
```

For production PostgreSQL, provide a PostgreSQL SQLAlchemy URL through the environment. Do not hardcode credentials in source files.

## Database Migrations

Run Alembic migrations with:

```powershell
python -m alembic upgrade head
```

Check the current migration version with:

```powershell
python -m alembic current
```

## Tests

Run the test suite with:

```powershell
python -m pytest
```

Run ingestion tests only:

```powershell
python -m pytest tests/ingestion
```

Run ETL tests only:

```powershell
python -m pytest tests/etl
```

## ETL Pipeline

Configure cities as comma-separated OpenWeatherMap query values:

```text
WEATHERPULSE_ETL_CITIES=London,GB,Kolkata,IN,Delhi,IN
```

Run the ETL pipeline manually from Python:

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
print(result.status, result.records_loaded)
```

Apply migration `0002_pipeline_run_stats` before running ETL against a persistent database:

```powershell
python -m alembic upgrade head
```

## Local Smoke Run

After installing the package in editable mode:

```powershell
python -m weatherpulse
```

Expected output:

```text
weatherpulse-enterprise (local): foundation
```
