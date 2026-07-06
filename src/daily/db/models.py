"""SQLAlchemy 2.0 ORM models for dAIly."""
from datetime import datetime
from typing import Optional

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class IntegrationToken(Base):
    __tablename__ = "integration_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    encrypted_access_token: Mapped[str] = mapped_column(Text)
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BriefingConfig(Base):
    __tablename__ = "briefing_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    # Local wall-clock hour/minute, interpreted in `timezone` below (audit M1:
    # storing a fixed UTC hour/minute computed once at write time goes stale
    # across DST transitions — APScheduler's CronTrigger resolves these two
    # fields against `timezone` on every fire instead, so DST is handled by
    # zoneinfo rather than a precomputed offset). Default "5, 0, UTC" reads
    # as 05:00 UTC either way, so existing UTC-only callers are unaffected.
    schedule_hour: Mapped[int] = mapped_column(default=5)
    schedule_minute: Mapped[int] = mapped_column(default=0)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    email_top_n: Mapped[int] = mapped_column(default=5)
    slack_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String), server_default="{}", default=list
    )  # per BRIEF-05: priority channels. Empty list = all accessible channels.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class VipSender(Base):
    __tablename__ = "vip_senders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint("user_id", "email", name="uq_vip_user_email"),
    )


class PairingCode(Base):
    __tablename__ = "pairing_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    code: Mapped[str] = mapped_column(String(6), index=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


class DeviceToken(Base):
    __tablename__ = "device_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text)
    # SHA-256 hex digest of the raw (unencrypted) refresh token (audit C4).
    # Enables an indexed lookup in /auth/token/refresh instead of a full-table
    # decrypt scan. Nullable — existing rows are backfilled lazily on next
    # successful refresh (see migration 009_add_refresh_token_hash).
    refresh_token_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
