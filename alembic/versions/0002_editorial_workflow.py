"""Editorial workflow tables

Revision ID: 0002_editorial_workflow
Revises: 0001_initial
Create Date: 2026-03-11 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_editorial_workflow"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "editorial_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel_ref", sa.String(length=255), nullable=False),
        sa.Column("channel_title", sa.String(length=255), nullable=True),
        sa.Column("telegram_id", sa.Integer(), nullable=True),
        sa.Column(
            "added_via",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "channel_ref", name="uq_editorial_sources_user_ref"),
    )
    op.create_index("ix_editorial_sources_user_id", "editorial_sources", ["user_id"])

    op.create_table(
        "editorial_source_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("telegram_msg_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["editorial_sources.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "source_id",
            "telegram_msg_id",
            name="uq_editorial_source_posts_source_msg",
        ),
    )
    op.create_index(
        "ix_editorial_source_posts_source_id", "editorial_source_posts", ["source_id"]
    )
    op.create_index(
        "ix_editorial_source_posts_published_at",
        "editorial_source_posts",
        ["published_at"],
    )
    op.create_index(
        "ix_editorial_source_posts_imported_at",
        "editorial_source_posts",
        ["imported_at"],
    )

    op.create_table(
        "editorial_topic_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("style_channel", sa.String(length=255), nullable=True),
        sa.Column("sources_csv", sa.Text(), nullable=False),
        sa.Column(
            "window_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'started'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "posts_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "categories_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_editorial_topic_reports_user_id", "editorial_topic_reports", ["user_id"]
    )
    op.create_index(
        "ix_editorial_topic_reports_created_at",
        "editorial_topic_reports",
        ["created_at"],
    )

    op.create_table(
        "editorial_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "post_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["report_id"], ["editorial_topic_reports.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "report_id",
            "slug",
            name="uq_editorial_topics_report_slug",
        ),
    )
    op.create_index("ix_editorial_topics_report_id", "editorial_topics", ["report_id"])
    op.create_index("ix_editorial_topics_slug", "editorial_topics", ["slug"])

    op.create_table(
        "editorial_topic_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["topic_id"], ["editorial_topics.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["editorial_source_posts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "topic_id",
            "post_id",
            name="uq_editorial_topic_posts_topic_post",
        ),
    )
    op.create_index(
        "ix_editorial_topic_posts_topic_id", "editorial_topic_posts", ["topic_id"]
    )
    op.create_index(
        "ix_editorial_topic_posts_post_id", "editorial_topic_posts", ["post_id"]
    )

    op.create_table(
        "editorial_generation_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("style_channel", sa.String(length=255), nullable=False),
        sa.Column("selected_post_ids_csv", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'started'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "outputs_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_editorial_generation_runs_user_id",
        "editorial_generation_runs",
        ["user_id"],
    )
    op.create_index(
        "ix_editorial_generation_runs_created_at",
        "editorial_generation_runs",
        ["created_at"],
    )

    op.create_table(
        "editorial_generation_outputs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("source_post_ids_csv", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("image_file", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["editorial_generation_runs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_editorial_generation_outputs_run_id",
        "editorial_generation_outputs",
        ["run_id"],
    )
    op.create_index(
        "ix_editorial_generation_outputs_created_at",
        "editorial_generation_outputs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_editorial_generation_outputs_created_at",
        table_name="editorial_generation_outputs",
    )
    op.drop_index(
        "ix_editorial_generation_outputs_run_id",
        table_name="editorial_generation_outputs",
    )
    op.drop_table("editorial_generation_outputs")

    op.drop_index(
        "ix_editorial_generation_runs_created_at",
        table_name="editorial_generation_runs",
    )
    op.drop_index(
        "ix_editorial_generation_runs_user_id",
        table_name="editorial_generation_runs",
    )
    op.drop_table("editorial_generation_runs")

    op.drop_index(
        "ix_editorial_topic_posts_post_id",
        table_name="editorial_topic_posts",
    )
    op.drop_index(
        "ix_editorial_topic_posts_topic_id",
        table_name="editorial_topic_posts",
    )
    op.drop_table("editorial_topic_posts")

    op.drop_index("ix_editorial_topics_slug", table_name="editorial_topics")
    op.drop_index("ix_editorial_topics_report_id", table_name="editorial_topics")
    op.drop_table("editorial_topics")

    op.drop_index(
        "ix_editorial_topic_reports_created_at",
        table_name="editorial_topic_reports",
    )
    op.drop_index(
        "ix_editorial_topic_reports_user_id",
        table_name="editorial_topic_reports",
    )
    op.drop_table("editorial_topic_reports")

    op.drop_index(
        "ix_editorial_source_posts_imported_at",
        table_name="editorial_source_posts",
    )
    op.drop_index(
        "ix_editorial_source_posts_published_at",
        table_name="editorial_source_posts",
    )
    op.drop_index(
        "ix_editorial_source_posts_source_id",
        table_name="editorial_source_posts",
    )
    op.drop_table("editorial_source_posts")

    op.drop_index("ix_editorial_sources_user_id", table_name="editorial_sources")
    op.drop_table("editorial_sources")
