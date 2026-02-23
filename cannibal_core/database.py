from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

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
    select,
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
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    with_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
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
    with_images: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="started")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    posts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_schema_version: int = 2


def init_engine(settings: Settings) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(settings.sqlite_url, echo=False, future=True)
    _session_factory = async_sessionmaker(
        _engine, expire_on_commit=False, class_=AsyncSession
    )


@asynccontextmanager
async def get_session():
    if _session_factory is None:
        raise RuntimeError("Database engine is not initialized")
    async with _session_factory() as session:
        yield session


async def init_db() -> None:
    if _engine is None:
        raise RuntimeError("Database engine is not initialized")
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_session() as session:
        result = await session.execute(select(SchemaMeta))
        meta = result.scalar_one_or_none()
        if meta is None:
            session.add(SchemaMeta(version=_schema_version))
            await session.commit()
            return
        if meta.version != _schema_version:
            # Avoid breaking; just warn.
            from loguru import logger

            logger.warning(
                "Schema version mismatch: db={} expected={}.",
                meta.version,
                _schema_version,
            )
