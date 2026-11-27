"""Specifications read automatically from the maker's own product pages (owner 2026-11-27: "maker-page readers").

For the makers whose pages can be read politely (robots.txt allows it, no bot check, the facts are in the page itself):
  1. their sitemap gives every product page address (once a month);
  2. our product's model code is matched to ONE page address (exact code, never a near one: no page = nothing);
  3. the page's specification table is read into our fields (numbers and names only, in our own wording, the same
     readers as shop_specs.py; nothing else is kept);
  4. saved in the database (maker_spec), read again after 90 days.
These count as the maker's page (no * mark). A hand-checked entry in specs.json always wins over them.
Makers left alone on 2026-11-27: MSI and Xiaomi (robots.txt says no), JBL (403), Dahua (its sitemap lists few models).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from . import spec_titles as st
from .shop_specs import LABELS, READ, pairs_from_html

# Brand (our name) -> where its pages are listed and how its page addresses name a model.
MAKERS = {
    "TP-Link": {
        "sitemaps": ["https://www.tp-link.com/us/sitemap.xml"],   # holds the /ae/ (Middle East) pages
        "keep": r"^https://www\.tp-link\.com/ae/(?:home-networking|business-networking|home-camera|smart-home|networking|vigi)/[^?#]+/$",
        "prefixes": ("archer", "deco", "tapo", "vigi", "omada", "tl"),
    },
}
READ_AGAIN = timedelta(days=90)
PAGES_PER_NIGHT = 300
KIND_WORDS = {"router", "camera", "monitor", "tv", "watch", "speaker", "audio", "peripheral", "console", "storage", "printer",
              "powerbank", "projector", "laptop", "desktop", "tablet", "smarthome"}

# fields maker pages name differently from shops (added to the shop labels; values go through the same readers)
EXTRA_LABELS = {
    "wifi": r"standards?(?: and protocols)?|wi-?fi standards?|wireless standards?",
    "speed": r"wi-?fi speeds?|wireless speeds?|max(?:imum)? speed",
    "ports": r"ports?|interfaces?|ethernet ports?|video (?:interface|input)s?|i/o ports?|connectors?",
    "sensor": r"image sensor|sensor(?: type)?",
    "lens": r"lens(?: type)?|focal length",
    "video": r"max\.? resolution|video resolution|resolution",
}


def _ports(v: str) -> str | None:
    out = []
    for name, rx in (("HDMI", r"hdmi"), ("DisplayPort", r"displayport|\bdp\b"), ("USB-C", r"usb[ -]?c|type[ -]?c"), ("VGA", r"\bvga\b"),
                     ("DVI", r"\bdvi\b"), ("WAN", r"\bwan\b"), ("LAN", r"\blan\b"), ("USB", r"\busb(?![ -]?c)")):
        m = re.search(rf"(\d)\s*[×x*]?\s*(?:[\w./-]+\s+){{0,2}}?(?:{rx})|(?:{rx})", v)
        if m:
            n = re.match(r"(\d)", m[0])
            out.append(f"{n[1]}× {name}" if n else name)
    return ", ".join(out) or None


def _sensor(v: str) -> str | None:
    m = re.search(r"(1/\d(?:\.\d{1,2})?)\s*[\"”″]?[^,;]{0,40}?\b(cmos|ccd)\b", v)
    return f'{m[1]}" {m[2].upper()}' if m else None


def _lens(v: str) -> str | None:
    mm = re.findall(r"(\d{1,2}(?:\.\d{1,2})?)\s*mm", v)
    return " / ".join(f"{st._num(x)} mm" for x in mm[:3]) or None


def _video(v: str) -> str | None:
    m = re.search(r"(\d{3,4})\s*(?:\(h\))?\s*[x×*]\s*(\d{3,4})", v)
    if m:
        w, h = int(m[1]), int(m[2])
        return f"{w} × {h} ({max(1, round(w * h / 1e6))}MP)"
    return "8K" if re.search(r"\b8k\b", v) else "4K" if re.search(r"\b4k\b", v) else None


def _speed(v: str) -> str | None:
    return st._wifi(v) if re.search(r"\b(?:be|ax|ac)\s*\d{4,5}\b", v) else st._mbps(v)


MAKER_READ = {"ports": _ports, "sensor": _sensor, "lens": _lens, "video": _video, "speed": _speed}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def code_of(family: str) -> str:
    """The model code in our family name: "router deco be85 2pack" -> "decobe85" (pack sizes are not models)."""
    words = family.lower().split()
    if words and words[0] in KIND_WORDS:
        words = words[1:]
    words = [w for w in words if not re.fullmatch(r"\d+pack|\d+-pack|pack|kit", w)]
    return _norm(" ".join(words))


def _strip(code: str, prefixes: tuple) -> str:
    for p in sorted(prefixes, key=len, reverse=True):
        if code.startswith(p) and len(code) - len(p) >= 3:
            return code[len(p):]
    return code


def _region(url: str) -> tuple:
    """The Middle East page first, then the international English one, then any."""
    return (not re.search(r"\.com/(?:ae|mena|me)/", url), not re.search(r"\.com/(?:en|global)/|\.com/products/", url), url)


def match(family: str, pages: dict[str, list[str]], prefixes: tuple) -> str | None:
    """The one page address whose last part is this model's code (with or without the maker's series prefix).
    Several different models matching = nothing (never a guess)."""
    code = code_of(family)
    if len(code) < 3 or not re.search(r"\d", code) or not re.search(r"[a-z]", code):   # a code has letters and digits ("c54", "lm27e331y")
        return None
    for want in (code, _strip(code, prefixes)):
        hits = {slug for slug in pages if slug == want or _strip(slug, prefixes) == want}
        if len(hits) == 1:
            return sorted(pages[hits.pop()], key=_region)[0]
        if len(hits) > 1:
            return None
    return None


def page_index(urls: list[str], keep: str) -> dict[str, list[str]]:
    """{normalized last part of the address: [addresses]} for the product pages."""
    rx = re.compile(keep)
    out: dict[str, list[str]] = {}
    for u in urls:
        if rx.match(u):
            out.setdefault(_norm(u.rstrip("/").rsplit("/", 1)[-1]), []).append(u)
    return out


def read_html(html: str, category: str) -> dict[str, str]:
    """The fields of this kind found in a maker page (a field the page does not state is left out)."""
    from .specs import FIELDS
    wanted = {k for k, _, _ in FIELDS.get(category, [])}
    labels = {f: re.compile("^(?:" + "|".join(p for p in (LABELS.get(f), EXTRA_LABELS.get(f)) if p) + ")$", re.I)
              for f in wanted if f in LABELS or f in EXTRA_LABELS}
    out: dict[str, str] = {}
    for label, raw in pairs_from_html(html):
        lab = re.sub(r"\s+", " ", label).strip(" :-–|•*").lower()
        if not lab or len(lab) > 40:
            continue
        raw = re.sub(r"\s+", " ", raw or "").strip()
        if not raw or "http" in raw.lower():
            continue
        for f, rx in labels.items():
            if f in out or not rx.match(lab):
                continue
            reader = MAKER_READ.get(f) or READ.get(f)
            v = reader(" " + raw.lower().replace("×", "x") + " ") if reader else None
            if v:
                out[f] = v
    if category == "camera":
        out.pop("resolution", None)
    return out


def _sitemap(client, url: str) -> list[str]:
    text = client.get(url).text
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
    if "<sitemapindex" in text:
        return [u for sm in locs[:40] for u in _sitemap(client, sm)]
    return locs


def run(limit: int = PAGES_PER_NIGHT) -> None:
    """Nightly: match products of the makers above to their pages, read due pages, save."""
    from pathlib import Path

    from sqlalchemy import select

    from .collectors.base import PoliteClient
    from .db.models import Brand, MakerSpec, Offer, PhoneModel, PhoneVariant
    from .db.session import get_engine, init_db, make_session
    from .matching.parse import category_of
    from .specs import FIELDS, key, load

    now = datetime.now(timezone.utc)
    cache = Path.home() / ".derbani" / "maker_pages.json"   # the sitemaps, read again monthly
    pages = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    engine = get_engine()
    init_db(engine)
    hand = load()
    read = found = 0
    left: list[str] = []
    with make_session(engine) as s:
        brands = {b.id: b.name_en for b in s.scalars(select(Brand)) if b.name_en in MAKERS}
        on_sale = {v.model_id for v in s.scalars(select(PhoneVariant).where(PhoneVariant.id.in_(
            select(Offer.variant_id).where(Offer.match_status == "matched", Offer.in_stock))))}
        known = {r.key: r for r in s.scalars(select(MakerSpec))}
        due = []
        for m in s.scalars(select(PhoneModel).where(PhoneModel.brand_id.in_(brands))):
            k, cat = key(brands[m.brand_id], m.family), category_of(m.family)
            if m.id in on_sale and k not in hand and cat in FIELDS and (k not in known or known[k].read_on < now - READ_AGAIN):
                due.append((k in known, brands[m.brand_id], m.family, cat, k))
        due.sort()
        for brand, cfg in MAKERS.items():
            mine = [d for d in due if d[1] == brand][:limit]
            if not mine:
                continue
            client = PoliteClient(min_interval=3.0, max_retries=1)
            try:
                got = pages.get(brand)
                if not got or now.timestamp() - got["at"] > 30 * 86400:
                    urls = [u for sm in cfg["sitemaps"] for u in _sitemap(client, sm)]
                    got = pages[brand] = {"at": now.timestamp(), "pages": page_index(urls, cfg["keep"])}
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(pages), encoding="utf-8")
                for _, _, family, cat, k in mine:
                    url = match(family, got["pages"], cfg["prefixes"])
                    row = known.get(k) or MakerSpec(key=k)
                    row.read_on, row.url = now, url
                    if url:
                        html = client.get(url).text
                        read += 1
                        facts = read_html(html, cat)
                        found += bool(facts)
                        row.specs = json.dumps(facts, ensure_ascii=False)
                    else:
                        row.specs = "{}"
                    if k not in known:
                        s.add(row)
                        known[k] = row
                    if read and read % 50 == 0:
                        s.commit()
            except Exception as e:   # robots.txt no, a bot check, 403/429: this maker is left alone tonight
                left.append(f"{brand} ({type(e).__name__})")
            s.commit()
    print(f"maker specs: {len(due)} models due; pages read {read}, with specs {found}; left tonight: {', '.join(left) or 'none'}")


def entries(s) -> dict[str, dict]:
    """{"Brand|family": {"source", "checked", field: value}} for every model with specs read from its maker's page."""
    from sqlalchemy import select

    from .db.models import MakerSpec
    try:
        rows = s.scalars(select(MakerSpec)).all()
    except Exception:   # the table is made by the first nightly run
        s.rollback()
        return {}
    out = {}
    for r in rows:
        facts = json.loads(r.specs or "{}")
        if r.url and facts:
            out[r.key] = {"source": r.url, "checked": r.read_on.date().isoformat(), **facts}
    return out
