"""Data health for the owner's admin dashboard (derbani.com/admin).

Every hour the runner computes these numbers from the price database and stores them in the Cloudflare D1
database `derbani-clicks` (table `stats`), where the dashboard reads them. They hold no personal data and no
secrets: shop collection results, product counts, freshness, the review queue and new catalog models.
Nothing is printed except a one-line confirmation, so the public runner logs stay clean.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import report
from .clicks import DATABASE_ID
from .display import LIVE_CATEGORIES, model_name
from .matching.gadget import PREFIX
from .matching.parse import category_of
from .db.models import AuditLog, CollectionRun, Offer, Source, Store


def _iso(d: datetime | None) -> str | None:
    if d is None:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat(timespec="minutes")


def _accuracy(s: Session, now: datetime) -> list[dict]:
    from .db.models import PhoneVariant, PhoneModel, Brand
    from .report import accuracy_check
    from .display import storage_label
    from .matching.gadget import size_label
    rows = []
    for vid, a in sorted(accuracy_check(s, now).items(), key=lambda kv: -kv[1]["ratio"])[:60]:
        v = s.get(PhoneVariant, vid)
        m = s.get(PhoneModel, v.model_id)
        b = s.get(Brand, m.brand_id)
        cat, gb = category_of(m.family), v.storage_gb
        size = (size_label(cat, gb) if cat in PREFIX else f'{gb}"' if cat == "tv" else f"{gb}mm" if cat == "watch"
                else storage_label(gb)) if gb else ""
        rows.append({"name": f"{_shown_name(b.name_en, m.family)} {size}".strip(),
                     "ratio": a["ratio"], "hidden": a["hidden"],
                     "offers": [{"shop": sh, "price": p, "title": t, "url": u} for sh, p, t, u in a["offers"][:12]]})
    return rows


def _shown_name(brand: str, family: str) -> str:
    """The product's name as the site shows it ("Sony PlayStation 5 Pro", not "console playstation 5 pro")."""
    from .matching import gadget, laptop, tv, watch
    try:
        cat = category_of(family)
        if cat in gadget.PREFIX:
            return gadget.pretty(brand, family)
        return {"laptop": laptop.pretty, "tv": tv.pretty, "watch": watch.pretty}.get(cat, model_name)(brand, family)
    except Exception:            # a name must never break the dashboard
        return f"{brand} {family}".strip()


def category_check(s: Session, category: str, now: datetime, n_match: int = 50, n_price: int = 20) -> dict:
    """The owner's hand check before a new category goes live (plan Stage 3): random matches (shop title -> our product)
    and random prices, each with the shop link. The same sample all day, a new one the next day."""
    import random

    from .display import storage_label
    from .matching.laptop import pretty
    from .matching.tv import pretty as tv_pretty
    from .matching.parse import category_of
    from .db.models import Brand, PhoneModel, PhoneVariant

    stores = {st.id: st.name for st in s.scalars(select(Store))}
    rows = s.execute(select(Offer, PhoneVariant, PhoneModel, Brand).join(PhoneVariant, Offer.variant_id == PhoneVariant.id)
                     .join(PhoneModel, PhoneVariant.model_id == PhoneModel.id).join(Brand, PhoneModel.brand_id == Brand.id)
                     .where(Offer.match_status == "matched")).all()
    mine = [(o, v, m, b) for o, v, m, b in rows if category_of(m.family) == category]
    rng = random.Random(f"{category}-{now:%Y-%m-%d}")
    rng.shuffle(mine)
    if category == "watch":
        from .matching.watch import pretty as watch_pretty
        label = lambda v, m, b: (f"{watch_pretty(b.name_en, m.family)} {str(v.storage_gb) + 'mm ' if v.storage_gb else ''}"
                                 f"{'GPS + Cellular' if v.connectivity == 'cellular' else 'GPS'}")
    elif category in PREFIX:
        from .matching.gadget import pretty as gadget_pretty, size_label
        label = lambda v, m, b: (f"{gadget_pretty(b.name_en, m.family)} {size_label(category, v.storage_gb)}"
                                 + (f" / {v.ram_gb}GB RAM" if v.ram_gb else "")).strip()
    else:
        label = lambda v, m, b: tv_pretty(b.name_en, m.family) if category == "tv" else \
            (pretty(b.name_en, m.family) if category == "laptop" else m.family) + \
            f" {storage_label(v.storage_gb)}" + (f" / {v.ram_gb}GB RAM" if v.ram_gb else "")
    products = {v.id for _, v, _, _ in mine}
    shops_per = {}
    for o, v, _, _ in mine:
        shops_per.setdefault(v.id, set()).add(o.store_id)
    return {
        "category": category, "products": len(products), "listings": len(mine),
        "at_2plus": sum(1 for x in shops_per.values() if len(x) >= 2),
        "matches": [{"shop": stores[o.store_id], "title": o.raw_title[:200], "product": label(v, m, b), "url": o.url if o.url.startswith("https://") else ""}
                    for o, v, m, b in mine[:n_match]],
        "prices": [{"shop": stores[o.store_id], "product": label(v, m, b), "price": float(o.price_jod), "url": o.url if o.url.startswith("https://") else ""}
                   for o, v, m, b in mine[n_match:n_match + n_price] or mine[:n_price]],
    }


def _note(detail: str | None) -> dict:
    """An audit note; an old note cut at 500 characters is shown as text, not a crash (2026-11-23)."""
    try:
        return json.loads(detail or "{}")
    except ValueError:
        return {"note": (detail or "")[:200]}


def compute(s: Session, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    base = report.compute(s, now)
    shops = []
    for st in s.scalars(select(Store).order_by(Store.name)):
        src = s.scalar(select(Source).where(Source.store_id == st.id))
        last = s.scalar(select(CollectionRun).where(CollectionRun.store_id == st.id).order_by(CollectionRun.started_at.desc()))
        ok = s.scalar(select(CollectionRun).where(CollectionRun.store_id == st.id, CollectionRun.status == "ok")
                      .order_by(CollectionRun.started_at.desc()))
        week = list(s.scalars(select(CollectionRun).where(CollectionRun.store_id == st.id,
                                                          CollectionRun.started_at >= now - timedelta(days=7))))
        p = base["per_shop"].get(st.slug, {})
        shops.append({
            "shop": st.name, "enabled": bool(src.enabled) if src else False,
            "last_run": _iso(last.started_at) if last else None, "last_status": last.status if last else None,
            "last_error": (last.error or "")[:160] if last and last.status != "ok" else "",
            "last_ok": _iso(ok.finished_at or ok.started_at) if ok else None,
            "items": ok.items_seen if ok else 0, "offers": p.get("phone_offers", 0), "matched": p.get("matched", 0),
            "runs_7d": len(week), "ok_7d": sum(1 for r in week if r.status == "ok"),
        })
    added = [_note(a.detail) | {"at": _iso(a.at)} for a in s.scalars(
        select(AuditLog).where(AuditLog.action == "catalog_add", AuditLog.at >= now - timedelta(days=14)).order_by(AuditLog.at.desc()))]
    return {
        "at": _iso(now),
        "products": base["variants_total"], "at_2plus": base["variants_in_2plus_shops"], "at_3plus": base["variants_in_3plus_shops"],
        "offers": base["phone_offers_with_storage"], "matched_pct": base["matched_pct"], "fresh_48h_pct": base["fresh_48h_pct"],
        "review_queue": s.scalar(select(func.count()).select_from(Offer).where(Offer.match_status == "review")),
        "suspicious_prices": base["suspicious_prices"], "price_changes": base["history_rows"],
        "shops": shops,
        # categories collected but not yet shown to visitors: the owner's hand check before switching them on
        "pending": [category_check(s, c, now) for c in ("laptop", "tv", "watch", *PREFIX) if c not in LIVE_CATEGORIES],
        # the hourly accuracy check: hidden products (prices 2x+ apart) and ones to look at (1.5x to 2x)
        "accuracy": _accuracy(s, now),
        # each new product with its kind (the admin page filters by it) and the name visitors see
        "catalog_added_14d": [{"name": _shown_name(a.get("brand", ""), a.get("family", "")), "way": a.get("way", ""), "at": a["at"],
                               "cat": category_of(a.get("family", "")) if a.get("family") else "phone"} for a in added],
    }


ZONE_ID = "c8528b57fabc6d1581ea6f7e07102663"  # derbani.com in the owner's Cloudflare account (not a secret)
TRAFFIC_QUERY = """query ($zone: String!, $since: Date!, $until: Date!) {
  viewer { zones(filter: {zoneTag: $zone}) {
    httpRequests1dGroups(limit: 40, orderBy: [date_ASC], filter: {date_geq: $since, date_leq: $until}) {
      dimensions { date }
      sum { requests pageViews countryMap { clientCountryName requests } }
      uniq { uniques }
    } } } }"""


def fetch_traffic(token: str, days: int = 30, client: httpx.Client | None = None, today: datetime | None = None) -> list[dict]:
    """Daily derbani.com traffic from Cloudflare's own counts (visitors = distinct addresses per day, as Cloudflare
    counts them; page views = HTML pages served, which include some bots). Needs "Analytics Read" on the token."""
    c = client or httpx.Client(timeout=60)
    end = (today or datetime.now(timezone.utc)).date()
    r = c.post("https://api.cloudflare.com/client/v4/graphql", headers={"Authorization": f"Bearer {token}"},
               json={"query": TRAFFIC_QUERY, "variables": {"zone": ZONE_ID, "since": str(end - timedelta(days=days - 1)), "until": str(end)}})
    r.raise_for_status()
    body = r.json()
    if body.get("errors"):
        raise RuntimeError(f"Cloudflare analytics: {body['errors'][0].get('message')}")
    out = []
    for g in body["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]:
        countries = sorted(g["sum"]["countryMap"], key=lambda x: -x["requests"])[:5]
        out.append({"day": g["dimensions"]["date"], "visitors": g["uniq"]["uniques"], "views": g["sum"]["pageViews"],
                    "requests": g["sum"]["requests"], "countries": [[x["clientCountryName"], x["requests"]] for x in countries]})
    return out


def push(stats: dict, token: str, account: str, client: httpx.Client | None = None) -> None:
    """Store the latest numbers, and one copy per day for trends."""
    c = client or httpx.Client(timeout=60)
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{DATABASE_ID}/query"
    body = json.dumps(stats, ensure_ascii=False, separators=(",", ":"))
    day = stats["at"][:10]
    for sql, params in (
        ("CREATE TABLE IF NOT EXISTS stats (key TEXT PRIMARY KEY, json TEXT NOT NULL, at TEXT NOT NULL)", []),
        ("INSERT INTO stats (key, json, at) VALUES (?1, ?2, ?3) ON CONFLICT (key) DO UPDATE SET json = ?2, at = ?3",
         ["health", body, stats["at"]]),
        ("INSERT INTO stats (key, json, at) VALUES (?1, ?2, ?3) ON CONFLICT (key) DO UPDATE SET json = ?2, at = ?3",
         [f"day:{day}", json.dumps({k: stats[k] for k in ("products", "at_2plus", "at_3plus", "offers", "fresh_48h_pct",
                                                           "review_queue")}), stats["at"]]),
    ):
        r = c.post(url, headers={"Authorization": f"Bearer {token}"}, json={"sql": sql, "params": params})
        r.raise_for_status()
        if not r.json().get("success"):
            raise RuntimeError("Cloudflare D1 write failed")


def main(s: Session) -> None:
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        print("health: no Cloudflare keys, skipped")
        return
    stats = compute(s)
    try:
        stats["traffic"] = fetch_traffic(token)
    except Exception as e:  # traffic is a nice-to-have: the health numbers still go in
        stats["traffic"] = None
        stats["traffic_error"] = str(e)[:200]
    push(stats, token, account)
    print(f"health: stored ({stats['products']} products, {len(stats['shops'])} shops, traffic "
          + ("ok" if stats.get("traffic") is not None else "failed: " + stats.get("traffic_error", "")) + ")")


# ---- shop problems, found by themselves every few hours (owner 2026-11-21: "must be automated") ----
WAITING = ("blocked", "limited")   # the shop asked us to stop or slow down (bot check, 403, 429): never worked around


def shop_problems(s: Session, now: datetime | None = None) -> list[dict]:
    """Each enabled shop that needs something, with what kind:
      "broken":  our reader fails or suddenly finds far fewer listings (the shop changed its site) -> the code is fixed
      "waiting": the shop asked us to wait (bot check, 403, 429) -> nothing is tried around it; its old prices leave
                 "best price" after 48 h by themselves and it comes back when the shop answers again
      "stale":   most of its listings were not read in the last day for another reason
    """
    now = now or datetime.now(timezone.utc)
    aware = lambda d: d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)
    out = []
    for st in s.scalars(select(Store).order_by(Store.slug)):
        src = s.scalar(select(Source).where(Source.store_id == st.id))
        if not (src and src.enabled):
            continue
        runs = list(s.scalars(select(CollectionRun).where(CollectionRun.store_id == st.id,
                                                          CollectionRun.started_at >= now - timedelta(days=7))
                              .order_by(CollectionRun.started_at.desc())))
        if not runs:
            out.append({"shop": st.slug, "kind": "stale", "detail": "no read at all in 7 days"})
            continue
        last = runs[0]
        ok = [r for r in runs if r.status == "ok"]
        recent = [o for o in s.scalars(select(Offer).where(Offer.store_id == st.id,
                                                           Offer.last_checked >= now - timedelta(days=7)))]
        fresh = sum(1 for o in recent if aware(o.last_checked) >= now - timedelta(hours=30))   # nightly shops: once a day
        share = fresh / len(recent) if recent else 1.0
        if last.status in WAITING:
            out.append({"shop": st.slug, "kind": "waiting", "detail": f"{last.status}: {(last.error or '')[:120]}",
                        "fresh_24h": round(share, 2)})
        elif len(runs) >= 2 and all(r.status == "failed" for r in runs[:2]):
            out.append({"shop": st.slug, "kind": "broken", "detail": f"last 2 reads failed: {(last.error or '')[:160]}"})
        elif last.status == "ok" and last.items_seen == 0 and len(ok) >= 2 and ok[1].items_seen == 0:
            out.append({"shop": st.slug, "kind": "broken", "detail": "the last 2 reads found no listings at all"})
        elif share < 0.5 and len(recent) >= 10:
            # its reads end "ok" (or not at all) yet most of its listings were not read again: the reader no longer
            # finds them on the shop's pages (the site changed). A shop's main and electronics reads give very
            # different counts, so counts alone cannot tell this; the listings' own read times can.
            out.append({"shop": st.slug, "kind": "broken" if last.status == "ok" else "stale",
                        "detail": f"only {share:.0%} of its listings read in the last 30 h (last read: {last.status})"})
    return out


def write_shop_problems(s: Session, path: Path | None = None) -> list[dict]:
    path = path or Path.home() / ".derbani" / "shop_problems.json"
    problems = shop_problems(s)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": _iso(datetime.now(timezone.utc)), "problems": problems}, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    return problems
