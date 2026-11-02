from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from weatherpulse.db.models import City


class CityRepository:
    """Data-access methods for city records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        name: str,
        country_code: str,
        latitude: Decimal,
        longitude: Decimal,
        region: str = "",
        timezone: str = "UTC",
    ) -> City:
        city = City(
            name=name,
            country_code=country_code.upper(),
            region=region,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
        )
        self.session.add(city)
        self.session.flush()
        return city

    def get(self, city_id: int) -> City | None:
        return self.session.get(City, city_id)

    def get_by_identity(self, *, name: str, country_code: str, region: str = "") -> City | None:
        statement = select(City).where(
            City.name == name,
            City.country_code == country_code.upper(),
            City.region == region,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list_by_country(self, country_code: str) -> list[City]:
        statement = select(City).where(City.country_code == country_code.upper()).order_by(City.name)
        return list(self.session.execute(statement).scalars())
