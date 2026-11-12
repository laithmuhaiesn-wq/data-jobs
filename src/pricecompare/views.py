"""What users see: one record per phone variant with its offers (shared by the static page and the API)."""
from __future__ import annotations

from urllib.parse import urlsplit

from .matching.parse import category_of

import re

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .blocklist import is_blocked
from .db.models import Brand, Offer, PhoneModel, PhoneVariant, PriceObservation, Store
from .display import BRAND_AR, model_name, plain, storage_label
from .report import _aware, suspicious_offer_ids

STALE_AFTER = timedelta(hours=48)
DROP_WINDOW = timedelta(days=7)    # a price cut by the shop itself counts as a "drop" for this long
HISTORY_DAYS = 90


def offer_timelines(s: Session) -> dict[int, list[tuple[datetime, float, bool]]]:
    """Every recorded change of each offer, oldest first: (time, price, in stock)."""
    out: dict[int, list[tuple[datetime, float, bool]]] = {}
    for oid, price, stock, at in s.execute(select(PriceObservation.offer_id, PriceObservation.price_jod, PriceObservation.in_stock,
                                                  PriceObservation.observed_at).order_by(PriceObservation.observed_at, PriceObservation.id)):
        out.setdefault(oid, []).append((_aware(at), float(price), bool(stock)))
    return out


def price_before(timeline: list[tuple[datetime, float, bool]], now: datetime) -> tuple[float, datetime] | None:
    """The earlier price of the same shop when it changed the price within DROP_WINDOW: (old price, time of the change)."""
    for i in range(len(timeline) - 1, 0, -1):
        at, price, _ = timeline[i]
        old = timeline[i - 1][1]
        if old != price:  # the latest real price change (stock-only changes are skipped)
            return (old, at) if at >= now - DROP_WINDOW else None
    return None


def best_price_history(timelines: list[list[tuple[datetime, float, bool]]], now: datetime) -> list[dict]:
    """Lowest in-stock price across the offers of one phone at the end of each day (UTC), for the last HISTORY_DAYS.
    Days are collapsed so shops collected a few minutes apart never look like a price move."""
    events = sorted((at, i, price, stock) for i, tl in enumerate(timelines) for at, price, stock in tl)
    state: dict[int, tuple[float, bool]] = {}
    days: dict[str, float | None] = {}
    for at, i, price, stock in events:
        state[i] = (price, stock)
        live = [p for p, ok in state.values() if ok]
        days[at.date().isoformat()] = min(live) if live else None
    first = (now - timedelta(days=HISTORY_DAYS)).date().isoformat()
    points = [{"d": d, "p": p} for d, p in sorted(days.items()) if p is not None and d >= first]
    out: list[dict] = []
    for pt in points:  # keep only the days where the price moved, plus the first day
        if not out or out[-1]["p"] != pt["p"]:
            out.append(pt)
    return out


def price_record(history: list[dict], best: float | None) -> dict:
    """The lowest and highest best price we have recorded, with the day each started, and a verdict on today's price:
    "lowest" (today is the lowest we recorded), "above_low" (it was cheaper before), "flat" (never moved) or None."""
    if not history:
        return {"tracked_since": None, "record_low": None, "record_low_at": None, "record_high": None, "record_high_at": None,
                "verdict": None}
    low = min(history, key=lambda h: (h["p"], h["d"]))
    high = max(history, key=lambda h: (h["p"], [-ord(c) for c in h["d"]]))  # the first day it reached that price
    if len(history) == 1:
        verdict = "flat"
    elif best is not None and best <= low["p"]:
        verdict = "lowest"
    elif best is not None:
        verdict = "above_low"
    else:
        verdict = None
    return {"tracked_since": history[0]["d"], "record_low": low["p"], "record_low_at": low["d"],
            "record_high": high["p"], "record_high_at": high["d"], "verdict": verdict}


_THUMB = re.compile(r"-\d{2,4}x\d{2,4}(?=\.(?:jpe?g|png|webp)$)", re.I)


def safe_link(url: str | None, shop_site: str | None = None) -> str | None:
    """A link the app may open or load: a normal web address only, and (for a shop's product page) on that shop's own
    site. A shop page is outside our control; if one ever carried a strange link, it must not reach people's phones."""
    try:
        u = urlsplit(url or "")
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname or len(url) > 600:
        return None
    if shop_site:
        home = (urlsplit(shop_site).hostname or "").removeprefix("www.")
        if not home or not (u.hostname == home or u.hostname.endswith("." + home)):
            return None
    return url


def full_size_first(url: str) -> list[str]:
    """WordPress shops serve thumbnails like name-600x338.webp; the original is the same name without the size."""
    full = _THUMB.sub("", url)
    return [full, url] if full != url else [url]


def build_variant_data(s: Session, now: datetime | None = None) -> list[dict]:
    """Rules: gray-market, out-of-stock, stale (>48 h), installment and suspicious prices are shown but never ranked."""
    now = now or datetime.now(timezone.utc)
    odd = suspicious_offer_ids(s)
    stores = {st.id: st.name for st in s.scalars(select(Store))}
    sites = {st.id: st.site_url for st in s.scalars(select(Store))}
    groups: dict[int, list[Offer]] = {}
    for o in s.scalars(select(Offer).where(Offer.match_status == "matched")):
        groups.setdefault(o.variant_id, []).append(o)
    try:  # the picture column is added by the nightly run; the API must keep working before that
        images = dict(s.execute(select(Offer.id, Offer.image_url)).all())
    except Exception:
        s.rollback()
        images = {}
    timelines = offer_timelines(s)
    variants = {v.id: v for v in s.scalars(select(PhoneVariant))}  # three queries instead of three per phone
    models = {m.id: m for m in s.scalars(select(PhoneModel))}
    brands = {b.id: b for b in s.scalars(select(Brand))}
    data = []
    for vid, offers in groups.items():
        v = variants[vid]
        m = models[v.model_id]
        b = brands[m.brand_id]
        market = v.market_version
        esim = v.connectivity == "esim_only"  # a different product from the normal SIM version
        # a tablet with a SIM slot is a different product from the Wi-Fi one
        net = {"esim_only": " eSIM", "wifi": " Wi-Fi", "cellular": " Wi-Fi + Cellular"}.get(v.connectivity, "")
        gray = market not in ("unknown", "jordan")
        # a non-official version says so in its name, so lists never show two identical names
        net += f" ({market.capitalize() if market != 'india' else 'Indian'} version)" if gray else ""
        rows = []
        offers = [o for o in offers if safe_link(o.url, sites[o.store_id])]
        if not offers:
            continue
        for o in offers:
            stale = _aware(o.last_checked) < now - STALE_AFTER
            rank = bool(o.in_stock and o.id not in odd and not stale and o.price_type == "cash" and not gray)
            before = price_before(timelines.get(o.id, []), now) if o.id not in odd else None
            rows.append({"oid": o.id, "store": stores[o.store_id], "price": float(o.price_jod), "url": o.url, "stock": bool(o.in_stock),
                         "stale": stale, "rank": rank, "checked": _aware(o.last_checked).isoformat(),
                         "was": before[0] if before else None, "changed": before[1].isoformat() if before else None})
        pics = sorted(offers, key=lambda o: (not (o.in_stock and o.id not in odd), float(o.price_jod)))
        seen_shops: set[int] = set()
        pictures: list[str] = []  # one picture per shop, top shop first; the app skips poor ones
        for o in pics:
            if safe_link(images.get(o.id)) and o.store_id not in seen_shops and not is_blocked(images[o.id]):
                seen_shops.add(o.store_id)
                pictures += full_size_first(images[o.id])
        pictures = list(dict.fromkeys(pictures))[:8]
        one_per_store: dict[str, dict] = {}  # colours are separate offers; show a shop once, at its best price
        for r in sorted(rows, key=lambda r: (not r["rank"], r["price"])):
            one_per_store.setdefault(r["store"], r)
        rows = sorted(one_per_store.values(), key=lambda r: (not r["rank"], r["price"]))
        ranked = [r["price"] for r in rows if r["rank"]]
        name = model_name(b.name_en, m.family)
        # RAM is shown only for phones that really come in several RAM sizes (the matcher sets ram_gb only then)
        size = storage_label(v.storage_gb) + (f" / {v.ram_gb}GB RAM" if v.ram_gb else "")
        best = next((r for r in rows if r["rank"]), None)
        was = best["was"] if best and best["was"] and best["was"] > best["price"] else None  # the best shop cut its own price
        history = best_price_history([timelines.get(o.id, []) for o in offers
                                      if o.id not in odd and o.price_type == "cash"], now)
        lows = [h["p"] for h in history]
        data.append({"id": vid, "brand": b.name_en, "brand_ar": BRAND_AR.get(b.name_en, b.name_en), "model": name,
                     "storage_gb": v.storage_gb, "ram_gb": v.ram_gb, "storage": size + net, "category": category_of(m.family),
                     "label": f"{name} {size}{net}", "slug": f"{vid}-" + plain(f"{name} {size}{net}"), "market": market, "gray": gray, "image": pictures[0] if pictures else None, "images": pictures,
                     "best_price": min(ranked) if ranked else None,
                     "best_store": next((r["store"] for r in rows if r["rank"]), None),
                     "highest_price": max(ranked) if ranked else None,
                     "save": round(max(ranked) - min(ranked), 3) if len(ranked) > 1 else 0,
                     "ranked_shops": len(ranked), "shops": len(rows), "offers": rows,
                     "was": was, "drop": round(was - best["price"], 3) if was else 0,
                     "drop_pct": round(100 * (was - best["price"]) / was, 1) if was else 0,
                     "dropped_at": best["changed"] if was else None,
                     "lowest": min(lows) if lows else None,
                     "at_lowest": bool(ranked and len(history) > 1 and min(ranked) <= min(lows)),
                     "history": history, **price_record(history, min(ranked) if ranked else None)})
    data.sort(key=lambda d: d["label"])
    return data
