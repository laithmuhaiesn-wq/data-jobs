from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Brand(Base):
    __tablename__ = "brand"
    id: Mapped[int] = mapped_column(primary_key=True)
    name_en: Mapped[str] = mapped_column(String(64), unique=True)
    name_ar: Mapped[str | None] = mapped_column(String(64))


class PhoneModel(Base):
    __tablename__ = "phone_model"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brand.id"))
    family: Mapped[str] = mapped_column(String(128))
    release_year: Mapped[int | None]
    __table_args__ = (UniqueConstraint("brand_id", "family"),)


class PhoneVariant(Base):
    __tablename__ = "phone_variant"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("phone_model.id"))
    storage_gb: Mapped[int | None]
    ram_gb: Mapped[int | None]
    connectivity: Mapped[str] = mapped_column(String(16), default="unknown")
    market_version: Mapped[str] = mapped_column(String(16), default="unknown")
    __table_args__ = (
        UniqueConstraint("model_id", "storage_gb", "ram_gb", "connectivity", "market_version"),
    )


class Store(Base):
    __tablename__ = "store"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    site_url: Mapped[str] = mapped_column(String(200))
    official_agent: Mapped[bool] = mapped_column(default=False)


class Source(Base):
    __tablename__ = "source"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"), unique=True)
    method: Mapped[str] = mapped_column(String(24))
    terms_rating: Mapped[str] = mapped_column(String(16), default="unknown")
    terms_reviewed_on: Mapped[str | None] = mapped_column(String(10))
    enabled: Mapped[bool] = mapped_column(default=True)
    consecutive_failures: Mapped[int] = mapped_column(default=0)
    store: Mapped[Store] = relationship()


class Offer(Base):
    __tablename__ = "offer"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"))
    external_id: Mapped[str] = mapped_column(String(200))
    raw_title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(500))
    image_url: Mapped[str | None] = mapped_column(String(500), deferred=True)  # shop picture address; linked, never downloaded
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("phone_variant.id"))
    match_status: Mapped[str] = mapped_column(String(16), default="unmatched")
    match_confidence: Mapped[float | None]
    price_jod: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    price_type: Mapped[str] = mapped_column(String(16), default="cash")
    in_stock: Mapped[bool] = mapped_column(default=True)
    condition: Mapped[str] = mapped_column(String(16), default="new")
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_price_change: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("store_id", "external_id"),
        Index("ix_offer_variant", "variant_id"),
    )


class PriceObservation(Base):
    __tablename__ = "price_observation"
    id: Mapped[int] = mapped_column(primary_key=True)
    offer_id: Mapped[int] = mapped_column(ForeignKey("offer.id"), index=True)
    price_jod: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    in_stock: Mapped[bool]
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CollectionRun(Base):
    __tablename__ = "collection_run"
    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")
    items_seen: Mapped[int] = mapped_column(default=0)
    items_changed: Mapped[int] = mapped_column(default=0)
    requests: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(500))
