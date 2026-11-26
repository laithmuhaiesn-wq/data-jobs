"""Specifications read from a shop's own product page or product list (owner 2026-11-26: "both, one shop enough").

Only facts are kept: a field name we know and a short value (numbers and names, e.g. "Intel Core i7-13620H",
"15.6 inch", "5000 mAh"). The shop's own text is never kept. One shop is enough; when shops state different
values for the same field, nothing is shown for it (see `agree`). The maker's page (specs.json) always wins.
"""
from __future__ import annotations

import re
from collections import Counter

from bs4 import BeautifulSoup

from . import spec_titles as st

# field -> label pattern (whole label, English or Arabic). A label is the text before ":" or the first table cell.
LABELS = {
    "processor": r"processor|cpu|processor (?:type|model|name)|المعالج",
    "chip": r"chip|chipset|processor|cpu|المعالج",
    "graphics": r"graphics?(?: card| processor)?|gpu|video card|vga|كرت الشاشة|بطاقة الرسومات",
    "display": r"display|screen|display size|screen size|display type|الشاشة|حجم الشاشة",
    "resolution": r"(?:display |screen |native |max(?:imum)? )?resolution|الدقة",
    "refresh": r"refresh rate|(?:max(?:imum)? )?refresh|معدل التحديث",
    "panel": r"panel(?: type)?|display technology",
    "response": r"response time|زمن الاستجابة",
    "battery": r"battery(?: capacity| life| type)?|البطارية",
    "rear_camera": r"(?:rear|main|back|primary) cameras?|الكاميرا الخلفية",
    "front_camera": r"(?:front|selfie) cameras?|الكاميرا الأمامية",
    "charging": r"(?:fast |wired )?charging(?: speed| power)?|الشحن",
    "weight": r"weight|الوزن",
    "os": r"operating system|os|platform|نظام التشغيل",
    "water": r"water(?:proof| resistance| resistant)|ip rating|مقاومة الماء",
    "connection": r"connectivity|connection(?: type)?|bluetooth(?: version)?|interface|الاتصال",
    "power": r"(?:total |rated |output )?power(?: output)?|القوة",
    "output": r"(?:max(?:imum)? )?output(?: power)?|قوة الشحن",
    "wifi": r"wi-?fi(?: standard)?|wireless standard|wireless",
    "speed": r"(?:read |print(?:ing)? |transfer |wi-?fi )?speed",
    "brightness": r"brightness|السطوع",
    "dpi": r"dpi|sensitivity|resolution \(dpi\)",
    "video": r"video(?: resolution| recording)?",
}
_LABEL_RE = {f: re.compile(rf"^(?:{p})$", re.I) for f, p in LABELS.items()}

# value readers: a value is kept only in the shape these give (never the shop's free text)
READ = {
    "processor": st._processor, "chip": st._chip, "graphics": st._graphics, "display": st._screen,
    "resolution": st._resolution, "refresh": st._refresh, "panel": st._panel, "response": st._response,
    "battery": st._battery, "water": st._water, "wifi": st._wifi, "brightness": st._lumens, "dpi": st._dpi,
}


def _mp(v: str) -> str | None:
    nums = re.findall(r"(\d{1,3}(?:\.\d)?)\s*mp\b", v.lower())
    return " + ".join(f"{st._num(n)}MP" for n in nums[:4]) or None


def _watts(v: str) -> str | None:
    m = re.search(r"(\d{1,4}(?:\.\d)?)\s*w\b", v.lower())
    return f"{st._num(m[1])} W" if m else None


def _weight(v: str) -> str | None:
    m = re.search(r"(\d{1,4}(?:[.,]\d{1,3})?)\s*(kg|g|grams?|كغ|غرام)\b", v.lower())
    if not m:
        return None
    n = m[1].replace(",", ".")
    return f"{st._num(n)} kg" if m[2] in ("kg", "كغ") else f"{st._num(n)} g"


def _os(v: str) -> str | None:
    w = st._os(" " + v.lower() + " ")
    if w:
        return w
    m = re.search(r"\b(android\s*\d{1,2}|ios\s*\d{1,2}|ipados\s*\d{1,2}|macos(?:\s+\w+)?|harmonyos\s*[\d.]*|chrome\s*os)\b", v.lower())
    if not m:
        return None
    t = m[1]
    for a, b in (("android", "Android"), ("ipados", "iPadOS"), ("ios", "iOS"), ("macos", "macOS"), ("harmonyos", "HarmonyOS"), ("chrome os", "ChromeOS"), ("chromeos", "ChromeOS")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().replace("Android", "Android ").replace("  ", " ").strip()


READ |= {"rear_camera": _mp, "front_camera": _mp, "charging": _watts, "power": _watts, "output": _watts, "weight": _weight,
         "os": _os, "connection": st._bluetooth, "video": lambda v: "8K" if re.search(r"\b8k\b", v.lower()) else "4K" if re.search(r"\b4k\b", v.lower()) else None}
READ["speed"] = lambda v: st._readspeed(v) or st._mbps(v) or st._ppm(v)


def value_for(field: str, raw: str) -> str | None:
    raw = re.sub(r"\s+", " ", raw or "").strip(" :-–|")
    if not raw or "http" in raw.lower() or "@" in raw:
        return None
    if field in READ:
        return READ[field](" " + raw.lower().replace("×", "x") + " ")
    return None


def _label_fields(label: str) -> list[str]:
    label = re.sub(r"\s+", " ", label).strip(" :-–|•*").lower()
    if not label or len(label) > 40:
        return []
    parts = [x.strip(" :-–|•*") for x in re.split(r"\s+/\s+|\s+\|\s+", label)]   # "Processor / المعالج"
    return [f for f, rx in _LABEL_RE.items() if any(rx.match(x) for x in parts)]


def from_pairs(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """(label, value) pairs -> {field: value}; the first readable value of each field wins."""
    out: dict[str, str] = {}
    for label, raw in pairs:
        for f in _label_fields(label):
            if f not in out and (v := value_for(f, raw)):
                out[f] = v
    return out


_SKIP = re.compile(r"related|upsell|up-sells|cross-?sell|recent|you-may|also-like|menu|nav|footer|header|breadcrumb|"
                   r"product-grid|products-carousel|product-layout|mega|cart|wishlist|newsletter|review|comment", re.I)
_SPLIT = re.compile(r"^\s*([^:：\n]{2,40}?)\s*[:：]\s*(.{1,120})$")


def pairs_from_html(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav", "form", "svg", "iframe"]):
        t.decompose()
    for t in soup.find_all(True):
        if t.attrs is None:   # inside a part already removed
            continue
        names = " ".join([t.get("id") or ""] + list(t.get("class") or []))
        if names.strip() and _SKIP.search(names) and t.name not in ("html", "body"):
            t.decompose()
    pairs: list[tuple[str, str]] = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            pairs.append((cells[0].get_text(" ", strip=True), cells[1].get_text(" ", strip=True)))
    for dt in soup.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if dd:
            pairs.append((dt.get_text(" ", strip=True), dd.get_text(" ", strip=True)))
    lines = [x.strip() for x in soup.get_text("\n").splitlines() if x.strip()]
    for i, line in enumerate(lines):
        m = _SPLIT.match(line)
        if m:
            pairs.append((m[1], m[2]))
        elif i + 1 < len(lines) and _label_fields(line):   # "Processor" on one line, its value on the next
            pairs.append((line, lines[i + 1]))
    return pairs


def from_html(html: str) -> dict[str, str]:
    return from_pairs(pairs_from_html(html))


def _key(v: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", v.lower())


def agree(per_shop: dict[object, dict[str, str]]) -> dict[str, str]:
    """{shop: {field: value}} -> {field: value}. One shop is enough; when shops differ, the value most shops state
    wins only if no other value is stated as often; a tie shows nothing."""
    by_field: dict[str, Counter] = {}
    shown: dict[tuple[str, str], str] = {}
    for facts in per_shop.values():
        for f, v in facts.items():
            k = _key(v)
            by_field.setdefault(f, Counter())[k] += 1
            shown.setdefault((f, k), v)
    out = {}
    for f, counts in by_field.items():
        top = counts.most_common(2)
        if len(top) == 1 or top[0][1] > top[1][1]:
            out[f] = shown[(f, top[0][0])]
    return out


# ---- nightly: product pages of shops whose list has no description (owner 2026-11-26) ----
PAGE_READS = 400              # product pages read per night at most (one request each, the shop's pace and robots.txt kept)
READ_AGAIN = 30               # days before a page is read again


def read_pages(limit: int = PAGE_READS) -> None:
    """Read the product pages of matched listings at shops with green terms whose specs are missing or a month old.
    Shopify shops are not read here: their list already carries the description (no extra request). A shop that
    answers with a bot check, a "no" in robots.txt, 429 or an error is left alone for the rest of the night."""
    import json
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from .cli import SIGNED, resting
    from .collectors.base import PoliteClient
    from .db.models import Offer, ShopSpec, Source, Store
    from .db.session import get_engine, init_db, make_session
    from .store import save_specs

    now = datetime.now(timezone.utc)
    engine = get_engine()
    init_db(engine)
    with make_session(engine) as s:
        ok = {so.store_id for so in s.scalars(select(Source).where(Source.enabled, Source.terms_rating == "green"))
              if not so.method.startswith("shopify")}
        slugs = {st.id: st.slug for st in s.scalars(select(Store))}
        known = {r.offer_id: r for r in s.scalars(select(ShopSpec))}
        offers = [o for o in s.scalars(select(Offer).where(Offer.match_status == "matched", Offer.store_id.in_(ok)))
                  if o.id not in known or known[o.id].read_on < now - timedelta(days=READ_AGAIN)]
        # never read first; then oldest; shops taken in turn so no shop gets all the night's reads
        offers.sort(key=lambda o: (o.id in known, known[o.id].read_on if o.id in known else now))
        queues: dict[int, list] = {}
        for o in offers:
            queues.setdefault(o.store_id, []).append(o)
        order = []
        while any(queues.values()) and len(order) < limit:
            for q in queues.values():
                if q and len(order) < limit:
                    order.append(q.pop(0))
        clients: dict[int, PoliteClient] = {}
        skip, read, found = set(), 0, 0
        for o in order:
            if o.store_id in skip:
                continue
            if o.store_id not in clients:
                if resting(s, o.store_id, now, slugs[o.store_id]):
                    skip.add(o.store_id)
                    continue
                clients[o.store_id] = PoliteClient(min_interval=3.0, max_retries=1, sign=slugs[o.store_id] in SIGNED)
            try:
                html = clients[o.store_id].get(o.url).text
            except Exception:   # robots.txt says no, a bot check, 429, gone: never worked around
                skip.add(o.store_id)
                continue
            read += 1
            specs = from_html(html)
            found += bool(specs)
            if o.id in known:
                known[o.id].read_on = now   # read again in a month even when nothing changed
            save_specs(s, known, o.id, specs, now)
            if read % 50 == 0:
                s.commit()
        s.commit()
    print(f"shop specs: {len(offers)} listings due; pages read {read}, with specs {found}; shops left for tonight: "
          f"{', '.join(sorted(slugs[i] for i in skip)) or 'none'}")


def by_offer(s) -> dict[int, dict]:
    """{offer id: {field: value}} for every listing with shop specifications."""
    import json

    from sqlalchemy import select

    from .db.models import ShopSpec
    try:
        rows = s.execute(select(ShopSpec.offer_id, ShopSpec.specs)).all()
    except Exception:   # the table is made by the first run that saves specs
        s.rollback()
        return {}
    return {oid: d for oid, txt in rows if (d := json.loads(txt or "{}"))}
