"""Grow the catalog by itself every night, safely and without waiting for a person.

A new model is added in one of two ways:
  A. "shops agree": 2+ different shops sell the same brand + model + storage + market version (new, not
     refurbished) and their prices for that size are within `max_spread` of each other.
  B. "one shop": one shop sells it, every listing of it was seen in the last 2 days, and its price is normal for the
     brand (not under 20 JOD, not 6x away from that brand's usual price). Added at once (owner, 2026-11-13) and marked
     "only at 1 shop". 2+ shops whose prices disagree must also have been listed `min_days` ("listed N days").
Both need: a brand we can name in Arabic, a short model-like name (no bundle or laptop words), never removed by a
person. At most `max_new` a run per category (A first, most shops first); the rest come the next run. Runs every hour.

Every addition is written to audit_log (actor "auto-grow") with the shops and prices that proved it.
`block_model` undoes one: the model is renamed "blocked:<family>" (so it never matches and is never re-added)
and its shop listings go back to the review queue. Nothing is deleted (the collector login cannot delete).
A product sold by one shop shows "only at 1 shop" on the site and in the app.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import AuditLog, Brand, Offer, PhoneModel, PhoneVariant, PriceObservation, Store
from ..display import BRAND_AR
from . import laptop, tv, watch
from .parse import category_of, parse_title

BLOCKED = "blocked:"
NOT_NEW = re.compile(r"\b(refurb\w*|renewed|used|pre-?owned|open ?box|demo|display unit|like new|grade [abc])\b|مستعمل|مجدد|مستخدم", re.I)
BUNDLE = re.compile(r"\b(bundle|with|offer|gift|free|set|pack|combo|and|kit)\b|[+&/]")
LAPTOP = re.compile(r"\b(core|i[3579]|ryzen|rtx|gtx|ideapad|thinkpad|thinkbook|loq|yoga|vivobook|zenbook|legion|"
                    r"all in one|2 ?in ?1|\d+(st|nd|rd|th) ?gen|\d{2}gen|intel|amd)\b")
NET = re.compile(r"\b[45]g\b")
MIN_PRICE, MAX_PRICE, BRAND_FACTOR = 20.0, 3000.0, 10.0
MAX_PRICE_BY_CATEGORY = {"laptop": 6000.0, "tv": 9000.0, "watch": 2000.0}  # a big 8K TV costs more than a laptop   # a top gaming laptop costs more than any phone
# Shops selling the same laptop were 0-14% apart on 2026-11-12; a bigger gap usually means two versions behind the same
# words (a 4K and a 3K screen), so laptops must agree within 20% (phones 35%).
SPREAD_BY_CATEGORY = {"laptop": 0.20, "tv": 0.25, "watch": 0.25}  # TVs: the maker code names one set; shops' TV sales run deeper
RAM_SIZES = {"2", "3", "4", "6", "8", "12", "16"}
# words that make a different model ("note", "tab", "pad" lines; "pro", "ultra" versions): never a messy extra word
MODEL_WORDS = {"note", "redmi", "galaxy", "nova", "pura", "mate", "reno", "find", "spark", "camon", "pova", "pop", "hot", "smart",
               "zero", "gt", "magic", "pad", "matepad", "ipad", "megapad", "xpad", "razr", "moto", "pixel", "z", "a", "m", "y"}
SUFFIXES = {"pro", "max", "plus", "ultra", "lite", "fe", "se", "neo", "mini", "air", "fold", "flip", "edge", "prime", "power",
            "play", "5g", "4g", "s", "c", "x", "t", "e", "i", "r", "go", "turbo", "slim"}


def _base(family: str) -> str:
    return re.sub(r"\s+", " ", NET.sub("", family)).strip()


def name_problem(fam: str, same_brand: set[str]) -> str:
    """Why a family name is probably a messy shop title rather than a real model name ("" = looks fine)."""
    words = fam.split()
    if len(fam) > 40 or len(words) > 5 or BUNDLE.search(fam) or not re.search(r"[a-z0-9]", fam):  # "Honor 400" is a real name
        return "name does not look like a model"
    if len(words) == 1 and not re.search(r"\d", fam):   # "matepad" alone: which MatePad? never guessed
        return "a product line, not a model"
    if len(set(words)) < len(words):
        return "a word is repeated (messy shop title)"
    if any(len(w) >= 7 and re.search(r"\d", w) and re.search(r"[a-z]", w) for w in words) or \
            any(w in ("cph", "apac", "display", "sm") or re.fullmatch(r"x\d{4}[a-z]?", w) for w in words):
        return "contains a shop's stock code"
    for i, w in enumerate(words[1:], 1):
        if w in RAM_SIZES and re.search(r"\d", words[i - 1]):
            return "a leftover RAM number in the name"
    for n in range(len(words) - 1, 0, -1):  # "a16 turbo" is fine, "a16 something" next to catalog "a16" is not
        head = " ".join(words[:n])
        if _base(head) in same_brand and any(_base(w) and w not in SUFFIXES for w in words[n:]):
            return f"looks like catalog model '{head}' with extra words"
    return ""


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


@dataclass
class Listing:
    price: float
    first_seen: datetime
    last_checked: datetime


@dataclass
class Candidate:
    brand: str
    family: str
    shops: set[str] = field(default_factory=set)
    prices: dict[str, float] = field(default_factory=dict)  # "shop storage" -> cheapest price
    way: str = ""      # "shops agree" or "listed N days"
    days: int = 0      # how long the newest listing has been up (way B)
    reason: str = ""   # empty = accepted


def _brand_prices(s: Session) -> dict[tuple[str, str], float]:
    """The usual (median) price of each brand's matched products in each category (a Lenovo laptop is not judged
    against Lenovo tablets)."""
    by: dict[tuple[str, str], list[float]] = defaultdict(list)
    q = (select(Brand.name_en, PhoneModel.family, Offer.price_jod).join(PhoneVariant, Offer.variant_id == PhoneVariant.id)
         .join(PhoneModel, PhoneVariant.model_id == PhoneModel.id).join(Brand, PhoneModel.brand_id == Brand.id)
         .where(Offer.match_status == "matched"))
    for b, fam, p in s.execute(q):
        by[(b, category_of(fam))].append(float(p))
    return {k: median(v) for k, v in by.items() if len(v) >= 3}


def price_is_normal(price: float, brand_median: float | None, category: str = "phone") -> bool:
    if not MIN_PRICE <= price <= MAX_PRICE_BY_CATEGORY.get(category, MAX_PRICE):
        return False
    return brand_median is None or brand_median / BRAND_FACTOR <= price <= brand_median * BRAND_FACTOR


def find_candidates(s: Session, min_shops: int = 2, max_spread: float = 0.35, min_days: int = 7,
                    now: datetime | None = None) -> list[Candidate]:
    now = now or datetime.now(timezone.utc)
    brands = set(BRAND_AR)  # a brand we can name in Arabic; Brand rows are made for new ones
    models = {(b.name_en, m.family) for m, b in s.execute(select(PhoneModel, Brand).join(Brand, PhoneModel.brand_id == Brand.id))}
    have_base = {(b, _base(f.removeprefix(BLOCKED))) for b, f in models}
    blocked = {(b, f.removeprefix(BLOCKED)) for b, f in models if f.startswith(BLOCKED)}
    blocked_base = {(b, _base(f)) for b, f in blocked}
    stores = {st.id: st.slug for st in s.scalars(select(Store))}
    first = dict(s.execute(select(PriceObservation.offer_id, func.min(PriceObservation.observed_at)).group_by(PriceObservation.offer_id)).all())
    usual = _brand_prices(s)

    # (brand, base family) -> spelling -> (storage, market) -> shop -> its cheapest listing
    seen: dict[tuple[str, str], dict[str, dict[tuple, dict[str, Listing]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for o in s.scalars(select(Offer).where(Offer.match_status == "review")):
        if o.condition != "new" or NOT_NEW.search(o.raw_title):
            continue
        p = parse_title(o.raw_title)
        if not (p.is_product and p.brand and p.storage_gb):
            continue
        shop, price = stores[o.store_id], float(o.price_jod)
        size = (p.storage_gb, f"ram{p.ram_gb}" if p.category == "laptop" else p.market_version)
        cell = seen[(p.brand, _base(p.family))][p.family][size]
        listing = Listing(price, _aware(first.get(o.id) or o.last_checked), _aware(o.last_checked))
        if shop not in cell or price < cell[shop].price:
            cell[shop] = listing

    out: list[Candidate] = []
    # every name seen for each brand (catalog and shops), to catch one product under two names
    names_of: dict[str, set[str]] = defaultdict(set)
    for b, f in models:
        names_of[b].add(f)
    for (b, _), spellings in seen.items():
        names_of[b] |= set(spellings)
    for (brand, base), spellings in sorted(seen.items()):
        # several 4G/5G-tagged spellings (A17 4G and A17 5G) are different phones; one tagged spelling is the canonical name
        tagged = sorted(f for f in spellings if NET.search(f))
        names = tagged if tagged else sorted(spellings)
        for fam in names:
            group = [spellings[fam]] if len(tagged) > 1 else list(spellings.values())
            sizes: dict[tuple, dict[str, Listing]] = defaultdict(dict)
            for g in group:
                for size, shops in g.items():
                    for shop, li in shops.items():
                        if shop not in sizes[size] or li.price < sizes[size][shop].price:
                            sizes[size][shop] = li
            c = Candidate(brand, fam)
            for (gb, market), shops in sizes.items():
                c.shops |= set(shops)
                for shop, li in shops.items():
                    c.prices[f"{shop} {gb}GB{'' if market == 'unknown' else ' ' + market}"] = li.price
            agreeing = {size: shops for size, shops in sizes.items() if len(shops) >= min_shops}
            spread = SPREAD_BY_CATEGORY.get(category_of(fam), max_spread)
            disagree = next(((min(x.price for x in sh.values()), max(x.price for x in sh.values())) for sh in agreeing.values()
                             if max(x.price for x in sh.values()) > min(x.price for x in sh.values()) * (1 + spread)), None)
            listings = [li for sh in sizes.values() for li in sh.values()]
            c.days = min((now - li.first_seen).days for li in listings)
            is_laptop = category_of(fam) in ("laptop", "tv", "watch")      # names built by our own readers, joined only when shops agree
            if (brand, fam) in blocked or (brand, _base(fam)) in blocked_base:
                c.reason = "removed by a person before"
            elif (brand, _base(fam)) in have_base and not tagged or (brand, fam) in models:
                c.reason = "already in the catalog"
            elif brand not in brands:
                c.reason = "unknown brand"
            elif is_laptop and not (laptop.is_laptop_family(fam) and laptop.well_formed(fam) or tv.is_tv_family(fam) or watch.is_watch_family(fam)):
                c.reason = "name does not look like a laptop"
            elif not is_laptop and LAPTOP.search(fam):
                c.reason = "looks like a laptop"
            elif is_laptop and (more := next((f for f in sorted(names_of[brand]) if f.startswith(fam + " ")), None)):
                c.reason = f"less exact than '{more}' (screen not in the title): waits for a title that says it"
            elif not is_laptop and (twin := next((" ".join(fam.split()[:i] + fam.split()[i + 1:]) for i, w in enumerate(fam.split())
                                                  if w not in SUFFIXES and w not in MODEL_WORDS and not any(ch.isdigit() for ch in w)
                                                  and " ".join(fam.split()[:i] + fam.split()[i + 1:]) in names_of[brand]), None)):
                c.reason = f"looks like '{twin}' with one extra word"
            elif not is_laptop and (problem := name_problem(fam, {f for b, f in have_base if b == brand})):
                c.reason = problem                                      # laptop names are built by the laptop reader itself
            elif agreeing and not disagree:
                c.way = "shops agree"
            elif is_laptop and disagree:
                # different screens or chips hide behind the same words: laptops are joined only when shops agree
                c.reason = f"shop prices disagree ({disagree[0]:g} to {disagree[1]:g} JOD): laptops are joined only when shops agree"
            else:
                # way B: one shop, or shops whose prices disagree; time and a normal price must vouch for it
                cat = category_of(fam)
                odd = next((li.price for li in listings if not price_is_normal(li.price, usual.get((brand, cat)), cat)), None)
                stale = any(now - li.last_checked > timedelta(days=2) for li in listings)
                why = f"shop prices disagree ({disagree[0]:g} to {disagree[1]:g} JOD); " if disagree else "one shop; "
                if odd is not None:
                    c.reason = why + f"price {odd:g} JOD is unusual for {brand}"
                elif stale:
                    c.reason = why + "not seen on the shop's site in the last 2 days"
                elif disagree and c.days < min_days:
                    # two shops far apart usually means two versions behind the same words: time must vouch for it
                    c.reason = why + f"listed {c.days} of {min_days} days"
                elif disagree:
                    c.way = f"listed {c.days} days (prices disagree)"
                else:
                    # owner 2026-11-13: a product only one shop sells is shown at once, marked "only at 1 shop"
                    c.way = "one shop"
            out.append(c)
    return out


def auto_grow(s: Session, max_new: int = 60, min_shops: int = 2, max_spread: float = 0.35, min_days: int = 7,
              dry_run: bool = False, now: datetime | None = None) -> dict:
    cands = find_candidates(s, min_shops, max_spread, min_days, now)
    ok = sorted((c for c in cands if not c.reason),
                key=lambda c: (c.way != "shops agree", -len(c.shops), -c.days, c.brand, c.family))
    taken: dict[str, int] = defaultdict(int)
    added, held = [], []
    for c in ok:
        cat = category_of(c.family)
        (added if taken[cat] < max_new else held).append(c)
        taken[cat] += 1
    for c in held:
        c.reason = f"over the nightly limit of {max_new} for its category (added on a later night)"
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
                           detail=json.dumps({"brand": c.brand, "family": c.family, "way": c.way, "prices": c.prices}, ensure_ascii=False)[:500]))
        s.flush()
    later = [c for c in cands if c.reason and c.reason != "already in the catalog"]
    return {
        "added": [f"{c.brand} {c.family} [{c.way}] ({', '.join(f'{k} {v:g}' for k, v in sorted(c.prices.items()))})" for c in added],
        "not_yet": [f"{c.brand} {c.family}: {c.reason}" for c in later],
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
