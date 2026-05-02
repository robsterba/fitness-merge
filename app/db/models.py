from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), unique=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkoutImport(Base):
    """One parsed file or Strava activity snapshot."""

    __tablename__ = "workout_imports"
    __table_args__ = (
        UniqueConstraint("origin_key", name="uq_workout_imports_origin_key"),
        Index("ix_workout_imports_start_time", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    origin_key: Mapped[str] = mapped_column(String(1024))
    format: Mapped[str] = mapped_column(String(32))
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    parsed: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    canonical_links: Mapped[list[CanonicalWorkoutSource]] = relationship(
        back_populates="workout_import", cascade="all, delete-orphan"
    )


class CanonicalWorkout(Base):
    __tablename__ = "canonical_workouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sport: Mapped[str | None] = mapped_column(String(64), nullable=True)
    merged: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    sources: Mapped[list[CanonicalWorkoutSource]] = relationship(
        back_populates="canonical_workout", cascade="all, delete-orphan"
    )


class CanonicalWorkoutSource(Base):
    __tablename__ = "canonical_workout_sources"
    __table_args__ = (UniqueConstraint("canonical_workout_id", "workout_import_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    canonical_workout_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_workouts.id", ondelete="CASCADE"),
        index=True,
    )
    workout_import_id: Mapped[int] = mapped_column(
        ForeignKey("workout_imports.id", ondelete="CASCADE"),
        index=True,
    )
    label: Mapped[str] = mapped_column(String(64))

    canonical_workout: Mapped[CanonicalWorkout] = relationship(back_populates="sources")
    workout_import: Mapped[WorkoutImport] = relationship(back_populates="canonical_links")
