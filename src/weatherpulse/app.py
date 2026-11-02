from weatherpulse.config import load_settings


def application_status() -> dict[str, str]:
    """Return a minimal status payload for local foundation checks."""
    settings = load_settings()
    return {
        "service": "weatherpulse-enterprise",
        "environment": settings.environment,
        "status": "foundation",
    }


def main() -> None:
    status = application_status()
    print(f"{status['service']} ({status['environment']}): {status['status']}")
