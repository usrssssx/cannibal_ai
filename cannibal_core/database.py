from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sql_text,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .config import Settings


class Base(DeclarativeBase):
    pass


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    posts: Mapped[list["Post"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint("channel_id", "telegram_msg_id", name="uq_posts_channel_msg"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"), index=True
    )
    telegram_msg_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("0"),
    )
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    channel: Mapped["Channel"] = relationship(back_populates="posts")


class WebAppSettings(Base):
    __tablename__ = "webapp_settings"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    style_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sources_csv: Mapped[str | None] = mapped_column(Text, nullable=True)
    limit: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=sql_text("1"),
    )
    with_images: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WebAppRun(Base):
    __tablename__ = "webapp_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    style_channel: Mapped[str] = mapped_column(String(255), nullable=False)
    sources_csv: Mapped[str] = mapped_column(Text, nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    with_images: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=sql_text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="started",
        server_default=sql_text("'started'"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )


class EditorialSource(Base):
    __tablename__ = "editorial_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "channel_ref", name="uq_editorial_sources_user_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    channel_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    added_via: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="manual",
        server_default=sql_text("'manual'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_text("1"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    posts: Mapped[list["EditorialSourcePost"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class EditorialSourcePost(Base):
    __tablename__ = "editorial_source_posts"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "telegram_msg_id",
            name="uq_editorial_source_posts_source_msg",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("editorial_sources.id", ondelete="CASCADE"), index=True
    )
    telegram_msg_id: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    source: Mapped["EditorialSource"] = relationship(back_populates="posts")
    topic_links: Mapped[list["EditorialTopicPost"]] = relationship(
        back_populates="post", cascade="all, delete-orphan"
    )


class EditorialTopicReport(Base):
    __tablename__ = "editorial_topic_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    style_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sources_csv: Mapped[str] = mapped_column(Text, nullable=False)
    window_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default=sql_text("30"),
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="started",
        server_default=sql_text("'started'"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    categories_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    topics: Mapped[list["EditorialTopic"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class EditorialTopic(Base):
    __tablename__ = "editorial_topics"
    __table_args__ = (
        UniqueConstraint("report_id", "slug", name="uq_editorial_topics_report_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("editorial_topic_reports.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    post_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    report: Mapped["EditorialTopicReport"] = relationship(back_populates="topics")
    post_links: Mapped[list["EditorialTopicPost"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )


class EditorialTopicPost(Base):
    __tablename__ = "editorial_topic_posts"
    __table_args__ = (
        UniqueConstraint("topic_id", "post_id", name="uq_editorial_topic_posts_topic_post"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("editorial_topics.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("editorial_source_posts.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    topic: Mapped["EditorialTopic"] = relationship(back_populates="post_links")
    post: Mapped["EditorialSourcePost"] = relationship(back_populates="topic_links")


class EditorialGenerationRun(Base):
    __tablename__ = "editorial_generation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    style_channel: Mapped[str] = mapped_column(String(255), nullable=False)
    selected_post_ids_csv: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="started",
        server_default=sql_text("'started'"),
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    outputs_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sql_text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    outputs: Mapped[list["EditorialGenerationOutput"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EditorialGenerationOutput(Base):
    __tablename__ = "editorial_generation_outputs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("editorial_generation_runs.id", ondelete="CASCADE"), index=True
    )
    source_post_ids_csv: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    run: Mapped["EditorialGenerationRun"] = relationship(back_populates="outputs")


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_settings: Settings | None = None


def init_engine(settings: Settings) -> None:
    global _engine, _session_factory, _settings
    _engine = create_async_engine(settings.sqlite_url, echo=False, future=True)
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )
    _settings = settings


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_alembic_config(sqlalchemy_url: str) -> Config:
    root = _project_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return config


def run_migrations(
    settings: Settings | None = None,
    sqlalchemy_url: str | None = None,
) -> None:
    if sqlalchemy_url is None:
        current = settings or _settings
        if current is None:
            raise RuntimeError("Database settings are not initialized")
        sqlalchemy_url = current.sqlite_sync_url
    command.upgrade(_build_alembic_config(sqlalchemy_url), "head")


@asynccontextmanager
async def get_session():
    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized")
    async with _session_factory() as session:
        yield session


async def init_db() -> None:
    await asyncio.to_thread(run_migrations)
