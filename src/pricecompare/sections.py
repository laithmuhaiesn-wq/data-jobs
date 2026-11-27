"""Shop sections we do not read: the check that keeps a shop's category from being missed (owner 2026-11-27:
"I don't want this case to happen ever again", after iGeek's and other shops' RAM sections were not read).

For each shop read by sections (not Shopify's full list or a full sitemap), the home page's menu links are sorted
into our live kinds by their words; a section of a kind we show that none of our listing pages covers is reported.
One request per shop. Run weekly by the nightly job; the doctor reads the report and adds the real ones.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

# What a section's link text or address says it holds. Checked in this order; the first kind that matches wins.
KIND_WORDS: list[tuple[str, str]] = [
    ("ram", r"\bram\b|\brams\b|memory-ram|desktop-memory|laptop-memory|system-memory|\bmemory\b(?!.*card)|رامات|ذاكرة عشوائية"),
    ("pcpart", r"graphics?[- ]?cards?|\bgpu|\bvga\b|processors?\b|\bcpus?\b|كروت شاشة|معالجات"),
    ("console", r"playstation|\bps5\b|\bxbox\b|nintendo|consoles?\b|بلايستيشن|اكس بوكس"),
    ("watch", r"smart[- ]?watch|apple[- ]?watch|\bwatch(es)?\b|ساعات"),
    ("tablet", r"tablets?\b|\bipad|تابلت|ايباد"),
    ("laptop", r"laptops?\b|notebooks?\b|macbook|لابتوب"),
    ("desktop", r"desktops?\b|all[- ]?in[- ]?one|\baio\b|\bimac|mac[- ]?mini|كمبيوتر مكتبي"),
    ("monitor", r"monitors?\b|شاشات كمبيوتر|شاشات الكمبيوتر"),
    ("tv", r"\btvs?\b|televisions?|smart[- ]screens?|tv[- ]screens?|شاشات تلفاز|تلفزيون|تلفزيونات"),
    ("audio", r"head ?phones?|ear ?buds?|ear ?phones?|head ?sets?|airpods|سماعات"),
    ("speaker", r"speakers?\b|sound ?bars?|سبيكر"),
    ("printer", r"printers?\b|طابعات"),
    ("projector", r"projectors?\b|بروجكتر"),
    ("router", r"routers?\b|\bnetwork|wi-?fi|\bmesh\b|access[- ]points?|راوتر"),
    ("powerbank", r"power[- ]?banks?|باور بانك"),
    ("storage", r"\bssd|hard[- ]?(disk|drive)s?|\bhdd|external[- ]storage|internal[- ]storage|\bstorage\b|flash|memory[- ]cards?|تخزين"),
    ("smarthome", r"smart[- ]home|vacuum|security[- ]cameras?|منزل ذكي"),
    ("camera", r"cameras?\b|gopro|instax|كاميرات"),
    ("peripheral", r"keyboards?\b|\bmouse\b|\bmice\b|كيبورد|ماوس"),
    ("phone", r"smart ?phones?|mobiles?(?![- ]?(acc|cover|case|charg))\b|\bphones?\b|هواتف|موبايل|جوالات"),
]
# Words that make a section accessories, parts or something we do not show, whatever kind word it also has.
NOT_OURS = re.compile(
    r"accessor|\bcases?\b|cover|cable|charger|adapter|\bink\b|toner|cartridge|\bbags?\b|stand|mount|strap|band|"
    r"protector|screen[- ]guard|glass|repair|spare|\bparts?\b|used|refurb|server|\bcooler|cooling|\bfans?\b|"
    r"\bcase\b|chassis|power[- ]suppl|\bpsu\b|motherboard|mouse[- ]?pad|controller|games?\b|cards? reader|"
    r"batter(y|ies)|skins?\b|arms?\b|remote|splitter|(vga|data|printer|kvm|hdmi)[- ]switch|receipt|label|thermal|clean|gimbal|holder|\bpens?\b|pencil|essentials|food|kitchen|\bups\b|cabinet|software|point of sale|paper|"
    r"إكسسوار|اكسسوار|كفرات|شواحن|كوابل|حبر", re.I)
SKIP_LINK = re.compile(r"/products?/|\.(jpg|jpeg|png|webp|css|js|pdf)$|/cart|/account|/login|/checkout|/wishlist|"
                       r"/compare|/blog|/contact|/about|/brand|/manufacturer|route=product/(product|search)|/information/|[?&](sort|filter|page|search)=", re.I)
# Card badges and buttons, not section names ("−14%", "New", "Buy Now →").
NOT_A_NAME = re.compile(r"^[−-]?\d+%$|^(new|best ?seller|hot|sale|buy now|shop now|view all|more|see all)\b", re.I)


def kind_of(text: str) -> str | None:
    t = text.lower().replace("_", " ")
    if NOT_OURS.search(t):
        return None
    for kind, rx in KIND_WORDS:
        if re.search(rx, t, re.I):
            return kind
    return None


def _norm(url: str) -> str:
    p = urlparse(url)
    return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/").lower())


def _lang(url: str) -> str:
    """The language part of an address: "/en/", "/en-gb/", "/ar/", or "%" for Arabic words in the address."""
    path = urlparse(url).path.lower()
    m = re.match(r"/(en|ar|en-gb|ar-jo)(/|$)", path)
    return m.group(1) if m else ("%" if "%d8" in path or "%d9" in path else "")


def covered(url: str, ours: list[str]) -> bool:
    """A section is read if one of our listing pages is it, sits under it, or holds it."""
    u = _norm(url)
    for o in ours:
        n = _norm(o)
        # OpenCart answers one section at its short and long address (/headset and /audio/headset)
        if u == n or n.startswith(u + "/") or u.startswith(n + "/") or u.rsplit("/", 1)[-1] == n.rsplit("/", 1)[-1]:
            return True
    return False


def sections_on(html: str | bytes, base: str) -> dict[str, str]:
    """The menu's section links of a shop page: {absolute url: link text}, same site only."""
    s = BeautifulSoup(html, "html.parser")
    host = urlparse(base).netloc.lower().removeprefix("www.")
    out: dict[str, str] = {}
    for a in s.select("a[href]"):
        href = urljoin(base + "/", a["href"].split("#")[0])
        if urlparse(href).netloc.lower().removeprefix("www.") != host or SKIP_LINK.search(href):
            continue
        text = a.get_text(" ", strip=True)
        if href.rstrip("/") == base.rstrip("/") or (text and len(text) > 60):
            continue
        out.setdefault(href, text)
    return out


def missed(html: str | bytes, base: str, ours: list[str], live: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """(kind, url, link text) of each section of a live kind that none of our listing pages covers."""
    got = []
    langs = {_lang(o) for o in ours}
    for url, text in sections_on(html, base).items():
        if not text or NOT_A_NAME.search(text) or (len(langs) == 1 and _lang(url) not in langs):
            continue    # a picture link or a product card; or the other language's copy of a section we read
        last = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        if len(last) > 70 or NOT_OURS.search(text):
            continue    # a product's own address (OpenCart products sit at the top level)
        # the link's own words decide; its address only when the words say nothing ("Desktops" under /pc-and-laptops/)
        kind = kind_of(text) or kind_of(urlparse(url).path.replace("-", " ").replace("/", " "))
        if kind in live and not covered(url, ours):
            got.append((kind, url, text))
    # a section under another missed one is read with it: report the top one only
    tops = {_norm(u) for _, u, _ in got}
    return sorted({g for g in got if not any(_norm(g[1]).startswith(t + "/") for t in tops)})


def read_by_sections() -> dict[str, tuple[str, list[str]]]:
    """Each shop we read section by section: (home page, every listing page we read for it)."""
    from .cli import ELECTRONICS, SOURCES
    shops = {}
    for slug, (_name, base, method, _terms, params) in SOURCES.items():
        if method in ("shopify_json", "sitemap_pages", "darwish_sitemap"):
            continue    # the whole shop is read: nothing to miss
        shops[slug] = (base, list(params.get("listings", [])) + list(ELECTRONICS.get(slug, [])))
    return shops


def home_page(base: str, ours: list[str]) -> str:
    """The home page in the language of the pages we read (Leaders and Baghdad Corner open in Arabic; we read /en/)."""
    langs = {_lang(o) for o in ours}
    lang = langs.pop() if len(langs) == 1 else ""
    return f"{base}/{lang}/" if lang and lang != "%" else base + "/"


def check(client, only: list[str] | None = None) -> dict[str, list[tuple[str, str, str]]]:
    """{shop: missed sections}; a shop whose home page cannot be read is reported with one ("error", reason, "")."""
    from .display import LIVE_CATEGORIES
    report = {}
    for slug, (base, ours) in read_by_sections().items():
        if only and slug not in only:
            continue
        try:
            html = client.get(home_page(base, ours)).content
        except Exception as e:     # a bot check or refusal: we never work around one, it is only reported
            report[slug] = [("error", f"{type(e).__name__}: {str(e)[:80]}", "")]
            continue
        report[slug] = missed(html, base, ours, LIVE_CATEGORIES)
    return report


REPORT = Path.home() / ".derbani" / "missed_sections.json"
# Sections judged by hand that we do not read on purpose (no products of ours on them): in git, so the cloud has them.
SEEN = Path(__file__).resolve().parents[2] / "data" / "sections_seen.json"


def _seen() -> dict[str, str]:
    try:
        return json.loads(SEEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write(client=None) -> dict:
    """Nightly: every shop's missed sections not judged before -> ~/.derbani/missed_sections.json (daily doctor)."""
    from .collectors.base import PoliteClient
    seen = _seen()
    report = check(client or PoliteClient())
    new = {shop: [r for r in rows if r[0] == "error" or r[1] not in seen] for shop, rows in report.items()}
    new = {shop: rows for shop, rows in new.items() if rows}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"shops": len(new), "sections": sum(len(r) for r in new.values())}


def mark_seen(urls: list[str], why: str) -> int:
    """Sections looked at and left out on purpose (why: "no products of ours", "accessories", ...)."""
    seen = _seen()
    for u in urls:
        seen[u] = why
    SEEN.write_text(json.dumps(dict(sorted(seen.items())), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(urls)
