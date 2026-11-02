"""Extract weather data via the Step 4 OpenWeatherMap client."""

from __future__ import annotations

import logging

from weatherpulse.ingestion.exceptions import WeatherAPIError, WeatherPulseError
from weatherpulse.ingestion.openweather_client import OpenWeatherClient
from weatherpulse.ingestion.schemas import CurrentWeatherResult
from weatherpulse.etl.models import CityExtractionResult, ExtractionBatchResult, ExtractionStatus

logger = logging.getLogger(__name__)


class WeatherExtractor:
    """Orchestrates city-by-city extraction through OpenWeatherClient."""

    def __init__(self, client: OpenWeatherClient) -> None:
        self._client = client

    def extract_cities(self, city_queries: list[str]) -> ExtractionBatchResult:
        """Extract current weather for each configured city independently."""
        results: list[CityExtractionResult] = []
        records_extracted = 0
        records_failed = 0

        for city_query in city_queries:
            logger.info("ETL extraction started for city=%s", city_query)
            result = self._extract_single_city(city_query)
            results.append(result)

            if result.status == ExtractionStatus.SUCCESS:
                records_extracted += 1
                logger.info("ETL extraction completed for city=%s", city_query)
            else:
                records_failed += 1
                logger.warning(
                    "ETL extraction failed for city=%s error_type=%s",
                    city_query,
                    result.error_type,
                )

        return ExtractionBatchResult(
            results=results,
            records_extracted=records_extracted,
            records_failed=records_failed,
        )

    def _extract_single_city(self, city_query: str) -> CityExtractionResult:
        try:
            weather_result: CurrentWeatherResult = self._client.get_current_weather(city_query)
        except WeatherAPIError as exc:
            metadata = exc.metadata
            return CityExtractionResult(
                city_query=city_query,
                status=ExtractionStatus.FAILED,
                metadata=metadata,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        except WeatherPulseError as exc:
            return CityExtractionResult(
                city_query=city_query,
                status=ExtractionStatus.FAILED,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

        return CityExtractionResult(
            city_query=city_query,
            status=ExtractionStatus.SUCCESS,
            weather_result=weather_result.observation,
            metadata=weather_result.metadata,
        )
