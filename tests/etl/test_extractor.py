from weatherpulse.etl.extractor import WeatherExtractor
from weatherpulse.etl.models import ExtractionStatus
from tests.etl.conftest import MockWeatherClient, make_weather_result, city_not_found_error


def test_extract_multiple_cities_successfully() -> None:
    client = MockWeatherClient(
        {
            "London,GB": make_weather_result(city_query="London,GB"),
            "Delhi,IN": make_weather_result(city_query="Delhi,IN"),
        }
    )
    extractor = WeatherExtractor(client)

    batch = extractor.extract_cities(["London,GB", "Delhi,IN"])

    assert batch.records_extracted == 2
    assert batch.records_failed == 0
    assert all(result.status == ExtractionStatus.SUCCESS for result in batch.results)


def test_one_city_failure_while_others_succeed(city_not_found_error) -> None:
    client = MockWeatherClient(
        {
            "London,GB": make_weather_result(city_query="London,GB"),
            "Unknown": city_not_found_error,
        }
    )
    extractor = WeatherExtractor(client)

    batch = extractor.extract_cities(["London,GB", "Unknown"])

    assert batch.records_extracted == 1
    assert batch.records_failed == 1
    assert batch.results[0].metadata is not None
    assert batch.results[0].metadata.http_status == 200
    assert batch.results[1].error_type == "CityNotFoundError"
    assert batch.results[1].metadata is not None
    assert batch.results[1].metadata.success is False


def test_propagates_safe_metadata() -> None:
    result = make_weather_result(city_query="London,GB")
    client = MockWeatherClient({"London,GB": result})
    extractor = WeatherExtractor(client)

    batch = extractor.extract_cities(["London,GB"])

    assert batch.results[0].metadata == result.metadata
    assert batch.results[0].weather_result == result.observation
