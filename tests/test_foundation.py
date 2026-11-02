from weatherpulse import __version__
from weatherpulse.app import application_status
from weatherpulse.config import load_settings


def test_version_is_defined() -> None:
    assert __version__ == "0.1.0"


def test_application_status_uses_environment(monkeypatch) -> None:
    monkeypatch.setenv("WEATHERPULSE_ENV", "test")

    status = application_status()

    assert status == {
        "service": "weatherpulse-enterprise",
        "environment": "test",
        "status": "foundation",
    }


def test_settings_use_safe_local_defaults(monkeypatch) -> None:
    monkeypatch.delenv("WEATHERPULSE_ENV", raising=False)
    monkeypatch.delenv("WEATHERPULSE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("WEATHERPULSE_DATABASE_URL", raising=False)

    settings = load_settings()

    assert settings.environment == "local"
    assert settings.log_level == "INFO"
    assert settings.database_url == "sqlite:///./data/weatherpulse.db"


def test_database_url_prefers_standard_environment_variable(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./standard.db")
    monkeypatch.setenv("WEATHERPULSE_DATABASE_URL", "sqlite:///./legacy.db")

    settings = load_settings()

    assert settings.database_url == "sqlite:///./standard.db"
