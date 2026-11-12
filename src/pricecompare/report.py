"""Pilot metrics against the go/no-go criteria (see plan)."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db.models import Brand, CollectionRun, Offer, PhoneModel, PhoneVariant, Store


def variant_label(s: Session, variant_id: int) -> str:
    v = s.get(PhoneVariant, variant_id)
    m = s.get(PhoneModel, v.model_id)
    b = s.get(Brand, m.brand_id)
    return f"{b.name_en} {m.family} {v.storage_gb}GB [{v.market_version}]"


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def suspicious_offer_ids(s: Session, jump: float = 0.4, floor: float = 0.3) -> set[int]:
    """Offers whose price looks wrong: moved more than `jump` since the last observation, or is under `floor` of the
    median of the same variant's other offers (needs 3+ offers). They are kept out of best price until reviewed."""
    from statistics import median

    from .db.models import PriceObservation
    bad: set[int] = set()
    last_two: dict[int, list[float]] = {}
    for oid, price in s.execute(select(PriceObservation.offer_id, PriceObservation.price_jod)
                                .order_by(PriceObservation.offer_id, PriceObservation.observed_at.desc())):
        last_two.setdefault(oid, [])
        if len(last_two[oid]) < 2:
            last_two[oid].append(float(price))
    for oid, v in last_two.items():
        if len(v) == 2 and v[1] > 0 and abs(v[0] - v[1]) / v[1] > jump:
            bad.add(oid)
    groups: dict[int, list[Offer]] = {}
    for o in s.scalars(select(Offer).where(Offer.match_status == "matched")):
        groups.setdefault(o.variant_id, []).append(o)
    for offers in groups.values():
        if len(offers) >= 3:
            med = median(float(o.price_jod) for o in offers)
            bad.update(o.id for o in offers if float(o.price_jod) < floor * med)
    return bad


def compute(s: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    offers = list(s.scalars(select(Offer)))
    phones = [o for o in offers if o.match_status not in ("not_phone", "no_storage")]
    no_storage = sum(1 for o in offers if o.match_status == "no_storage")
    matched = [o for o in phones if o.match_status == "matched"]
    fresh = [o for o in phones if _aware(o.last_checked) >= now - timedelta(hours=48)]

    by_variant: dict[int, set[int]] = {}
    for o in matched:
        by_variant.setdefault(o.variant_id, set()).add(o.store_id)

    shops = {st.id: st.slug for st in s.scalars(select(Store))}
    per_shop = {}
    for sid, slug in shops.items():
        runs = list(s.scalars(select(CollectionRun).where(CollectionRun.store_id == sid)))
        n = sum(1 for o in phones if o.store_id == sid)
        per_shop[slug] = {
            "phone_offers": n,
            "matched": sum(1 for o in matched if o.store_id == sid),
            "runs": len(runs),
            "runs_ok": sum(1 for r in runs if r.status == "ok"),
        }
    n_phones = len(phones) or 1
    return {
        "shops_with_phone_offers": sum(1 for v in per_shop.values() if v["phone_offers"] > 0),
        "phone_offers_with_storage": len(phones),
        "no_storage_offers": no_storage,
        "matched_pct": round(100 * len(matched) / n_phones, 1),
        "unmatched_pct": round(100 * (len(phones) - len(matched)) / n_phones, 1),
        "fresh_48h_pct": round(100 * len(fresh) / n_phones, 1),
        "variants_total": len(by_variant),
        "variants_in_3plus_shops": sum(1 for st in by_variant.values() if len(st) >= 3),
        "variants_in_2plus_shops": sum(1 for st in by_variant.values() if len(st) >= 2),
        "per_shop": per_shop,
        "suspicious_prices": len(suspicious_offer_ids(s)),
        "history_rows": s.scalar(select(func.count()).select_from(
            __import__("pricecompare.db.models", fromlist=["PriceObservation"]).PriceObservation)),
    }


def audit_sample(s: Session, n: int = 200, seed: int = 7) -> list[tuple[int, str, str, str]]:
    """Random matched offers: (offer id, shop, raw title, assigned variant) for a human accuracy audit."""
    shops = {st.id: st.slug for st in s.scalars(select(Store))}
    matched = list(s.scalars(select(Offer).where(Offer.match_status == "matched")))
    random.Random(seed).shuffle(matched)
    return [(o.id, shops[o.store_id], o.raw_title, variant_label(s, o.variant_id)) for o in matched[:n]]


def spot_check_sample(s: Session, n: int = 100, seed: int = 11) -> list[Offer]:
    offers = list(s.scalars(select(Offer).where(Offer.match_status == "matched")))
    random.Random(seed).shuffle(offers)
    return offers[:n]
