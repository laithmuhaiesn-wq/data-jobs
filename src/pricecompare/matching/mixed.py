"""Automatic fix for products whose shops' prices are far apart (owner 2026-11-22: "make the fixing automatic").

Run every hour after matching. A listing that clearly belongs to another product is "held": it keeps its product link
but is shown nowhere (the site, the app and search read "matched" listings only), so the product shows the right prices.
Two signs, both needed to be clear:
- a word splits the listings into two tight price groups ("Wired" 49 vs the wireless 79, "Earbuds" 49 vs the headset
  90-124): the group sold by fewer shops is held; when both are sold by as many shops, nothing is guessed.
- a listing more than 2x away from the other listings' median, when at least 3 listings from 2 shops agree.
Held listings are judged again with the others every run and come back by themselves as soon as no rule holds them
(the shop's price agrees again, or the other listings are gone). A title change sends it back to matching anyway (store.py). The reader fix that gives the held listing
its own product is the daily repair session's job: `held` lists them."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Offer, PhoneModel, PhoneVariant

# words that make another product of the same name; shop words (USB, Bluetooth, colours) are left out on purpose
SPLIT_WORDS = ("wired", "wireless", "earbuds", "edition", "mini", "pro", "lite", "plus", "max", "ultra", "se", "oled")
OPPOSITE = {"wired": "wireless", "wireless": "wired"}
TIGHT, SPLIT_GAP, FAR = 1.5, 1.3, 2.0


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _counts(o: Offer, now: datetime) -> bool:
    return o.in_stock and o.price_type == "cash" and float(o.price_jod) > 0 and _aware(o.last_checked) >= now - timedelta(days=7)


def _spread(offers: list[Offer]) -> float:
    p = [float(o.price_jod) for o in offers]
    return max(p) / min(p)


def _by_word(offers: list[Offer], family: str) -> list[Offer]:
    fam = set(family.lower().split())
    for w in SPLIT_WORDS:
        if w in fam:
            continue
        has = [o for o in offers if re.search(rf"\b{w}\b", o.raw_title, re.I)]
        rest = [o for o in offers if o not in has]
        if not has or not rest or _spread(has) > TIGHT or _spread(rest) > TIGHT:
            continue
        # wired / wireless count only when the other side says the opposite: most shops just leave the word out
        # ("JBL Tune Buds 2" vs "... True Wireless ...", PC Circle 2026-11-22)
        if w in OPPOSITE and not all(re.search(rf"\b{OPPOSITE[w]}\b", o.raw_title, re.I) for o in rest):
            continue
        lo, hi = sorted((has, rest), key=lambda g: median(float(o.price_jod) for o in g))
        if min(float(o.price_jod) for o in hi) / max(float(o.price_jod) for o in lo) < SPLIT_GAP:
            continue
        a, b = (len({o.store_id for o in g}) for g in (has, rest))
        if a == b and {o.store_id for o in has} == {o.store_id for o in rest} == {has[0].store_id}:
            a, b = len(has), len(rest)       # one shop sells both (iGeek: 1 wired, 2 wireless): the odd one is held
        if a != b:
            return has if a < b else rest
    return []


def _far(offers: list[Offer]) -> list[Offer]:
    if len(offers) < 3 or len({o.store_id for o in offers}) < 2:
        return []
    med = median(float(o.price_jod) for o in offers)
    out = [o for o in offers if float(o.price_jod) > FAR * med or float(o.price_jod) < med / FAR]
    return out if len(out) * 2 < len(offers) else []


def fix_mixed(s: Session, now: datetime | None = None) -> dict[str, list[str]]:
    """Holds listings that belong to another product and lets held ones back; returns what changed (for the log)."""
    now = now or datetime.now(timezone.utc)
    family = dict(s.execute(select(PhoneVariant.id, PhoneModel.family).join(PhoneModel, PhoneVariant.model_id == PhoneModel.id)).all())
    # held listings are judged again from scratch with the others every run: held while a rule still says so
    rows = list(s.scalars(select(Offer).where(Offer.match_status.in_(("matched", "held")), Offer.variant_id.is_not(None))))
    groups: dict[int, list[Offer]] = {}
    for o in rows:
        if _counts(o, now):
            groups.setdefault(o.variant_id, []).append(o)
    hold: set[int] = set()
    for vid, offers in groups.items():
        if len(offers) >= 2 and _spread(offers) > TIGHT:
            hold.update(o.id for o in _by_word(offers, family.get(vid, "")) or _far(offers))
    out: dict[str, list[str]] = {"held": [], "back": []}
    for o in rows:
        now_held = o.id in hold
        if now_held != (o.match_status == "held"):
            o.match_status = "held" if now_held else "matched"
            out["held" if now_held else "back"].append(f"{o.id} {o.raw_title[:70]} {float(o.price_jod):g} (product {o.variant_id})")
    return out
