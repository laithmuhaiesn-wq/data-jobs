"""Products our listing pages never show, read from the shop's own sitemap and product pages (2026-11-27).

Owner 2026-11-27: "handle all shops in the best way so we can read all the products from their shop". A shop's sitemap
(named in robots.txt, allowed by it) lists every product page with its name. Those whose name reads as a kind we show,
and that no listing page of ours gave us, are read one by one from their own page: the schema.org Product data every
shop theme puts there (name, price, availability, picture). New pages first, then the ones read longest ago, a fixed
number per run at the polite pace; robots.txt is checked on every request as always. City Center is the main reason:
its robots.txt forbids `?page=`, so its listings show only their first 20 items.
"""
from __future__ import annotations

import html as html_lib
import json
import time
from dataclasses import dataclass, replace
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from ..matching.parse import parse_title
from .common import parse_price
from .base import PoliteClient
from .shopify import RawOffer

PREFIX = "page-"          # external ids of listings read this way (a listing page's ids never start with it)
URL_BLOCK = re.compile(r"<url>(.*?)</url>", re.S)
SKIP_URL = re.compile(r"[?&]lang=ar|/ar/|/ar-jo/|/product-category/|/category/|/categories/|/brand", re.I)


def sitemap_urls(client: PoliteClient, base: str) -> list[str]:
    try:
        robots = client.get(base + "/robots.txt").text
        maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots)
    except Exception:
        maps = []
    return maps or [base + "/sitemap.xml"]


def entries(xml: str) -> tuple[list[str], list[tuple[str, str]]]:
    """(child sitemaps, [(page address, name from the picture caption or "")])."""
    subs = re.findall(r"<sitemap>\s*<loc>\s*([^<\s]+)", xml)
    out = []
    for block in URL_BLOCK.findall(xml):
        m = re.search(r"<loc>\s*(?:<!\[CDATA\[)?\s*([^<\s\]]+)", block)
        cap = re.search(r"<image:(?:caption|title)>\s*(?:<!\[CDATA\[)?([^<\]]+)", block)
        if m:
            name = (cap.group(1) if cap else "").replace("&quot;", '"').replace("&amp;", "&").strip()
            out.append((m.group(1).replace("&amp;", "&"), name))
    return subs, out


def page_name(url: str, caption: str) -> str:
    return caption or unquote(urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]).removesuffix(".html").replace("-", " ")


@dataclass(frozen=True)
class Rules:
    """What one shop's pages need (2026-11-27). rewrite: (from, to) for the page address, e.g. Action's sitemap lists
    the Arabic pages and our listings the English ones; skip: addresses that are not products (ProfPC's sections sit
    under /shop/ like its products); no_out_price: an out-of-stock page shows a made-up price (Action shows 5 JOD), so
    the last price read stays and a product never listed before is not kept."""
    rewrite: tuple[str, str] | None = None
    skip: str | None = None
    no_out_price: bool = False


def products(client: PoliteClient, base: str, kinds: tuple[str, ...], rules: Rules = Rules()) -> list[tuple[str, str]]:
    """Every product page in the shop's sitemaps whose name reads as one of our kinds: [(address, name)]."""
    todo, seen, out = sitemap_urls(client, base), set(), {}
    while todo:
        url = todo.pop(0)
        if url in seen or len(seen) > 60:
            continue
        seen.add(url)
        try:
            subs, items = entries(client.get(url).text)
        except Exception:
            continue
        todo += [u for u in subs if not re.search(r"post-sitemap|page-sitemap|categor|tag|brand|author|blog|image", u, re.I)]
        for u, cap in items:
            if SKIP_URL.search(u) or (rules.skip and re.search(rules.skip, u)):
                continue
            if rules.rewrite and u.startswith(rules.rewrite[0]):
                u = rules.rewrite[1] + u[len(rules.rewrite[0]):]
            name = page_name(u, cap)
            p = parse_title(name)
            if p.is_product and p.category in kinds:
                out.setdefault(u.replace("http://", "https://", 1), name)
    return list(out.items())


def _price(v) -> Decimal | None:
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d > 0 else None


def _product_ld(s: BeautifulSoup) -> dict | None:
    for tag in s.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack += d
            elif isinstance(d, dict):
                t = d.get("@type")
                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return d
                stack += [v for k, v in d.items() if k in ("@graph", "mainEntity", "itemListElement")]
    return None


def _theme(s: BeautifulSoup) -> tuple[str, Decimal, bool] | None:
    """(name, price, in stock) from the shop platform's own product page, for shops with no schema.org data (2026-11-27).

    Magento (Darwish): the selling price, never the crossed-out one; WooCommerce (BCI): the main product's classes say
    instock / outofstock; Odoo (Newton): the price in its hidden itemprop, in stock while the page offers "Add to cart"
    (the shop's own listing shows the same: Odoo lists only what can be ordered)."""
    final = s.select_one('.product-info-main [data-price-type="finalPrice"], [data-price-type="finalPrice"]')
    title = s.select_one("h1.page-title")
    if final is not None and title is not None:
        out = s.select_one(".stock.unavailable, .product-info-stock-sku .unavailable") is not None
        return (title.get_text(" ", strip=True), _price(final.get("data-price-amount")),
                not out and s.select_one("#product-addtocart-button") is not None)
    main = s.select_one("div[id^=product-].type-product")
    title = s.select_one("h1.product_title")
    if main is not None and title is not None:
        box = main.select_one(".summary .price") or main.select_one(".price")
        amount = box and (box.select_one("ins .amount") or box.select_one(".amount"))
        cls = main.get("class") or []
        if amount is None or "product-type-variable" in cls or ("instock" not in cls and "outofstock" not in cls):
            return None     # a choice of colours or sizes has one price each: the listing reader handles those
        return title.get_text(" ", strip=True), parse_price(amount.get_text(" ", strip=True)), "instock" in cls
    odoo = s.select_one(".js_main_product")
    title = s.select_one('h1[itemprop="name"]')
    cur = s.select_one('.js_main_product [itemprop="priceCurrency"]') if odoo else None
    el = odoo.select_one('[itemprop="price"]') if odoo else None
    if el is not None and title is not None and cur is not None and cur.get_text(strip=True).upper() in ("JOD", "JD"):
        return (title.get_text(" ", strip=True), _price(el.get_text(strip=True)),
                s.select_one("#add_to_cart, a.js_check_product") is not None)
    return None


def parse_page(html: bytes | str, url: str) -> RawOffer | None:
    """One product page: its schema.org Product (JSON-LD), else its itemprop and og: tags, else the shop platform's own
    page. None when there is no sure price and stock."""
    s = BeautifulSoup(html, "html.parser")
    ld = _product_ld(s)
    name = price = image = None
    stock = None
    if ld:
        name = ld.get("name")
        offers = ld.get("offers") or {}
        offers = offers[0] if isinstance(offers, list) and offers else offers
        if isinstance(offers, dict):
            price = _price(offers.get("price") or offers.get("lowPrice"))
            cur = (offers.get("priceCurrency") or "JOD").upper()
            if cur not in ("JOD", "JD"):
                price = None
            av = str(offers.get("availability") or "")
            stock = None if not av else ("InStock" in av or "PreOrder" in av or "LimitedAvailability" in av)
        img = ld.get("image")
        image = (img[0] if isinstance(img, list) and img else img) if not isinstance(img, dict) else img.get("url")
    if price is None:
        el = s.select_one('[itemprop="price"]')
        price = _price(el.get("content") or el.get_text()) if el else None
        if price is None:
            meta = s.select_one('meta[property="product:price:amount"]')
            price = _price(meta.get("content")) if meta else None
    if not name:
        meta = s.select_one('meta[property="og:title"]') or s.select_one("h1")
        name = (meta.get("content") if meta and meta.name == "meta" else meta.get_text(" ", strip=True)) if meta else None
    if stock is None:
        el = s.select_one('[itemprop="availability"]')
        av = (el.get("href") or el.get("content") or "") if el else ""
        stock = ("InStock" in av) if av else None
    if not name or price is None or stock is None:
        themed = _theme(s)
        if not themed or not themed[0] or themed[1] is None:
            return None      # without a sure price and stock we keep nothing rather than guess
        name, price, stock = themed
    if not image:
        meta = s.select_one('meta[property="og:image"]')
        image = meta.get("content") if meta else ""
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1] or url
    return RawOffer(external_id=PREFIX + slug[:180], title=html_lib.unescape(str(name)).strip(), url=url, price_jod=price, in_stock=bool(stock),
                    image_url=str(image or "")[:500])


def collect(client: PoliteClient, base: str, kinds: tuple[str, ...], held: dict[str, float], listed: set[str],
            max_pages: int, rules: Rules = Rules(), last: dict[str, Decimal] | None = None,
            tried: dict[str, float] | None = None) -> list[RawOffer]:
    """Up to max_pages product pages: never read ones first, then those read longest ago.

    held: {address: last read (epoch seconds)} of the listings this reader keeps; listed: addresses our listing pages
    already give us (never read here, to keep one listing per page); last: {address: last price} of those held;
    tried: {address: when} of pages read that gave nothing to keep, filled in here, so they wait their turn too."""
    found = [(u, n) for u, n in products(client, base, kinds, rules) if _key(u) not in listed]
    tried = {} if tried is None else tried
    found.sort(key=lambda un: held.get(_key(un[0])) or tried.get(_key(un[0]), 0.0))
    out = []
    for url, _name in found[:max_pages]:
        try:
            o = parse_page(client.get(url).content, url)
        except Exception as e:
            if type(e).__name__ in ("RobotsBlocked",):
                continue
            raise
        if o is not None and rules.no_out_price and not o.in_stock:
            old = (last or {}).get(_key(url))
            o = None if old is None else replace(o, price_jod=old)
        if o is not None:
            out.append(o)
        else:
            tried[_key(url)] = time.time()
    return out


def _key(url: str) -> str:
    return url.replace("http://", "https://", 1).split("?")[0].rstrip("/").lower()
