"""Missing and broken product pictures, found and fixed every night.

The price readers never fetch shops' pictures (only cutouts.py does, once per picture, owner 2026-11-28). Instead the site and the app report a picture that did
not load for a visitor (worker /img-fail, D1 table img_fail: address and count only). Every night `fix-images`:
  1. reads those reports; a picture of ours that failed at least twice is no longer shown (kept for 14 days, then tried
     again in case the shop fixed it);
  2. for products left with no working picture, reads the shop's product page (a normal, polite page read that obeys
     robots.txt, like the price readers) and takes its og:image as the new picture;
  3. writes a short report to ~/Derbani image reports.
The decisions live in ~/.derbani/image-fixes.json, read by views.py when the site and the API are built.
"""
from __future__ import annotations

import json
import re
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

FILE = Path.home() / ".derbani" / "image-fixes.json"
REPORTS = Path.home() / "Derbani image reports"
MIN_FAILS = 2          # loads that failed before a picture is dropped (one bad network moment is not enough)
KEEP_DAYS = 14         # a dropped picture is tried again after this
PAGE_READS = 40        # shop pages read per night at most


def load(path: Path | None = None) -> dict:
    try:
        d = json.loads((path or FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"broken": dict(d.get("broken") or {}), "replace": {str(k): v for k, v in (d.get("replace") or {}).items()}}


def save(d: dict, path: Path | None = None) -> None:
    p = path or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def picture_for(oid: int, url: str | None, fixes: dict) -> str | None:
    """The picture to show for one offer: a new one found on the shop's page wins; a dropped one is not shown."""
    url = fixes["replace"].get(str(oid)) or url
    return None if not url or url in fixes["broken"] else url


def expire(fixes: dict, today: date) -> None:
    old = (today - timedelta(days=KEEP_DAYS)).isoformat()
    fixes["broken"] = {u: d for u, d in fixes["broken"].items() if d >= old}


def add_reports(fixes: dict, rows: list[dict], known: set[str], today: date, loads=None) -> list[str]:
    """Reported addresses that are ours and failed often enough are dropped; returns the newly dropped ones.
    `loads(url) -> bool`: a picture that loads for us now is kept (2026-11-28: one bad hour at GTS's picture server
    dropped 19 good GTS pictures, and one product got the shop's logo instead)."""
    new = []
    for r in rows:
        u = r.get("url") or ""
        if int(r.get("n") or 0) >= MIN_FAILS and u in known and u not in fixes["broken"] and not (loads and loads(u)):
            fixes["broken"][u] = today.isoformat()
            new.append(u)
    return new


NOT_PRODUCT = re.compile(r"logo|icon|favicon|placeholder|no[-_]?image|default", re.I)  # a shop's sign, not the product


def page_picture(html: str) -> str | None:
    """The product's picture on a shop page: the product data's (schema.org) image first, then og:image / twitter:image.
    Shops' logos and "no picture" placeholders are never taken (2026-11-28: GTS's og:image is its logo)."""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "html.parser")
    found = []
    for tag in s.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        for d in data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []:
            if isinstance(d, dict) and "Product" in str(d.get("@type")):
                img = d.get("image")
                img = img[0] if isinstance(img, list) and img else img
                img = img.get("url") if isinstance(img, dict) else img
                if isinstance(img, str):
                    found.append(img)
    for sel in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        m = s.select_one(sel)
        if m:
            found.append(m.get("content") or "")
    for u in (x.strip() for x in found):
        if u.startswith(("http://", "https://")) and len(u) <= 500 and not NOT_PRODUCT.search(u.rsplit("/", 1)[-1]):
            return u
    return None


og_image = page_picture  # old name


def _d1(sql: str, params: list | None = None) -> list[dict]:
    from .clicks import DATABASE_ID
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        raise SystemExit("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are needed")
    r = httpx.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{DATABASE_ID}/query",
                   headers={"Authorization": f"Bearer {token}"}, json={"sql": sql, "params": params or []}, timeout=60)
    if "no such table" in r.text:  # nothing reported yet
        return []
    r.raise_for_status()
    return r.json()["result"][0]["results"]


def clean(fixes: dict, loads=None, no_copy: tuple = ()) -> None:
    """Takes back wrong decisions: replacement pictures that are a shop's logo or placeholder, or from a shop whose
    pictures may not be used, and dropped pictures that load again (each night, so a bad hour is undone)."""
    fixes["replace"] = {k: u for k, u in fixes["replace"].items()
                        if not NOT_PRODUCT.search(u.rsplit("/", 1)[-1]) and not any(n in u for n in no_copy)}
    if loads:
        fixes["broken"] = {u: d for u, d in fixes["broken"].items() if not loads(u)}


def _loads(url: str) -> bool:
    """Does the picture load for us now, the way a visitor's browser asks for it from our pages?"""
    from .collectors.base import USER_AGENT
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT, "Referer": "https://kamkam.derbani.com/"}, timeout=20,
                      follow_redirects=True)
        return r.status_code == 200 and r.headers.get("content-type", "").startswith("image/")
    except httpx.HTTPError:
        return False


def main() -> None:
    from sqlalchemy import select
    from .cli import resting
    from .collectors.base import PoliteClient
    from .db.models import Offer, PhoneVariant, PhoneModel, Store
    from .db.session import get_engine, make_session
    from .blocklist import is_blocked
    from .cutouts import NO_COPY   # shops whose pictures may not be used

    today = date.today()
    now = datetime.now(timezone.utc)
    fixes = load()
    expire(fixes, today)
    clean(fixes, _loads, NO_COPY)
    with make_session(get_engine()) as s:
        offers = list(s.scalars(select(Offer).where(Offer.match_status == "matched")))
        images = dict(s.execute(select(Offer.id, Offer.image_url).where(Offer.match_status == "matched")).all())
        known = {u for u in images.values() if u} | set(fixes["replace"].values())
        rows = _d1("SELECT url, n FROM img_fail")
        dropped = add_reports(fixes, rows, known, today, loads=_loads)
        if rows:  # counted reports are cleared; a picture that keeps failing is reported again
            _d1("DELETE FROM img_fail WHERE day <= ?", [today.isoformat()])
        # products (variants) left with no working picture at any shop
        by_variant: dict[int, list] = {}
        for o in offers:
            by_variant.setdefault(o.variant_id, []).append(o)
        bare = []
        for vid, os_ in by_variant.items():
            if any((p := picture_for(o.id, images.get(o.id), fixes)) and not is_blocked(p) for o in os_):
                continue
            bare.append((vid, sorted(os_, key=lambda o: (not o.in_stock, float(o.price_jod)))))
        stores = {st.id: st for st in s.scalars(select(Store))}
        client = PoliteClient(min_interval=3.0)
        found, tried, skip_store = [], 0, set()
        for vid, os_ in bare:
            for o in os_:
                if tried >= PAGE_READS:
                    break
                if o.store_id in skip_store or resting(s, o.store_id, now) or any(n in o.url for n in NO_COPY):
                    continue
                tried += 1
                try:
                    pic = page_picture(client.get(o.url).text)
                except Exception:  # robots.txt says no, a bot check, 429, gone: never worked around
                    skip_store.add(o.store_id)
                    continue
                if pic and pic not in fixes["broken"] and not is_blocked(pic):
                    fixes["replace"][str(o.id)] = pic
                    found.append((vid, stores[o.store_id].name, pic))
                    break
        save(fixes)
        still = [vid for vid, _ in bare if vid not in {f[0] for f in found}]
        names = {}
        if still:
            q = (select(PhoneVariant.id, PhoneModel.family, PhoneVariant.storage_gb)
                 .join(PhoneModel, PhoneModel.id == PhoneVariant.model_id).where(PhoneVariant.id.in_(still)))
            names = {vid: f"{n} {gb or ''}".strip() for vid, n, gb in s.execute(q)}
    lines = [f"Pictures {today}", f"reported not loading (dropped now): {len(dropped)}",
             f"dropped and waiting to be tried again: {len(fixes['broken'])}",
             f"products with no picture: {len(bare)}; shop pages read: {tried}; new pictures found: {len(found)}",
             f"still with no picture: {len(still)}", ""]
    lines += [f"  fixed {vid} from {shop}" for vid, shop, _ in found]
    lines += [f"  none: {vid} {names.get(vid, '')}" for vid in still[:200]]
    text = "\n".join(lines)
    print("\n".join(lines[:6]))
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"images-{today}.txt").write_text(text, encoding="utf-8")
