from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from weatherpulse.db.base import Base, UTCDateTime

if TYPE_CHECKING:
    from weatherpulse.db.models.city import City
    from weatherpulse.db.models.pipeline import DataQualityResult


class WeatherCondition(Base):
    """Normalized weather condition codes and descriptions."""

    __tablename__ = "weather_conditions"
    __table_args__ = (Index("ix_weather_conditions_main", "main"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    main: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(20))
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    observations: Mapped[list["WeatherObservation"]] = relationship(back_populates="condition")


class WeatherObservation(Base):
    """Weather measurement for one city at one observed timestamp."""

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("city_id", "observed_at", name="uq_weather_observations_city_time"),
        CheckConstraint("temperature_c >= -100 AND temperature_c <= 80", name="temperature_c_range"),
        CheckConstraint("humidity_percent >= 0 AND humidity_percent <= 100", name="humidity_range"),
        CheckConstraint("pressure_hpa >= 300 AND pressure_hpa <= 1200", name="pressure_range"),
        CheckConstraint("wind_speed_mps >= 0 AND wind_speed_mps <= 150", name="wind_speed_range"),
        CheckConstraint(
            "wind_direction_deg IS NULL OR (wind_direction_deg >= 0 AND wind_direction_deg <= 360)",
            name="wind_direction_range",
        ),
        CheckConstraint("precipitation_mm IS NULL OR precipitation_mm >= 0", name="precipitation_non_negative"),
        CheckConstraint(
            "cloud_cover_percent IS NULL OR (cloud_cover_percent >= 0 AND cloud_cover_percent <= 100)",
            name="cloud_cover_range",
        ),
        Index("ix_weather_observations_city_observed_at", "city_id", "observed_at"),
        Index("ix_weather_observations_observed_at", "observed_at"),
        Index("ix_weather_observations_condition_id", "condition_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id", ondelete="CASCADE"), nullable=False)
    condition_id: Mapped[int] = mapped_column(
        ForeignKey("weather_conditions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    temperature_c: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    feels_like_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    pressure_hpa: Mapped[int] = mapped_column(Integer, nullable=False)
    wind_speed_mps: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    wind_direction_deg: Mapped[int | None] = mapped_column(Integer)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2))
    cloud_cover_percent: Mapped[int | None] = mapped_column(Integer)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    city: Mapped["City"] = relationship(back_populates="observations")
    condition: Mapped["WeatherCondition"] = relationship(back_populates="observations")
    data_quality_results: Mapped[list["DataQualityResult"]] = relationship(
        back_populates="observation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
