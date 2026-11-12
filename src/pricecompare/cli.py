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
# Each shop lists its phone section, its tablet section (2026-11-11) and its laptop section (2026-11-12, Stage 3:
# robots.txt of every laptop address checked that day); Platinum and Darwish are read from their sitemaps.
# City Center and Action laptops are not read: their titles almost never give the exact processor.
SOURCES = {
    "smartbuy": ("SmartBuy", "https://smartbuy-me.com", "shopify_json", "unknown", {"handles": ["mobile-phone", "tablets", "laptops", "notebooks", "gaming-notebook", "macbook", "mac-book"]}),
    "igeek": ("iGeek Megastore", "https://igeekjo.com", "shopify_json", "green", {"handles": ["mobile-phones", "laptops-1"]}),  # added 2026-11-12
    "estorejo": ("eStoreJO", "https://estorejo.com", "shopify_json", "amber", {"handles": ["iphone", "ipad", "macbook-air", "macbook-pro", "macbook-neo"]}),
    "iservice": ("iService", "https://iservicejo.com", "woocommerce_html", "green", {"listings": [
        f"https://iservicejo.com/store/mobile-phones/{b}/"
        for b in ("iphone", "samsung", "xiaomi", "honor", "infinix", "tecno", "realme")]
        + ["https://iservicejo.com/store/tablets/", "https://iservicejo.com/store/laptops/"]}),
    "leaders": ("Leaders Center", "https://leaders.jo", "woocommerce_html", "green", {"listings": [
        "https://leaders.jo/en/product-category/all-products/electronics/mobiles/mobile-devices/",
        "https://leaders.jo/en/product-category/all-products/electronics/tablets-and-accessories/tablets/",
        "https://leaders.jo/en/product-category/all-products/electronics/laptops/"]}),
    "alaryan": ("Al-Aryan Mobile", "https://alaryanmobile.com", "woocommerce_html", "green", {"listings": [
        "https://alaryanmobile.com/product-category/mobile-phones/",
        "https://alaryanmobile.com/product-category/laptops-tablets/tablets/",
        "https://alaryanmobile.com/product-category/laptops-tablets/mac/"]}),
    "ammar": ("Ammar Mobile", "https://ammarmobile.com", "opencart_html", "green", {"listings": [
        "https://ammarmobile.com/en-gb/category/mobile-phones-smartphones-latest-devices",
        "https://ammarmobile.com/en-gb/category/AMMAR-TABLETS-CATEGORY",
        "https://ammarmobile.com/en-gb/category/laptops-gaming-business-student-everyday-jordan"]}),
    "gts": ("GTS", "https://gts.jo", "opencart_html", "amber", {"listings": ["https://gts.jo/phone-tablets/mobile", "https://gts.jo/phone-tablets/tablets", "https://gts.jo/computers/laptops"]}),
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
        if cmd == "push-health":
            from . import health
            health.main(s)
            return
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


def run_grow(dry_run: bool, block: list[str] | None) -> None:
    """Nightly: add new models that several shops agree on (see matching/grow.py). --block undoes one."""
    import json, os
    from .matching import grow
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        if block:
            print("listings back to review:", grow.block_model(s, block[0], block[1]))
            s.commit()
            return
        r = grow.auto_grow(s, dry_run=dry_run)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        if not dry_run:
            s.commit()
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:  # shown on the run's page
            with open(summary, "a", encoding="utf-8") as f:
                lines = "".join(f"- {x}\n" for x in r["added"]) or "none\n"
                f.write("## New products added to the catalog\n" + lines)
                f.write("\n## Not added yet (checked again every night)\n" + "".join(f"- {x}\n" for x in r["not_yet"]))


def main() -> None:
    ap = argparse.ArgumentParser(prog="pricecompare")
    sub = ap.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("source", choices=sorted(SOURCES))
    c.add_argument("--dry-run", action="store_true")
    cr = sub.add_parser("clicks-report", help="private Go-to-shop click report (private project only)")
    cr.add_argument("--csv", help="also save the raw counts to this file")
    g = sub.add_parser("auto-grow")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--block", nargs=2, metavar=("BRAND", "FAMILY"), help="remove a wrong model for good")
    for name in ("propose-catalog", "grow-catalog", "seed-catalog", "match", "report", "audit-sample", "build-site", "build-web", "indexnow-prepare", "indexnow-send", "push-health"):
        sub.add_parser(name)
    a = ap.parse_args()
    if a.command == "collect":
        run_source(a.source, a.dry_run)
    elif a.command == "clicks-report":
        from . import clicks
        clicks.main(a.csv)
    elif a.command == "auto-grow":
        run_grow(a.dry_run, a.block)
    else:
        run_matching(a.command)


if __name__ == "__main__":
    main()
