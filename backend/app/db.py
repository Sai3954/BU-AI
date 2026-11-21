"""Database models. Works with SQLite (default) or PostgreSQL via DATABASE_URL."""
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, Integer, String, Text, create_engine)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Chunk(Base):
    """One searchable passage of official content."""
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(300), unique=True, index=True)
    url: Mapped[str] = mapped_column(String(1000), index=True)
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(80), index=True)
    audiences: Mapped[str] = mapped_column(String(300), default="all")  # comma separated
    text: Mapped[str] = mapped_column(Text)
    updated_label: Mapped[str] = mapped_column(String(80), default="")
    source: Mapped[str] = mapped_column(String(20), default="seed")  # seed | crawl
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of floats
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Page(Base):
    """A crawled page, used for change detection and link health."""
    __tablename__ = "pages"
    url: Mapped[str] = mapped_column(String(1000), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    updated_label: Mapped[str] = mapped_column(String(80), default="")
    last_crawled: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_changed: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QueryLog(Base):
    """Anonymous log of questions, for the admin analytics view. No personal data."""
    __tablename__ = "queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    role: Mapped[str] = mapped_column(String(40), default="")
    question: Mapped[str] = mapped_column(Text)
    top_category: Mapped[str] = mapped_column(String(80), default="")
    sources: Mapped[str] = mapped_column(Text, default="")  # JSON list of urls
    answered: Mapped[bool] = mapped_column(Boolean, default=True)
    high_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pii_removed: Mapped[str] = mapped_column(String(200), default="")  # kinds redacted, e.g. "EMAIL,PHONE"
    unverified: Mapped[int] = mapped_column(Integer, default=0)  # figures in the answer not found in sources
    ai: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_reason: Mapped[str] = mapped_column(String(40), default="")  # wrong | missing | unclear (on thumbs-down)


class Issue(Base):
    """Content quality issue found by the knowledge monitor."""
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)  # stale | broken_link | conflict | changed
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    url: Mapped[str] = mapped_column(String(1000), default="")
    detail: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Tiny migration: add columns introduced after a database was first created."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            ddl_type = col.type.compile(engine.dialect)
            default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
            dflt = "" if default is None else f" DEFAULT {repr(default) if isinstance(default, str) else int(default)}"
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl_type}{dflt}'))
