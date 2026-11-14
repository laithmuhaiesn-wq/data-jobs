from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .collectors import darwish, action, opencart, platinum, shopify, stores, woocommerce
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
    "smartbuy": ("SmartBuy", "https://smartbuy-me.com", "shopify_json", "unknown", {"handles": ["mobile-phone", "apple-watches", "smart-watch", "tablets", "laptops", "notebooks", "gaming-notebook", "macbook", "mac-book", "tvs", "qled-tvs"]}),
    "igeek": ("iGeek Megastore", "https://igeekjo.com", "shopify_json", "green", {"handles": ["mobile-phones", "laptops-1"]}),  # added 2026-11-12
    "estorejo": ("eStoreJO", "https://estorejo.com", "shopify_json", "amber", {"handles": ["iphone", "ipad", "macbook-air", "macbook-pro", "macbook-neo", "apple-watch"]}),
    "iservice": ("iService", "https://iservicejo.com", "woocommerce_html", "green", {"listings": [
        f"https://iservicejo.com/store/mobile-phones/{b}/"
        for b in ("iphone", "samsung", "xiaomi", "honor", "infinix", "tecno", "realme")] + ["https://iservicejo.com/store/apple-watch/"]
        + ["https://iservicejo.com/store/tablets/", "https://iservicejo.com/store/laptops/"]}),
    "leaders": ("Leaders Center", "https://leaders.jo", "woocommerce_html", "green", {"listings": [
        "https://leaders.jo/en/product-category/all-products/electronics/mobiles/mobile-devices/",
        "https://leaders.jo/en/product-category/all-products/electronics/tablets-and-accessories/tablets/",
        "https://leaders.jo/en/product-category/all-products/electronics/laptops/",
        "https://leaders.jo/en/product-category/all-products/home-appliance/tv-and-video-screens/tv-screens/"]}),
    "alaryan": ("Al-Aryan Mobile", "https://alaryanmobile.com", "woocommerce_html", "green", {"listings": [
        "https://alaryanmobile.com/product-category/smart-watches-bands/smart-watches/",
        "https://alaryanmobile.com/product-category/mobile-phones/",
        "https://alaryanmobile.com/product-category/laptops-tablets/tablets/",
        "https://alaryanmobile.com/product-category/laptops-tablets/mac/"]}),
    "ammar": ("Ammar Mobile", "https://ammarmobile.com", "opencart_html", "green", {"listings": [
        "https://ammarmobile.com/en-gb/category/mobile-phones-smartphones-latest-devices",
        "https://ammarmobile.com/en-gb/category/AMMAR-TABLETS-CATEGORY",
        "https://ammarmobile.com/en-gb/category/laptops-gaming-business-student-everyday-jordan"]}),
    "gts": ("GTS", "https://gts.jo", "opencart_html", "amber", {"listings": ["https://gts.jo/phone-tablets/mobile", "https://gts.jo/phone-tablets/smart-watch", "https://gts.jo/phone-tablets/tablets", "https://gts.jo/computers/laptops", "https://gts.jo/tvs-projectors/tvs"]}),
    "citycenter": ("City Center", "https://citycenter.jo", "opencart_html", "green", {"listings": [
        "https://citycenter.jo/electronics/electronics-smartphone",
        "https://citycenter.jo/pc-and-laptops/pc-and-laptops-tablet-pc"]}),
    "action": ("Action", "https://action.jo", "nuxt_html", "amber", {"listings": ["https://action.jo/en/category/smartphones", "https://action.jo/en/category/tablets"]}),
    "platinum": ("Platinum", "https://www.platinum-jo.com", "sitemap_pages", "green", {}),
    # added 2026-11-13 (robots.txt allows our reader; terms read, no rule against automated reading; see data-source-permissions)
    "xmart": ("Xmart", "https://www.xmart.jo/en", "shopify_json", "green", {"handles": ["smartphones", "tablets", "laptops", "tvs", "smart-watches"]}),
    "dna": ("DNA Jordan", "https://dna.jo", "shopify_json", "green",
            {"handles": ["apple-iphone", "mobility-phones", "apple-ipad", "tech-tablets", "tech-laptop"]}),
    "newvision": ("New Vision", "https://newvision.jo", "woocommerce_html", "green",
                  {"listings": ["https://newvision.jo/en/product-category/tvs/"]}),
    "compujordan": ("Compu Jordan", "https://compujordan.com", "opencart_html", "green", {"listings": [
        "https://compujordan.com/electronics/smart-watches",
        "https://compujordan.com/pc-and-laptops/laptops", "https://compujordan.com/pc-and-laptops/tablets",
        "https://compujordan.com/monitor-and-display/tv"]}),
    # added 2026-11-14 from a Jordan store directory; robots.txt allows, no rule against automated reading in the terms
    "osjo": ("Oriental Store", "https://os-jo.com", "opencart_html", "green", {"listings": [
        "https://os-jo.com/computer-systems/laptops", "https://os-jo.com/gaming-in-jordan/gaming-laptop"]}),
    "smartsystems": ("Smart Systems", "https://smartsystems.jo", "opencart_html", "green", {"listings": [
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/laptops-laptop-and-tablet-pcs",
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/tablet-android-laptop-and-tablet-pcs",
        "https://smartsystems.jo/computer-systems/laptop-and-tablet-pcs-computer-systems/tablet-pc-laptop-and-tablet-pcs"]}),
    "midteks": ("Midteks", "https://midteks.com", "opencart_html", "green", {"listings": [
        "https://midteks.com/computer-systems/laptops", "https://midteks.com/gaming/laptops-1",
        "https://midteks.com/computer-systems/tablet", "https://midteks.com/electronics/mobile/mobile-device"]}),
    "cse": ("CSE Jordan", "https://cse.jo", "opencart_html", "green", {"listings": ["https://cse.jo/computer-systems/laptop"]}),
    "almohanad": ("Al-Mohanad Tech", "https://almohanadtech.com", "woocommerce_html", "green", {"listings": [
        "https://almohanadtech.com/product-category/laptops/", "https://almohanadtech.com/product-category/apple-tablets/"]}),
    "pccircle": ("PC Circle", "https://pccircle.com", "woocommerce_html", "green",
                 {"listings": ["https://pccircle.com/product-category/laptops-notebooks/"]}),
    "h4m": ("Hawaii Telecom", "https://h4mjo.com", "woocommerce_html", "green",
            {"listings": ["https://h4mjo.com/smart-phone/", "https://h4mjo.com/tablets/", "https://h4mjo.com/smart-watch/"]}),
    "newton": ("Newton Stores", "https://newtonstores.com", "odoo_html", "green", {"listings": [
        "https://newtonstores.com/shop/category/tvs-home-theatres-tvs-40"]}),
    "profpc": ("The Professional PC", "https://www.theprofpc.com", "site123_html", "green", {"listings": [
        "https://www.theprofpc.com/shop/laptops", "https://www.theprofpc.com/shop/mobiles-and-tablet"]}),
    "alruwwad": ("Al-Ruwwad", "https://al-ruwwad.com", "zoho_html", "green", {"listings": [
        "https://al-ruwwad.com/categories/smart-tv/6640546000000143098", "https://al-ruwwad.com/categories/normal-tv/6640546000000143120"]}),
    # Magento; home page is behind a bot challenge (never fetched), sitemap and product pages are open. Owner asked for it 2026-11-12.
    "darwish": ("Darwish Electronics", "https://darwishelectronics.jo", "darwish_sitemap", "amber", {}),
}
CATALOG_CSV = Path(__file__).resolve().parents[2] / "data" / "catalog.csv"


# Stage 3 electronics sections (2026-11-14): read in their own run (collect --part electronics, every 6 hours) so the hourly
# run stays short. Picked from the section survey (scripts/section_survey.py); robots.txt checked on every fetch as always.
# City Center is left out: its printer page answered with a bot check (we never work around one).
ELECTRONICS = {
    "smartbuy": ["headphones", "speakers", "sound-bar", "gaming-consoles", "monitors", "gaming-monitors", "printers", "imac", "routers", "storage", "cameras", "digital-cameras", "instant-cameras"],
    "xmart": ["headphones-earbuds", "bluetooth-speakers", "home-audio-systems", "storage-devices", "desktop", "gopro"],
    "igeek": ["earbuds-earphones", "headsets", "monitors", "nintendo-switch-2-console", "nintendo-switch-console", "xbox-console", "playstation-5-collection", "network", "power-bank", "internal-storage", "external-storage", "printers"],
    "estorejo": ["airpods", "audio", "imac", "mac-mini", "power-banks"],
    "dna": ["audio-earphones", "audio-headphones", "apple-airpods-audio", "gaming-consoles", "tech-monitors", "accessories-power-banks", "cameras", "tech-routers", "apple-imac"],
    "iservice": [
        "https://iservicejo.com/store/accessories/headphones/",
        "https://iservicejo.com/store/accessories/speakers/",
        "https://iservicejo.com/store/accessories/power-banks/",
        "https://iservicejo.com/store/gaming/",
    ],
    "alaryan": [
        "https://alaryanmobile.com/product-category/audio",
        "https://alaryanmobile.com/product-category/network/",
        "https://alaryanmobile.com/product-category/accessories/power-banks/",
        "https://alaryanmobile.com/product-category/security-smart-home/smart-cameras/",
    ],
    "ammar": [
        "https://ammarmobile.com/en-gb/category/computer-monitors-gaming-office-led-ips-full-hd-4k-display",
        "https://ammarmobile.com/en-gb/category/printers-ink-toner-home-office-printing-jordan/printers-inkjet-laser-wireless-office-home-jordan",
        "https://ammarmobile.com/en-gb/category/desktop-pcs-custom-gaming-computers-jordan/branded-desktop-pcs-dell-hp-lenovo-jordan",
    ],
    "gts": [
        "https://gts.jo/audio",
        "https://gts.jo/accessories/phone-accessories/handsfree-earphone",
        "https://gts.jo/computers/monitor",
        "https://gts.jo/gaming/gaming-monitor",
        "https://gts.jo/printers-supplies-1",
        "https://gts.jo/accessories/phone-accessories/power-bank",
        "https://gts.jo/components/external-storage",
        "https://gts.jo/cameras",
    ],
    "compujordan": [
        "https://compujordan.com/computer-hardware/audio",
        "https://compujordan.com/gaming-rampage/gaming-accessories/gaming-headsets",
        "https://compujordan.com/monitor-and-display",
        "https://compujordan.com/gaming-rampage/gaming-monitor",
        "https://compujordan.com/printers-and-scanners",
        "https://compujordan.com/pc-and-laptops/all-in-one",
        "https://compujordan.com/pc-and-laptops/desktops",
        "https://compujordan.com/computer-hardware/networking",
        "https://compujordan.com/electronics/power-bank",
        "https://compujordan.com/computer-hardware/storage",
    ],
    "osjo": [
        "https://os-jo.com/accessories/audio",
        "https://os-jo.com/components/computer-monitors",
        "https://os-jo.com/printers-scanners",
        "https://os-jo.com/computer-systems/desktop-computer",
        "https://os-jo.com/gaming-in-jordan/gaming-desktop",
        "https://os-jo.com/network",
        "https://os-jo.com/accessories/power-banks",
        "https://os-jo.com/components/storage",
    ],
    "smartsystems": [
        "https://smartsystems.jo/computer-systems/monitors-and-projectors-computer-systems",
        "https://smartsystems.jo/printers-and-scanners",
        "https://smartsystems.jo/computer-systems/desktops",
        "https://smartsystems.jo/accessories/output-devices/speaker",
        "https://smartsystems.jo/accessories/consumer-electronics/power-bank-and-chargersconsumer-electronics",
        "https://smartsystems.jo/components/storage",
    ],
    "midteks": [
        "https://midteks.com/accessories-1/audio",
        "https://midteks.com/computer-systems/projector-and-monitors",
        "https://midteks.com/computer-systems/desktop",
    ],
    "cse": [
        "https://cse.jo/audio",
        "https://cse.jo/computer-systems/monitors-projectors",
        "https://cse.jo/printers-supplies",
        "https://cse.jo/computer-systems/desktop-computer",
        "https://cse.jo/accessories/mobile-accessories/power-bank",
        "https://cse.jo/components/storage-components",
        "https://cse.jo/camera-and-recorder",
    ],
    "almohanad": [
        "https://almohanadtech.com/product-category/audio-video/",
        "https://almohanadtech.com/product-category/monitors/",
        "https://almohanadtech.com/product-category/desktops/",
        "https://almohanadtech.com/product-category/networking/",
        "https://almohanadtech.com/product-category/cameras-photo/cameras/",
    ],
    "pccircle": [
        "https://pccircle.com/product-category/accessories/headphones-headset/",
        "https://pccircle.com/product-category/accessories/speakers/",
        "https://pccircle.com/product-category/components/lcd-led-monitor/",
        "https://pccircle.com/product-category/printers/",
        "https://pccircle.com/product-category/desktop-pc/",
        "https://pccircle.com/product-category/network-products/wireless/",
        "https://pccircle.com/product-category/components/solid-state-drive-ssd/",
        "https://pccircle.com/product-category/accessories/cameras/",
    ],
    "profpc": [
        "https://www.theprofpc.com/shop/monitor",
        "https://www.theprofpc.com/shop/printer-scanner",
        "https://www.theprofpc.com/shop/desktops",
    ],
    "alruwwad": [
        "https://al-ruwwad.com/categories/audio-systems-accessories/6640546000000138087",
        "https://al-ruwwad.com/categories/speakers/6640546000000191775",
        "https://al-ruwwad.com/categories/monitors/6640546000000143109",
        "https://al-ruwwad.com/categories/cctv-cameras/6640546000000100035",
    ],
    "newvision": [
        "https://newvision.jo/product-category/audio-video-and-home-theater-systems-ar/",
    ],
    "action": [
        "https://action.jo/en/category/camera",
    ],
}


def fetch_offers(slug: str, client: PoliteClient, part: str = "main"):
    _, base, method, _, params = SOURCES[slug]
    if part == "electronics":   # the same reader, pointed at the shop's electronics sections only
        if method == "sitemap_pages":
            return platinum.collect(client, base, part="electronics")
        if slug not in ELECTRONICS:
            return []
        params = {"handles" if method == "shopify_json" else "listings": ELECTRONICS[slug]}
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
    if method in ("odoo_html", "site123_html", "zoho_html"):
        return stores.collect(client, method.split("_")[0], base, params["listings"])
    if method == "opencart_html":
        return opencart.collect(client, params["listings"])
    if method == "darwish_sitemap":
        return darwish.collect(client, base)
    return platinum.collect(client, base)


BLOCK_REST = timedelta(days=3)  # a shop that refused us (bot check, 403, 429) is left alone this long, then tried once


def refused(e: Exception) -> bool:
    """The shop said no to our reader. We never try another way: we stop, rest, and the owner decides."""
    import httpx

    from .collectors.base import ChallengeBlocked
    return isinstance(e, ChallengeBlocked) or (isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (403, 429))


LIMIT_REST = timedelta(hours=2)   # "too many requests, retry in 60 s" (429): a short pause, not a refusal


def rate_limited(e: Exception) -> bool:
    import httpx
    return isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429


def rest_for(run) -> timedelta | None:
    """How long a shop rests after its last run: 3 days after a refusal (bot check, 403), 2 hours after a busy-signal
    (429, the shop's own rate limit, which says to come back in a minute). Older 429 runs were saved as "blocked"."""
    if run is None:
        return None
    if run.status == "limited" or run.status == "blocked" and "429" in (run.error or ""):
        return LIMIT_REST
    return BLOCK_REST if run.status == "blocked" else None


def resting(s, store_id: int, now: datetime) -> bool:
    last = s.query(CollectionRun).filter_by(store_id=store_id).order_by(CollectionRun.started_at.desc()).first()
    rest = rest_for(last)
    if rest is None:
        return False
    at = last.started_at if last.started_at.tzinfo else last.started_at.replace(tzinfo=timezone.utc)
    return now - at < rest


def run_source(slug: str, dry_run: bool, part: str = "main") -> None:
    name, base, method, rating, _ = SOURCES[slug]
    client = PoliteClient()
    if not dry_run:
        engine = get_engine()
        init_db(engine)
        with make_session(engine) as s:
            store = ensure_store(s, slug, name, base, method, rating)
            if resting(s, store.id, datetime.now(timezone.utc)):
                print(f"{slug}: the shop refused our reader recently; resting (tried again after {BLOCK_REST.days} days)")
                return
    try:
        # one listing can sit in two of a shop's sections (SmartBuy "laptops" and "notebooks"): keep it once
        offers = list({o.external_id: o for o in fetch_offers(slug, client, part)}.values())
    except Exception as e:  # a crash must show up in the run log, or reliability numbers lie
        blocked = refused(e)
        if not dry_run:
            engine = get_engine()
            init_db(engine)
            with make_session(engine) as s:
                store = ensure_store(s, slug, name, base, method, rating)
                src = s.query(Source).filter_by(store_id=store.id).one()
                src.consecutive_failures = (src.consecutive_failures or 0) + 1
                status = ("limited" if rate_limited(e) else "blocked") if blocked else "failed"
                s.add(CollectionRun(store_id=store.id, requests=client.request_count, status=status,
                                    finished_at=datetime.now(timezone.utc), error=f"{type(e).__name__}: {e}"[:500]))
                s.commit()
        if blocked:  # not a fault of ours: recorded and shown on the dashboard, the job itself carries on green
            if rate_limited(e):
                print(f"{slug}: the shop asked us to slow down (429); stopped politely, trying again in {LIMIT_REST} ")
            else:
                print(f"{slug}: the shop refused our reader ({type(e).__name__}); stopped politely, resting {BLOCK_REST.days} days")
            return
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
            from . import api_static  # the app's data as files on derbani.com (served instantly, never sleeps)
            print("app files:", api_static.build(root / "web_build"))
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
    c.add_argument("--part", choices=["main", "electronics"], default="main")
    cr = sub.add_parser("clicks-report", help="private Go-to-shop click report (private project only)")
    cr.add_argument("--csv", help="also save the raw counts to this file")
    g = sub.add_parser("auto-grow")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--block", nargs=2, metavar=("BRAND", "FAMILY"), help="remove a wrong model for good")
    for name in ("propose-catalog", "grow-catalog", "seed-catalog", "match", "report", "audit-sample", "build-site", "build-web", "indexnow-prepare", "indexnow-send", "push-health"):
        sub.add_parser(name)
    a = ap.parse_args()
    if a.command == "collect":
        run_source(a.source, a.dry_run, a.part)
    elif a.command == "clicks-report":
        from . import clicks
        clicks.main(a.csv)
    elif a.command == "auto-grow":
        run_grow(a.dry_run, a.block)
    else:
        run_matching(a.command)


if __name__ == "__main__":
    main()
