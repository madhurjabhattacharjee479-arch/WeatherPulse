"""Create initial WeatherPulse database schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-15 02:22:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("latitude", sa.Numeric(8, 5), nullable=False),
        sa.Column("longitude", sa.Numeric(8, 5), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90", name=op.f("ck_cities_latitude_range")),
        sa.CheckConstraint("longitude >= -180 AND longitude <= 180", name=op.f("ck_cities_longitude_range")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cities")),
        sa.UniqueConstraint("name", "country_code", "region", name="uq_cities_identity"),
    )
    op.create_index("ix_cities_country_name", "cities", ["country_code", "name"])

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_processed", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("finished_at IS NULL OR finished_at >= started_at", name=op.f("ck_pipeline_runs_pipeline_time_order")),
        sa.CheckConstraint("records_processed >= 0", name=op.f("ck_pipeline_runs_records_processed_non_negative")),
        sa.CheckConstraint("status IN ('pending', 'running', 'success', 'failed')", name=op.f("ck_pipeline_runs_pipeline_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_runs")),
    )
    op.create_index("ix_pipeline_runs_status_started_at", "pipeline_runs", ["status", "started_at"])

    op.create_table(
        "weather_conditions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("main", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("icon", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_conditions")),
        sa.UniqueConstraint("code", name=op.f("uq_weather_conditions_code")),
    )
    op.create_index("ix_weather_conditions_main", "weather_conditions", ["main"])

    op.create_table(
        "api_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("request_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_ms", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("response_ms IS NULL OR response_ms >= 0", name=op.f("ck_api_requests_response_ms_non_negative")),
        sa.CheckConstraint("status_code IS NULL OR (status_code >= 100 AND status_code <= 599)", name=op.f("ck_api_requests_status_code_range")),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"], name=op.f("fk_api_requests_city_id_cities"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_api_requests_pipeline_run_id_pipeline_runs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_requests")),
    )
    op.create_index("ix_api_requests_city_id", "api_requests", ["city_id"])
    op.create_index("ix_api_requests_pipeline_run_id", "api_requests", ["pipeline_run_id"])
    op.create_index("ix_api_requests_provider_endpoint", "api_requests", ["provider", "endpoint"])
    op.create_index("ix_api_requests_started_at", "api_requests", ["request_started_at"])

    op.create_table(
        "weather_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("condition_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("temperature_c", sa.Numeric(5, 2), nullable=False),
        sa.Column("feels_like_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("humidity_percent", sa.Integer(), nullable=False),
        sa.Column("pressure_hpa", sa.Integer(), nullable=False),
        sa.Column("wind_speed_mps", sa.Numeric(6, 2), nullable=False),
        sa.Column("wind_direction_deg", sa.Integer(), nullable=True),
        sa.Column("precipitation_mm", sa.Numeric(7, 2), nullable=True),
        sa.Column("cloud_cover_percent", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("cloud_cover_percent IS NULL OR (cloud_cover_percent >= 0 AND cloud_cover_percent <= 100)", name=op.f("ck_weather_observations_cloud_cover_range")),
        sa.CheckConstraint("humidity_percent >= 0 AND humidity_percent <= 100", name=op.f("ck_weather_observations_humidity_range")),
        sa.CheckConstraint("precipitation_mm IS NULL OR precipitation_mm >= 0", name=op.f("ck_weather_observations_precipitation_non_negative")),
        sa.CheckConstraint("pressure_hpa >= 300 AND pressure_hpa <= 1200", name=op.f("ck_weather_observations_pressure_range")),
        sa.CheckConstraint("temperature_c >= -100 AND temperature_c <= 80", name=op.f("ck_weather_observations_temperature_c_range")),
        sa.CheckConstraint("wind_direction_deg IS NULL OR (wind_direction_deg >= 0 AND wind_direction_deg <= 360)", name=op.f("ck_weather_observations_wind_direction_range")),
        sa.CheckConstraint("wind_speed_mps >= 0 AND wind_speed_mps <= 150", name=op.f("ck_weather_observations_wind_speed_range")),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"], name=op.f("fk_weather_observations_city_id_cities"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["condition_id"],
            ["weather_conditions.id"],
            name=op.f("fk_weather_observations_condition_id_weather_conditions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_observations")),
        sa.UniqueConstraint("city_id", "observed_at", name="uq_weather_observations_city_time"),
    )
    op.create_index("ix_weather_observations_city_observed_at", "weather_observations", ["city_id", "observed_at"])
    op.create_index("ix_weather_observations_condition_id", "weather_observations", ["condition_id"])
    op.create_index("ix_weather_observations_observed_at", "weather_observations", ["observed_at"])

    op.create_table(
        "data_quality_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=True),
        sa.Column("observation_id", sa.Integer(), nullable=True),
        sa.Column("check_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("severity IN ('info', 'warning', 'critical')", name=op.f("ck_data_quality_results_quality_severity")),
        sa.CheckConstraint("status IN ('pass', 'warn', 'fail')", name=op.f("ck_data_quality_results_quality_status")),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"], name=op.f("fk_data_quality_results_city_id_cities"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["observation_id"],
            ["weather_observations.id"],
            name=op.f("fk_data_quality_results_observation_id_weather_observations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_runs.id"],
            name=op.f("fk_data_quality_results_pipeline_run_id_pipeline_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_results")),
    )
    op.create_index("ix_data_quality_results_check_name", "data_quality_results", ["check_name"])
    op.create_index("ix_data_quality_results_observation_id", "data_quality_results", ["observation_id"])
    op.create_index("ix_data_quality_results_pipeline_status", "data_quality_results", ["pipeline_run_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_data_quality_results_pipeline_status", table_name="data_quality_results")
    op.drop_index("ix_data_quality_results_observation_id", table_name="data_quality_results")
    op.drop_index("ix_data_quality_results_check_name", table_name="data_quality_results")
    op.drop_table("data_quality_results")

    op.drop_index("ix_weather_observations_observed_at", table_name="weather_observations")
    op.drop_index("ix_weather_observations_condition_id", table_name="weather_observations")
    op.drop_index("ix_weather_observations_city_observed_at", table_name="weather_observations")
    op.drop_table("weather_observations")

    op.drop_index("ix_api_requests_started_at", table_name="api_requests")
    op.drop_index("ix_api_requests_provider_endpoint", table_name="api_requests")
    op.drop_index("ix_api_requests_pipeline_run_id", table_name="api_requests")
    op.drop_index("ix_api_requests_city_id", table_name="api_requests")
    op.drop_table("api_requests")

    op.drop_index("ix_weather_conditions_main", table_name="weather_conditions")
    op.drop_table("weather_conditions")

    op.drop_index("ix_pipeline_runs_status_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_cities_country_name", table_name="cities")
    op.drop_table("cities")
