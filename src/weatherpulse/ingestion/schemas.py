"""Pydantic schemas for OpenWeatherMap ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WeatherConditionInfo(BaseModel):
    """Normalized weather condition from the provider response."""

    model_config = ConfigDict(frozen=True)

    id: int
    main: str
    description: str
    icon: str | None = None


class WeatherObservationData(BaseModel):
    """Validated internal representation of a current weather observation."""

    model_config = ConfigDict(frozen=True)

    city_name: str
    country_code: str
    latitude: float
    longitude: float
    observed_at: datetime
    temperature_c: float
    feels_like_c: float | None = None
    temp_min_c: float | None = None
    temp_max_c: float | None = None
    pressure_hpa: int
    humidity_percent: int
    visibility_m: int | None = None
    wind_speed_mps: float | None = None
    wind_direction_deg: int | None = None
    cloudiness_percent: int | None = None
    rain_1h_mm: float | None = None
    snow_1h_mm: float | None = None
    weather_conditions: list[WeatherConditionInfo]


class WeatherRequestMetadata(BaseModel):
    """Safe request metadata for future pipeline persistence."""

    model_config = ConfigDict(frozen=True)

    requested_at: datetime
    city: str
    endpoint: str
    http_status: int | None = None
    response_time_ms: int | None = None
    success: bool
    retry_count: int = 0
    error_type: str | None = None
    error_message: str | None = None


class CurrentWeatherResult(BaseModel):
    """Successful weather fetch with observation data and request metadata."""

    model_config = ConfigDict(frozen=True)

    observation: WeatherObservationData
    metadata: WeatherRequestMetadata


class _CoordinatesResponse(BaseModel):
    lat: float
    lon: float


class _MainWeatherResponse(BaseModel):
    temp: float
    feels_like: float | None = None
    temp_min: float | None = None
    temp_max: float | None = None
    pressure: int
    humidity: int


class _WindResponse(BaseModel):
    speed: float | None = None
    deg: int | None = None


class _CloudsResponse(BaseModel):
    all: int


class _PrecipitationVolumeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    one_hour_mm: float | None = Field(default=None, alias="1h")


class _SysResponse(BaseModel):
    country: str


class _WeatherItemResponse(BaseModel):
    id: int
    main: str
    description: str
    icon: str | None = None


class OpenWeatherCurrentResponse(BaseModel):
    """Validated OpenWeatherMap /data/2.5/weather response."""

    coord: _CoordinatesResponse
    weather: list[_WeatherItemResponse]
    main: _MainWeatherResponse
    visibility: int | None = None
    wind: _WindResponse | None = None
    clouds: _CloudsResponse | None = None
    rain: _PrecipitationVolumeResponse | None = None
    snow: _PrecipitationVolumeResponse | None = None
    dt: int
    sys: _SysResponse
    name: str

    @field_validator("weather")
    @classmethod
    def validate_weather_not_empty(cls, value: list[_WeatherItemResponse]) -> list[_WeatherItemResponse]:
        if not value:
            raise ValueError("weather must contain at least one condition")
        return value

    def to_observation_data(self) -> WeatherObservationData:
        """Convert a validated provider response into the internal model."""
        return WeatherObservationData(
            city_name=self.name,
            country_code=self.sys.country,
            latitude=self.coord.lat,
            longitude=self.coord.lon,
            observed_at=datetime.fromtimestamp(self.dt, tz=UTC),
            temperature_c=self.main.temp,
            feels_like_c=self.main.feels_like,
            temp_min_c=self.main.temp_min,
            temp_max_c=self.main.temp_max,
            pressure_hpa=self.main.pressure,
            humidity_percent=self.main.humidity,
            visibility_m=self.visibility,
            wind_speed_mps=self.wind.speed if self.wind else None,
            wind_direction_deg=self.wind.deg if self.wind else None,
            cloudiness_percent=self.clouds.all if self.clouds else None,
            rain_1h_mm=self.rain.one_hour_mm if self.rain else None,
            snow_1h_mm=self.snow.one_hour_mm if self.snow else None,
            weather_conditions=[
                WeatherConditionInfo(
                    id=item.id,
                    main=item.main,
                    description=item.description,
                    icon=item.icon,
                )
                for item in self.weather
            ],
        )


def parse_openweather_response(payload: dict[str, Any]) -> WeatherObservationData:
    """Validate provider JSON and return the internal observation model."""
    validated = OpenWeatherCurrentResponse.model_validate(payload)
    return validated.to_observation_data()
