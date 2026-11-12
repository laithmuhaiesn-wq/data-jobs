from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from .collectors import darwish, action, opencart, platinum, shopify, woocommerce
from .collectors.base import PoliteClient
from .db.models import CollectionRun, Source
from .db.session import get_engine, init_db, make_session
from . import report
from .matching import matcher
from .store import ensure_store, save_offers

# slug -> name, base url, method, terms rating, params. Handles/URLs confirmed in dry runs.
# Each shop lists its phone section and (since 2026-11-11) its tablet section; Platinum is read from its sitemap.
SOURCES = {
    "smartbuy": ("SmartBuy", "https://smartbuy-me.com", "shopify_json", "unknown", {"handles": ["mobile-phone", "tablets"]}),
    "estorejo": ("eStoreJO", "https://estorejo.com", "shopify_json", "amber", {"handles": ["iphone", "ipad"]}),
    "iservice": ("iService", "https://iservicejo.com", "woocommerce_html", "green", {"listings": [
        f"https://iservicejo.com/store/mobile-phones/{b}/"
        for b in ("iphone", "samsung", "xiaomi", "honor", "infinix", "tecno", "realme")]
        + ["https://iservicejo.com/store/tablets/"]}),
    "leaders": ("Leaders Center", "https://leaders.jo", "woocommerce_html", "green", {"listings": [
        "https://leaders.jo/en/product-category/all-products/electronics/mobiles/mobile-devices/",
        "https://leaders.jo/en/product-category/all-products/electronics/tablets-and-accessories/tablets/"]}),
    "alaryan": ("Al-Aryan Mobile", "https://alaryanmobile.com", "woocommerce_html", "green", {"listings": [
        "https://alaryanmobile.com/product-category/mobile-phones/",
        "https://alaryanmobile.com/product-category/laptops-tablets/tablets/"]}),
    "ammar": ("Ammar Mobile", "https://ammarmobile.com", "opencart_html", "green", {"listings": [
        "https://ammarmobile.com/en-gb/category/mobile-phones-smartphones-latest-devices",
        "https://ammarmobile.com/en-gb/category/AMMAR-TABLETS-CATEGORY"]}),
    "gts": ("GTS", "https://gts.jo", "opencart_html", "amber", {"listings": ["https://gts.jo/phone-tablets/mobile", "https://gts.jo/phone-tablets/tablets"]}),
    "citycenter": ("City Center", "https://citycenter.jo", "opencart_html", "green", {"listings": [
        "https://citycenter.jo/electronics/electronics-smartphone",
        "https://citycenter.jo/pc-and-laptops/pc-and-laptops-tablet-pc"]}),
    "action": ("Action", "https://action.jo", "nuxt_html", "amber", {"listings": ["https://action.jo/en/category/smartphones", "https://action.jo/en/category/tablets"]}),
    "platinum": ("Platinum", "https://www.platinum-jo.com", "sitemap_pages", "green", {}),
    # Magento; home page is behind a bot challenge (never fetched), sitemap and product pages are open. Owner asked for it 2026-11-12.
    "darwish": ("Darwish Electronics", "https://darwishelectronics.jo", "darwish_sitemap", "amber", {}),
}
CATALOG_CSV = Path(__file__).resolve().parents[2] / "data" / "catalog.csv"


def fetch_offers(slug: str, client: PoliteClient):
    _, base, method, _, params = SOURCES[slug]
    if method == "shopify_json":
        out = []
        for h in params["handles"]:
            out.extend(shopify.collect(client, base, h))
        return out
    if method == "woocommerce_html":
        return woocommerce.collect(client, slug, params["listings"])
    if method == "nuxt_html":
        out = {}
        for listing in params["listings"]:
            for o in action.collect(client, base, listing):
                out[o.external_id] = o
        return list(out.values())
    if method == "opencart_html":
        return opencart.collect(client, params["listings"])
    if method == "darwish_sitemap":
        return darwish.collect(client, base)
    return platinum.collect(client, base)


def run_source(slug: str, dry_run: bool) -> None:
    name, base, method, rating, _ = SOURCES[slug]
    client = PoliteClient()
    try:
        offers = fetch_offers(slug, client)
    except Exception as e:  # a crash must show up in the run log, or reliability numbers lie
        if not dry_run:
            engine = get_engine()
            init_db(engine)
            with make_session(engine) as s:
                store = ensure_store(s, slug, name, base, method, rating)
                src = s.query(Source).filter_by(store_id=store.id).one()
                src.consecutive_failures = (src.consecutive_failures or 0) + 1
                s.add(CollectionRun(store_id=store.id, requests=client.request_count, status="failed",
                                    finished_at=datetime.now(timezone.utc), error=f"{type(e).__name__}: {e}"[:500]))
                s.commit()
        raise
    print(f"{slug}: {len(offers)} offers, {client.request_count} requests")
    for o in offers[:5]:
        print(" ", o.price_jod, o.in_stock, o.title)
    if dry_run:
        return
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        store = ensure_store(s, slug, name, base, method, rating)
        src = s.query(Source).filter_by(store_id=store.id).one()
        if not src.enabled:
            print("source disabled, skipping")
            return
        run = CollectionRun(store_id=store.id, requests=client.request_count)
        s.add(run)
        save_offers(s, store, offers, run)
        run.status, run.finished_at = "ok", datetime.now(timezone.utc)
        src.consecutive_failures = 0
        s.commit()
        print(f"saved: {run.items_seen} seen, {run.items_changed} changed")


def run_matching(cmd: str) -> None:
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        if cmd == "propose-catalog":
            for brand, family, n in matcher.propose_catalog(s):
                print(f"{brand},{family},{n}")
            return
        if cmd == "report":
            import json
            print(json.dumps(report.compute(s), indent=2))
            return
        if cmd == "build-site":
            from . import site
            print("variants on page:", site.build(s, Path(__file__).resolve().parents[2] / "site"))
            return
        if cmd == "build-web":
            from . import website
            root = Path(__file__).resolve().parents[2]
            from sqlalchemy import select as _select

            from .db.models import Store as _Store
            sites = {name: url for name, url in s.execute(_select(_Store.name, _Store.site_url)).all()}
            stats = website.build(s, root / "web_build", root / "web", shop_sites=sites)
            print("website:", stats)
            if stats["products"] < 50:  # never publish a nearly empty site over the real one
                raise SystemExit("too few products for a website build; not publishing")
            return
        if cmd in ("indexnow-prepare", "indexnow-send"):
            from . import indexnow
            root = Path(__file__).resolve().parents[2]
            listing = root / "indexnow-urls.txt"
            if cmd == "indexnow-prepare":
                print("new addresses:", indexnow.prepare(root / "web_build" / "sitemap.xml", listing))
            else:
                print("indexnow answer:", indexnow.send(listing))
            return
        if cmd == "audit-sample":
            for row in report.audit_sample(s):
                print(" | ".join(str(x) for x in row))
            return
        if cmd == "grow-catalog":
            print("families appended:", matcher.grow_catalog(s, CATALOG_CSV))
            return
        if cmd == "seed-catalog":
            print("models added:", matcher.load_catalog(s, CATALOG_CSV))
        else:
            print(matcher.match_offers(s))
        s.commit()


def main() -> None:
    ap = argparse.ArgumentParser(prog="pricecompare")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("source", choices=sorted(SOURCES))
    c.add_argument("--dry-run", action="store_true")
    for name in ("propose-catalog", "grow-catalog", "seed-catalog", "match", "report", "audit-sample", "build-site", "build-web", "indexnow-prepare", "indexnow-send"):
        sub.add_parser(name)
    a = ap.parse_args()
    if a.command == "collect":
        run_source(a.source, a.dry_run)
    else:
        run_matching(a.command)


if __name__ == "__main__":
    main()
