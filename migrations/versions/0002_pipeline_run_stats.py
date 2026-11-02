"""Add pipeline run statistics and partial_success status.

Revision ID: 0002_pipeline_run_stats
Revises: 0001_initial_schema
Create Date: 2026-09-15 03:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_pipeline_run_stats"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.drop_constraint("pipeline_status", type_="check")
        batch_op.create_check_constraint(
            "pipeline_status",
            "status IN ('pending', 'running', 'success', 'partial_success', 'failed')",
        )
        batch_op.add_column(
            sa.Column("records_extracted", sa.Integer(), nullable=False, server_default="0"),
        )
        batch_op.add_column(
            sa.Column("records_validated", sa.Integer(), nullable=False, server_default="0"),
        )
        batch_op.add_column(
            sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        )
        batch_op.add_column(
            sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        )
        batch_op.create_check_constraint(
            "records_extracted_non_negative",
            "records_extracted >= 0",
        )
        batch_op.create_check_constraint(
            "records_validated_non_negative",
            "records_validated >= 0",
        )
        batch_op.create_check_constraint(
            "records_rejected_non_negative",
            "records_rejected >= 0",
        )
        batch_op.create_check_constraint(
            "execution_time_non_negative",
            "execution_time_ms IS NULL OR execution_time_ms >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("pipeline_runs", schema=None) as batch_op:
        batch_op.drop_constraint("execution_time_non_negative", type_="check")
        batch_op.drop_constraint("records_rejected_non_negative", type_="check")
        batch_op.drop_constraint("records_validated_non_negative", type_="check")
        batch_op.drop_constraint("records_extracted_non_negative", type_="check")
        batch_op.drop_column("execution_time_ms")
        batch_op.drop_column("records_rejected")
        batch_op.drop_column("records_validated")
        batch_op.drop_column("records_extracted")
        batch_op.drop_constraint("pipeline_status", type_="check")
        batch_op.create_check_constraint(
            "pipeline_status",
            "status IN ('pending', 'running', 'success', 'failed')",
        )
