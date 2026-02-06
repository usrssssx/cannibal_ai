from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    channel: Mapped["Channel"] = relationship(back_populates="posts")


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


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
