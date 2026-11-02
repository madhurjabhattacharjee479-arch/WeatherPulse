from weatherpulse.config import load_openweather_settings


def test_openweather_settings_use_spec_environment_variables(monkeypatch) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "spec-key")
    monkeypatch.setenv("OPENWEATHER_BASE_URL", "https://api.openweathermap.org")
    monkeypatch.setenv("OPENWEATHER_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("OPENWEATHER_MAX_RETRIES", "5")
    monkeypatch.setenv("OPENWEATHER_RETRY_BACKOFF", "3")

    settings = load_openweather_settings()

    assert settings.api_key == "spec-key"
    assert settings.base_url == "https://api.openweathermap.org"
    assert settings.timeout_seconds == 15.0
    assert settings.max_retries == 5
    assert settings.retry_backoff == 3.0


def test_openweather_settings_support_legacy_environment_variables(monkeypatch) -> None:
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    monkeypatch.delenv("OPENWEATHER_BASE_URL", raising=False)
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", "legacy-key")
    monkeypatch.setenv("OPENWEATHERMAP_BASE_URL", "https://api.openweathermap.org/data/2.5")

    settings = load_openweather_settings()

    assert settings.api_key == "legacy-key"
    assert settings.base_url == "https://api.openweathermap.org"
