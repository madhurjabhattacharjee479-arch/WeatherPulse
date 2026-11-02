from datetime import UTC, datetime

from weatherpulse.etl.models import PipelineStatus
from weatherpulse.etl.pipeline import WeatherETLPipeline
from weatherpulse.ingestion.exceptions import CityNotFoundError
from weatherpulse.ingestion.schemas import WeatherRequestMetadata
from weatherpulse.repositories import PipelineRunRepository, WeatherObservationRepository
from tests.etl.conftest import MockWeatherClient, OBSERVED_AT, REQUESTED_AT, make_observation, make_weather_result


def test_pipeline_complete_success(session_factory) -> None:
    client = MockWeatherClient(
        {
            "London,GB": make_weather_result(city_query="London,GB"),
            "Delhi,IN": make_weather_result(
                city_query="Delhi,IN",
                observation=make_observation(city_name="Delhi", country_code="IN"),
            ),
        }
    )
    pipeline = WeatherETLPipeline(client=client, session_factory=session_factory, cities=["London,GB", "Delhi,IN"])

    result = pipeline.run()

    assert result.status == PipelineStatus.SUCCESS
    assert result.records_extracted == 2
    assert result.records_validated == 2
    assert result.records_rejected == 0
    assert result.records_loaded == 2
    assert result.execution_time_ms >= 0

    with session_factory() as session:
        run = PipelineRunRepository(session).get(result.run_id)

    assert run is not None
    assert run.status == "success"
    assert run.records_processed == 2
    assert run.records_extracted == 2


def test_pipeline_partial_success(session_factory, city_not_found_error) -> None:
    client = MockWeatherClient(
        {
            "London,GB": make_weather_result(city_query="London,GB"),
            "Unknown": city_not_found_error,
        }
    )
    pipeline = WeatherETLPipeline(
        client=client,
        session_factory=session_factory,
        cities=["London,GB", "Unknown"],
    )

    result = pipeline.run()

    assert result.status == PipelineStatus.PARTIAL_SUCCESS
    assert result.records_extracted == 1
    assert result.records_loaded == 1
    assert result.records_failed >= 1

    with session_factory() as session:
        run = PipelineRunRepository(session).get(result.run_id)

    assert run is not None
    assert run.status == "partial_success"


def test_pipeline_total_failure(session_factory) -> None:
    error = CityNotFoundError(
        "missing",
        metadata=WeatherRequestMetadata(
            requested_at=REQUESTED_AT,
            city="Unknown",
            endpoint="/data/2.5/weather",
            http_status=404,
            success=False,
        ),
    )
    client = MockWeatherClient({"Unknown": error})
    pipeline = WeatherETLPipeline(client=client, session_factory=session_factory, cities=["Unknown"])

    result = pipeline.run()

    assert result.status == PipelineStatus.FAILED
    assert result.records_loaded == 0

    with session_factory() as session:
        run = PipelineRunRepository(session).get(result.run_id)

    assert run is not None
    assert run.status == "failed"


def test_pipeline_idempotent_second_run(session_factory) -> None:
    client = MockWeatherClient({"London,GB": make_weather_result(city_query="London,GB")})
    pipeline = WeatherETLPipeline(client=client, session_factory=session_factory, cities=["London,GB"])

    first = pipeline.run()
    second = pipeline.run()

    assert first.records_loaded == 1
    assert second.records_duplicates == 1
    assert second.records_loaded == 0

    with session_factory() as session:
        observations = WeatherObservationRepository(session).list_for_city(city_id=first.city_results[0].city_id)

    assert len(observations) == 1


def test_pipeline_rejected_validation_counts(session_factory) -> None:
    bad_observation = make_observation(humidity_percent=200)
    client = MockWeatherClient(
        {
            "Bad,GB": make_weather_result(city_query="Bad,GB", observation=bad_observation),
            "London,GB": make_weather_result(city_query="London,GB"),
        }
    )
    pipeline = WeatherETLPipeline(
        client=client,
        session_factory=session_factory,
        cities=["Bad,GB", "London,GB"],
    )

    result = pipeline.run()

    assert result.records_rejected == 1
    assert result.records_loaded == 1
    assert result.status == PipelineStatus.PARTIAL_SUCCESS


def test_pipeline_preserves_observed_at(session_factory) -> None:
    observed = datetime(2019, 5, 1, 10, 30, tzinfo=UTC)
    client = MockWeatherClient(
        {
            "London,GB": make_weather_result(
                city_query="London,GB",
                observation=make_observation(observed_at=observed),
            )
        }
    )
    pipeline = WeatherETLPipeline(client=client, session_factory=session_factory, cities=["London,GB"])
    result = pipeline.run()

    with session_factory() as session:
        observation = WeatherObservationRepository(session).get(result.city_results[0].observation_id)

    assert observation is not None
    assert observation.observed_at == observed
    assert observation.observed_at != REQUESTED_AT
