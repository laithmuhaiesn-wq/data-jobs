"""In-stock listings the site hides, each one checked once (owner 2026-11-25: a 575 JOD PS5 Slim was hidden for days).

A hidden listing is not a fault by itself (a cable, a case, a laptop without its RAM), so nothing raised an alarm when
a real product was hidden by a reader gap. Now every in-stock title that is not matched is put on a list until it has
been looked at once:
  sure    - it names a product line everybody sells (PS5, Xbox, iPhone, Galaxy, MacBook...) and no add-on word
  likely  - it says one of our categories and a maker we know, or a product waiting a week for the catalogue
  other   - everything else that is new (a new kind of goods, a new maker)
`python -m pricecompare.cli missed` writes ~/.derbani/missed_products.json (nightly job); the daily doctor reads every
title, fixes the reader gaps with tests and runs `missed --seen`. A title comes back only when the shop changes it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Offer, PriceObservation, Store
from . import gadget, laptop, tablet, tv, watch

REPORT = Path.home() / ".derbani" / "missed_products.json"
SEEN = Path.home() / ".derbani" / "missed_seen.json"
LINES = re.compile(r"\b(play\s?sta\w+\s*(?:5|portal)|ps\s?5|xbox\s+series|nintendo\s+switch|switch\s+2|steam\s+deck|rog\s+(?:xbox\s+)?ally|"
                   r"iphone\s+(?:1[4-9]|2\d|air|duo)|galaxy\s+(?:[sa]\d{2}|z\s?(?:fold|flip)|tab|watch|buds)|ipad|macbook|imac|mac\s?mini|"
                   r"airpods|apple\s+watch|redmi\s+(?:note|pad|buds|watch)|poco\s+\w\d|honor\s+(?:magic|\d{3}|x\d)|"
                   r"(?:tune|live)\s+\d{3}(?:nc|bt)|rtx\s?\d{4}|ryzen\s+[3579]\s+\d{4}|core\s+i[3579])\b", re.I)
ADDON = re.compile(r"\b(for|case|cases|cover|protector|film|glass|screen|cable|charger|charging|adapter|strap|bands?|tips|holder|stand|mount|"
                   r"skin|sticker|controllers?|dualsense|gamepad|games?|edition\s+(?:ps[45]|playstation)|standard\s+edition|bag|sleeve|pouch|"
                   r"keyboard|pencil|bumper|techwoven|silicone|leather|compatible|replacement|refurb\w*|used|open\s?box|motherboard|cooler|"
                   r"fan|toner|cartridge|dock|hub|grip|fifa|key\s?ring|metal\s+frame|battery)\b|كفر|غطاء|شاحن|حماية|كابل", re.I)
PARTS = re.compile(r"\b(cable|adapter|case|cover|bracket|mount|holder|stand|toner|cartridge|ink|cooler|fan|motherboard|power\s+supply|psu|"
                   r"nvr|dvr|rack|patch|label|paper|bag|strap|protector|charger)\b", re.I)
HELD_DAYS = 7


def kind(title: str, status: str, days: int) -> str:
    """"sure", "likely" or "other": how probable it is that a real product of ours is hidden."""
    if LINES.search(title) and not ADDON.search(title):
        return "sure"
    if status == "review":
        return "likely" if days >= HELD_DAYS else "other"
    says = any(p.search(title) for _, p in gadget.SAYS) or laptop.looks_like_laptop(title) or tv.looks_like_tv(title) \
        or watch.looks_like_watch(title) or tablet.looks_like_tablet(title)
    known = gadget.BRAND.search(title) or tv.BRAND.search(title) or watch.BRAND.search(title)
    return "likely" if says and known and not PARTS.search(title) else "other"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _key(shop: str, title: str) -> str:
    return f"{shop}|{' '.join(title.split()).lower()}"


def find(s: Session, seen: dict | None = None, now: datetime | None = None) -> list[dict]:
    """Every hidden in-stock title not looked at yet, the surest first."""
    now = now or datetime.now(timezone.utc)
    seen = _load(SEEN) if seen is None else seen
    first = dict(s.execute(select(PriceObservation.offer_id, func.min(PriceObservation.observed_at)).group_by(PriceObservation.offer_id)).all())
    out: dict[str, dict] = {}
    q = select(Offer, Store.slug).join(Store, Store.id == Offer.store_id).where(
        Offer.in_stock.is_(True), Offer.match_status.in_(("not_phone", "no_storage", "review")))
    for o, shop in s.execute(q):
        key = _key(shop, o.raw_title)
        checked = o.last_checked if o.last_checked.tzinfo else o.last_checked.replace(tzinfo=timezone.utc)
        if key in out or key in seen or now - checked > timedelta(days=2):
            continue
        since = first.get(o.id) or checked
        since = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
        out[key] = {"kind": kind(o.raw_title, o.match_status, (now - since).days), "shop": shop, "title": " ".join(o.raw_title.split())[:200],
                    "price": float(o.price_jod), "status": o.match_status, "key": key}
    order = {"sure": 0, "likely": 1, "other": 2}
    return sorted(out.values(), key=lambda r: (order[r["kind"]], r["shop"], r["title"]))


def write(s: Session, path: Path = REPORT, seen: dict | None = None) -> dict[str, int]:
    rows = find(s, seen)
    counts = {k: sum(r["kind"] == k for r in rows) for k in ("sure", "likely", "other")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "counts": counts, "titles": rows}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return counts


def mark_seen(report: Path = REPORT, seen_path: Path = SEEN) -> int:
    """Everything in the last report has been looked at (only the titles in it: newer ones stay on the list)."""
    seen = _load(seen_path)
    day = datetime.now(timezone.utc).date().isoformat()
    new = [r["key"] for r in _load(report).get("titles", []) if r["key"] not in seen]
    seen.update({k: day for k in new})
    tmp = seen_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(seen_path)
    return len(new)
