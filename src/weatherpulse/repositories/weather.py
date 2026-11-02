from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from weatherpulse.db.models import WeatherCondition, WeatherObservation


class WeatherConditionRepository:
    """Data-access methods for normalized weather conditions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        code: str,
        main: str,
        description: str,
        icon: str | None = None,
    ) -> WeatherCondition:
        condition = WeatherCondition(code=code, main=main, description=description, icon=icon)
        self.session.add(condition)
        self.session.flush()
        return condition

    def get(self, condition_id: int) -> WeatherCondition | None:
        return self.session.get(WeatherCondition, condition_id)

    def get_by_code(self, code: str) -> WeatherCondition | None:
        statement = select(WeatherCondition).where(WeatherCondition.code == code)
        return self.session.execute(statement).scalar_one_or_none()


class WeatherObservationRepository:
    """Data-access methods for weather observations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        city_id: int,
        condition_id: int,
        observed_at: datetime,
        temperature_c: Decimal,
        humidity_percent: int,
        pressure_hpa: int,
        wind_speed_mps: Decimal,
        feels_like_c: Decimal | None = None,
        wind_direction_deg: int | None = None,
        precipitation_mm: Decimal | None = None,
        cloud_cover_percent: int | None = None,
    ) -> WeatherObservation:
        observation = WeatherObservation(
            city_id=city_id,
            condition_id=condition_id,
            observed_at=observed_at,
            temperature_c=temperature_c,
            feels_like_c=feels_like_c,
            humidity_percent=humidity_percent,
            pressure_hpa=pressure_hpa,
            wind_speed_mps=wind_speed_mps,
            wind_direction_deg=wind_direction_deg,
            precipitation_mm=precipitation_mm,
            cloud_cover_percent=cloud_cover_percent,
        )
        self.session.add(observation)
        self.session.flush()
        return observation

    def get(self, observation_id: int) -> WeatherObservation | None:
        statement = (
            select(WeatherObservation)
            .options(joinedload(WeatherObservation.city), joinedload(WeatherObservation.condition))
            .where(WeatherObservation.id == observation_id)
        )
        return self.session.execute(statement).scalar_one_or_none()

    def get_for_city_at(self, *, city_id: int, observed_at: datetime) -> WeatherObservation | None:
        statement = select(WeatherObservation).where(
            WeatherObservation.city_id == city_id,
            WeatherObservation.observed_at == observed_at,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list_for_city(
        self,
        *,
        city_id: int,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[WeatherObservation]:
        statement = (
            select(WeatherObservation)
            .where(WeatherObservation.city_id == city_id)
            .order_by(WeatherObservation.observed_at)
        )

        if start_at is not None:
            statement = statement.where(WeatherObservation.observed_at >= start_at)
        if end_at is not None:
            statement = statement.where(WeatherObservation.observed_at <= end_at)
        if limit is not None:
            statement = statement.limit(limit)

        return list(self.session.execute(statement).scalars())
