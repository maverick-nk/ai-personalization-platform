"""Initial schema: consent and audit_log tables

Revision ID: 001
Revises:
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # consent — non-partitioned; one row per user, no bloat risk
    op.create_table(
        "consent",
        sa.Column("user_pseudo_id", sa.String(), nullable=False),
        sa.Column("consent_granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("user_pseudo_id"),
    )

    # audit_log — partitioned by timestamp (RANGE) for scalable TTL cleanup.
    #
    # Two constraints of PostgreSQL range-partitioned tables drive the schema here:
    #   1. SERIAL / SEQUENCE defaults don't propagate to child partitions — use
    #      GENERATED ALWAYS AS IDENTITY instead (supported since PG 10).
    #   2. Every unique/PK constraint must include the partition key (timestamp),
    #      so the PK is composite (id, timestamp).
    #
    # Monthly partitions and 6-month TTL are managed at runtime by app/partitions.py,
    # not in the migration, so the table starts with no child partitions here.
    op.execute(sa.text("""
        CREATE TABLE audit_log (
            id              INTEGER      GENERATED ALWAYS AS IDENTITY,
            user_pseudo_id  VARCHAR      NOT NULL,
            action          VARCHAR(10)  NOT NULL,
            timestamp       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            reason          VARCHAR(255),
            PRIMARY KEY (id, timestamp)
        ) PARTITION BY RANGE (timestamp)
    """))

    # Index on user_pseudo_id is created on the parent table and automatically
    # inherited by every current and future monthly partition.
    op.create_index("audit_log_user_idx", "audit_log", ["user_pseudo_id"])


def downgrade() -> None:
    op.drop_index("audit_log_user_idx", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_table("consent")
