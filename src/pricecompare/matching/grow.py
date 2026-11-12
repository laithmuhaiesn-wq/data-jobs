"""Grow the catalog by itself every night, safely.

A new model is added only when ALL of these hold:
  * at least `min_shops` different shops sell the same brand + model + storage + market version (new, not refurbished);
  * their prices for that same size agree (cheapest / most expensive within `max_spread`), otherwise it is
    probably two different products sharing a name and waits for a person;
  * the name looks like a model name (short, no bundle words), the brand is a known brand, and the model was
    never removed by a person;
  * no more than `max_new` are added in one night (a sudden flood means a shop page changed, not new phones).

Every addition is written to audit_log (actor "auto-grow") with the shops and prices that proved it.
`block_model` undoes one: the model is renamed "blocked:<family>" (so it never matches and is never re-added)
and its shop listings go back to the review queue. Nothing is deleted (the collector login cannot delete).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import AuditLog, Brand, Offer, PhoneModel, PhoneVariant, Store
from ..display import BRAND_AR
from .parse import parse_title

BLOCKED = "blocked:"
NOT_NEW = re.compile(r"\b(refurb\w*|renewed|used|pre-?owned|open ?box|demo|display unit|like new|grade [abc])\b|مستعمل|مجدد|مستخدم", re.I)
BUNDLE = re.compile(r"\b(bundle|with|offer|gift|free|set|pack|combo|and|kit)\b|[+&/]")
LAPTOP = re.compile(r"\b(core|i[3579]|ryzen|rtx|gtx|ideapad|thinkpad|thinkbook|loq|yoga|vivobook|zenbook|legion|"
                    r"all in one|2 ?in ?1|\d+(st|nd|rd|th) ?gen|\d{2}gen|intel|amd)\b")
NET = re.compile(r"\b[45]g\b")


def _base(family: str) -> str:
    return re.sub(r"\s+", " ", NET.sub("", family)).strip()


@dataclass
class Candidate:
    brand: str
    family: str
    shops: set[str] = field(default_factory=set)
    prices: dict[str, float] = field(default_factory=dict)  # "shop storage" -> cheapest price
    reason: str = ""  # empty = accepted


def find_candidates(s: Session, min_shops: int = 2, max_spread: float = 0.35) -> list[Candidate]:
    brands = set(BRAND_AR)  # a brand we can name in Arabic; Brand rows are made for new ones
    models = {(b.name_en, m.family) for m, b in s.execute(select(PhoneModel, Brand).join(Brand, PhoneModel.brand_id == Brand.id))}
    have_base = {(b, _base(f.removeprefix(BLOCKED))) for b, f in models}
    blocked = {(b, f.removeprefix(BLOCKED)) for b, f in models if f.startswith(BLOCKED)}
    stores = {st.id: st.slug for st in s.scalars(select(Store))}

    # (brand, base family) -> spelling -> (storage, market) -> shop -> cheapest price
    seen: dict[tuple[str, str], dict[str, dict[tuple, dict[str, float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for o in s.scalars(select(Offer).where(Offer.match_status == "review")):
        if o.condition != "new" or NOT_NEW.search(o.raw_title):
            continue
        p = parse_title(o.raw_title)
        if not (p.is_product and p.brand and p.storage_gb):
            continue
        shop, price = stores[o.store_id], float(o.price_jod)
        cell = seen[(p.brand, _base(p.family))][p.family][(p.storage_gb, p.market_version)]
        cell[shop] = min(price, cell.get(shop, price))

    out: list[Candidate] = []
    for (brand, base), spellings in sorted(seen.items()):
        # several 4G/5G-tagged spellings (A17 4G and A17 5G) are different phones; one tagged spelling is the canonical name
        tagged = sorted(f for f in spellings if NET.search(f))
        names = tagged if tagged else sorted(spellings)
        for fam in names:
            group = [spellings[fam]] if len(tagged) > 1 else list(spellings.values())
            sizes: dict[tuple, dict[str, float]] = defaultdict(dict)
            for g in group:
                for size, shops in g.items():
                    for shop, price in shops.items():
                        sizes[size][shop] = min(price, sizes[size].get(shop, price))
            c = Candidate(brand, fam)
            agreeing = {size: shops for size, shops in sizes.items() if len(shops) >= min_shops}
            for (gb, market), shops in agreeing.items():
                c.shops |= set(shops)
                for shop, price in shops.items():
                    c.prices[f"{shop} {gb}GB{'' if market == 'unknown' else ' ' + market}"] = price
            if (brand, fam) in blocked or (brand, _base(fam)) in {(b, _base(f)) for b, f in blocked}:
                c.reason = "removed by a person before"
            elif (brand, _base(fam)) in have_base and not tagged:
                c.reason = "already in the catalog"
            elif (brand, fam) in models:
                c.reason = "already in the catalog"
            elif not agreeing:
                c.reason = f"fewer than {min_shops} shops sell the same size"
            elif brand not in brands:
                c.reason = "unknown brand"
            elif LAPTOP.search(fam):
                c.reason = "looks like a laptop"
            elif len(fam) > 40 or len(fam.split()) > 5 or BUNDLE.search(fam) or not re.search(r"[a-z]", fam):
                c.reason = "name does not look like a model"
            else:
                for shops in agreeing.values():
                    lo, hi = min(shops.values()), max(shops.values())
                    if hi > lo * (1 + max_spread):
                        c.reason = f"shop prices disagree ({lo:g} to {hi:g} JOD)"
                        break
            out.append(c)
    return out


def auto_grow(s: Session, max_new: int = 10, min_shops: int = 2, max_spread: float = 0.35, dry_run: bool = False) -> dict:
    cands = find_candidates(s, min_shops, max_spread)
    ok = sorted((c for c in cands if not c.reason), key=lambda c: (-len(c.shops), c.brand, c.family))
    added, held = ok[:max_new], ok[max_new:]
    for c in held:
        c.reason = f"over the nightly limit of {max_new}"
    if not dry_run:
        brand_ids = {b.name_en: b.id for b in s.scalars(select(Brand))}
        for c in added:
            if c.brand not in brand_ids:
                b = Brand(name_en=c.brand)
                s.add(b)
                s.flush()
                brand_ids[c.brand] = b.id
            s.add(PhoneModel(brand_id=brand_ids[c.brand], family=c.family))
            s.add(AuditLog(actor="auto-grow", action="catalog_add",
                           detail=json.dumps({"brand": c.brand, "family": c.family, "prices": c.prices}, ensure_ascii=False)[:500]))
        s.flush()
    waiting = [c for c in cands if c.reason and c.reason != "already in the catalog"]
    return {
        "added": [f"{c.brand} {c.family} ({len(c.shops)} shops: {', '.join(f'{k} {v:g}' for k, v in sorted(c.prices.items()))})" for c in added],
        "waiting": [f"{c.brand} {c.family}: {c.reason}" for c in waiting if c.reason != f"fewer than {min_shops} shops sell the same size"],
        "one_shop_only": sum(1 for c in waiting if c.reason == f"fewer than {min_shops} shops sell the same size"),
    }


def block_model(s: Session, brand: str, family: str) -> int:
    """Undo a wrong model: it never matches again and is never re-added; its shop listings go back to review."""
    m = s.scalar(select(PhoneModel).join(Brand, PhoneModel.brand_id == Brand.id)
                 .where(Brand.name_en == brand, PhoneModel.family == family))
    if m is None:
        raise SystemExit(f"no model {brand} {family!r} in the catalog")
    vids = list(s.scalars(select(PhoneVariant.id).where(PhoneVariant.model_id == m.id)))
    freed = 0
    if vids:
        for o in s.scalars(select(Offer).where(Offer.variant_id.in_(vids))):
            o.variant_id, o.match_status, o.match_confidence = None, "review", None
            freed += 1
    m.family = (BLOCKED + family)[:128]
    s.add(AuditLog(actor="person", action="catalog_block", detail=f"{brand} {family}: {freed} listings back to review"))
    s.flush()
    return freed
