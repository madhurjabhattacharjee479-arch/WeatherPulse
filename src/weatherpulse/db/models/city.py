from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from weatherpulse.db.base import Base

if TYPE_CHECKING:
    from weatherpulse.db.models.pipeline import ApiRequest, DataQualityResult
    from weatherpulse.db.models.weather import WeatherObservation


class City(Base):
    """City metadata for weather collection and querying."""

    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("name", "country_code", "region", name="uq_cities_identity"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
        Index("ix_cities_country_name", "country_code", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    region: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    latitude: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(8, 5), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    observations: Mapped[list["WeatherObservation"]] = relationship(
        back_populates="city",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    api_requests: Mapped[list["ApiRequest"]] = relationship(back_populates="city")
    data_quality_results: Mapped[list["DataQualityResult"]] = relationship(back_populates="city")
