from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from weatherpulse.db.session import session_scope
from weatherpulse.repositories import CityRepository, WeatherConditionRepository, WeatherObservationRepository


def create_city(session: Session):
    return CityRepository(session).create(
        name="Kolkata",
        country_code="IN",
        region="WB",
        latitude=Decimal("22.57260"),
        longitude=Decimal("88.36390"),
        timezone="Asia/Kolkata",
    )


def create_condition(session: Session):
    return WeatherConditionRepository(session).create(
        code="800",
        main="Clear",
        description="clear sky",
        icon="01d",
    )


def create_observation(
    session: Session,
    *,
    city_id: int,
    condition_id: int,
    observed_at: datetime | None = None,
    humidity_percent: int = 65,
    wind_speed_mps: Decimal = Decimal("3.40"),
    pressure_hpa: int = 1011,
):
    return WeatherObservationRepository(session).create(
        city_id=city_id,
        condition_id=condition_id,
        observed_at=observed_at or datetime(2026, 9, 15, 8, 0, 0),
        temperature_c=Decimal("29.50"),
        feels_like_c=Decimal("32.10"),
        humidity_percent=humidity_percent,
        pressure_hpa=pressure_hpa,
        wind_speed_mps=wind_speed_mps,
        wind_direction_deg=180,
        precipitation_mm=Decimal("0.00"),
        cloud_cover_percent=20,
    )


def test_successful_city_insertion(db_session: Session) -> None:
    city = create_city(db_session)

    assert city.id is not None
    assert city.country_code == "IN"


def test_duplicate_city_handling(db_session: Session) -> None:
    create_city(db_session)

    with pytest.raises(IntegrityError):
        create_city(db_session)


def test_valid_observation_insertion(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)

    observation = create_observation(db_session, city_id=city.id, condition_id=condition.id)

    assert observation.id is not None
    assert observation.city_id == city.id
    assert observation.condition_id == condition.id


def test_invalid_humidity(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)

    with pytest.raises(IntegrityError):
        create_observation(db_session, city_id=city.id, condition_id=condition.id, humidity_percent=101)


def test_invalid_wind_speed(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)

    with pytest.raises(IntegrityError):
        create_observation(
            db_session,
            city_id=city.id,
            condition_id=condition.id,
            wind_speed_mps=Decimal("-0.01"),
        )


def test_invalid_pressure(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)

    with pytest.raises(IntegrityError):
        create_observation(db_session, city_id=city.id, condition_id=condition.id, pressure_hpa=0)


def test_invalid_foreign_key(db_session: Session) -> None:
    condition = create_condition(db_session)

    with pytest.raises(IntegrityError):
        create_observation(db_session, city_id=999, condition_id=condition.id)


def test_observation_retrieval(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)
    observed_at = datetime(2026, 9, 15, 9, 0, 0)
    observation = create_observation(
        db_session,
        city_id=city.id,
        condition_id=condition.id,
        observed_at=observed_at,
    )

    repository = WeatherObservationRepository(db_session)

    assert repository.get(observation.id).id == observation.id
    assert repository.get_for_city_at(city_id=city.id, observed_at=observed_at).id == observation.id


def test_historical_retrieval(db_session: Session) -> None:
    city = create_city(db_session)
    condition = create_condition(db_session)
    start = datetime(2026, 9, 15, 0, 0, 0)

    first = create_observation(
        db_session,
        city_id=city.id,
        condition_id=condition.id,
        observed_at=start,
    )
    second = create_observation(
        db_session,
        city_id=city.id,
        condition_id=condition.id,
        observed_at=start + timedelta(hours=1),
    )
    create_observation(
        db_session,
        city_id=city.id,
        condition_id=condition.id,
        observed_at=start + timedelta(hours=2),
    )

    observations = WeatherObservationRepository(db_session).list_for_city(
        city_id=city.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
    )

    assert [observation.id for observation in observations] == [first.id, second.id]


def test_transaction_rollback_behavior(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError):
        with session_scope(session_factory) as session:
            create_city(session)
            raise RuntimeError("force rollback")

    with session_factory() as session:
        city = CityRepository(session).get_by_identity(name="Kolkata", country_code="IN", region="WB")

    assert city is None
