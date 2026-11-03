from types import SimpleNamespace

import pytest

from weatherpulse.app import main
from weatherpulse.etl.models import PipelineStatus


def test_run_rejects_missing_api_key(monkeypatch, capsys) -> None:
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)
    monkeypatch.setenv("WEATHERPULSE_ETL_CITIES", "Kolkata")

    exit_code = main(["run"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "OPENWEATHER_API_KEY" in captured.err


def test_run_rejects_missing_cities(monkeypatch, capsys) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-only-placeholder")
    monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)
    monkeypatch.delenv("WEATHERPULSE_ETL_CITIES", raising=False)

    exit_code = main(["run"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "WEATHERPULSE_ETL_CITIES" in captured.err


@pytest.mark.parametrize(
    ("pipeline_status", "expected_exit_code", "loaded", "failed"),
    [
        (PipelineStatus.SUCCESS, 0, 1, 0),
        (PipelineStatus.PARTIAL_SUCCESS, 1, 1, 1),
        (PipelineStatus.FAILED, 1, 0, 1),
    ],
)
def test_run_returns_exit_code_for_pipeline_outcome(
    monkeypatch,
    capsys,
    pipeline_status,
    expected_exit_code,
    loaded,
    failed,
) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-only-placeholder")
    monkeypatch.setenv("WEATHERPULSE_ETL_CITIES", "Kolkata")

    fake_engine = SimpleNamespace(dispose=lambda: None)

    class FakeClient:
        def __init__(self, settings):
            self.settings = settings

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return SimpleNamespace(
                run_id=123,
                status=pipeline_status,
                records_extracted=2,
                records_validated=2,
                records_rejected=0,
                records_loaded=loaded,
                records_duplicates=0,
                records_failed=failed,
                execution_time_ms=100,
                error_message=None,
            )

    monkeypatch.setattr(
        "weatherpulse.db.engine.create_engine_from_url",
        lambda database_url: fake_engine,
    )
    monkeypatch.setattr(
        "weatherpulse.db.session.get_session_factory",
        lambda engine: "fake-session-factory",
    )
    monkeypatch.setattr(
        "weatherpulse.ingestion.openweather_client.OpenWeatherClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "weatherpulse.etl.pipeline.WeatherETLPipeline",
        FakePipeline,
    )

    exit_code = main(["run"])

    captured = capsys.readouterr()

    assert exit_code == expected_exit_code
    assert pipeline_status.value in captured.out
    assert f"loaded={loaded}" in captured.out
    assert f"failed={failed}" in captured.out
