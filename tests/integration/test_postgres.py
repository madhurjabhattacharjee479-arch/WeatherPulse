
import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from weatherpulse.db.base import Base
from weatherpulse.db.models import City, WeatherCondition, WeatherObservation
from weatherpulse.repositories import (
    CityRepository,
    WeatherConditionRepository,
    WeatherObservationRepository,
)


@pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").startswith(("postgresql://", "postgresql+")),
    reason="PostgreSQL integration test requires a PostgreSQL DATABASE_URL",
)
def test_postgres_weather_observation_round_trip() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])

    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            session = Session(bind=connection, expire_on_commit=False)

            try:
                suffix = uuid4().hex[:12]

                city = CityRepository(session).create(
                    name=f"WPTest-{suffix}",
                    country_code="IN",
                    region="TEST",
                    latitude=Decimal("22.57260"),
                    longitude=Decimal("88.36390"),
                    timezone="Asia/Kolkata",
                )

                condition = WeatherConditionRepository(session).create(
                    code=f"WP-{suffix}",
                    main="Clear",
                    description="clear sky",
                    icon="01d",
                )

                observed_at = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

                observation = WeatherObservationRepository(session).create(
                    city_id=city.id,
                    condition_id=condition.id,
                    observed_at=observed_at,
                    temperature_c=Decimal("29.50"),
                    feels_like_c=Decimal("32.10"),
                    humidity_percent=65,
                    pressure_hpa=1011,
                    wind_speed_mps=Decimal("3.40"),
                    wind_direction_deg=180,
                    precipitation_mm=Decimal("0.00"),
                    cloud_cover_percent=20,
                )

                session.flush()
                observation_id = observation.id
                session.expire_all()

                retrieved = WeatherObservationRepository(session).get(observation_id)

                assert retrieved is not None
                assert retrieved.temperature_c == Decimal("29.50")
                assert retrieved.humidity_percent == 65
                assert retrieved.city.name == f"WPTest-{suffix}"
                assert retrieved.condition.code == f"WP-{suffix}"

            finally:
                session.close()
                transaction.rollback()

    finally:
        engine.dispose()
