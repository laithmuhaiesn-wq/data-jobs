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

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import report
from .clicks import DATABASE_ID
from .db.models import AuditLog, CollectionRun, Offer, Source, Store


def _iso(d: datetime | None) -> str | None:
    if d is None:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).isoformat(timespec="minutes")


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
    added = [json.loads(a.detail or "{}") | {"at": _iso(a.at)} for a in s.scalars(
        select(AuditLog).where(AuditLog.action == "catalog_add", AuditLog.at >= now - timedelta(days=14)).order_by(AuditLog.at.desc()))]
    return {
        "at": _iso(now),
        "products": base["variants_total"], "at_2plus": base["variants_in_2plus_shops"], "at_3plus": base["variants_in_3plus_shops"],
        "offers": base["phone_offers_with_storage"], "matched_pct": base["matched_pct"], "fresh_48h_pct": base["fresh_48h_pct"],
        "review_queue": s.scalar(select(func.count()).select_from(Offer).where(Offer.match_status == "review")),
        "suspicious_prices": base["suspicious_prices"], "price_changes": base["history_rows"],
        "shops": shops,
        "catalog_added_14d": [{"name": f"{a.get('brand', '')} {a.get('family', '')}".strip(), "way": a.get("way", ""), "at": a["at"]}
                              for a in added],
    }


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
    push(stats, token, account)
    print(f"health: stored ({stats['products']} products, {len(stats['shops'])} shops)")
