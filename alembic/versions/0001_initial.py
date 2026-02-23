"""Initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-02-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_channels_name", "channels", ["name"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("telegram_msg_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rewritten_text", sa.Text(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("duplicate_of", sa.String(length=255), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("channel_id", "telegram_msg_id", name="uq_posts_channel_msg"),
    )
    op.create_index("ix_posts_channel_id", "posts", ["channel_id"])
    op.create_index("ix_posts_processed_at", "posts", ["processed_at"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "webapp_settings",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("style_channel", sa.String(length=255), nullable=True),
        sa.Column("sources_csv", sa.Text(), nullable=True),
        sa.Column("limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("with_images", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "webapp_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("style_channel", sa.String(length=255), nullable=False),
        sa.Column("sources_csv", sa.Text(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False),
        sa.Column("with_images", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'started'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("posts_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_webapp_runs_user_id", "webapp_runs", ["user_id"])
    op.create_index("ix_webapp_runs_created_at", "webapp_runs", ["created_at"])

    op.create_table(
        "schema_meta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("schema_meta")
    op.drop_index("ix_webapp_runs_created_at", table_name="webapp_runs")
    op.drop_index("ix_webapp_runs_user_id", table_name="webapp_runs")
    op.drop_table("webapp_runs")
    op.drop_table("webapp_settings")
    op.drop_index("ix_posts_created_at", table_name="posts")
    op.drop_index("ix_posts_processed_at", table_name="posts")
    op.drop_index("ix_posts_channel_id", table_name="posts")
    op.drop_table("posts")
    op.drop_index("ix_channels_name", table_name="channels")
    op.drop_table("channels")
