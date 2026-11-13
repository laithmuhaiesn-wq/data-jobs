"""Readers for three shop systems seen in Jordan: Odoo (Newton Stores), Site123 (The Prof PC) and Zoho Commerce
(Al-Ruwwad). Each reads only public category pages, through the polite client (robots.txt, 3 s between requests).
Products shown without a price ("contact us for the best price", price 0) are skipped: there is nothing to compare.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from decimal import Decimal
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import PoliteClient, RobotsBlocked
from .common import parse_price
from .shopify import RawOffer


def _ok(price: Decimal | None) -> bool:
    return price is not None and price > 0


# ---- Odoo website shop: <form class="oe_product_cart">, pages at .../page/2
def parse_odoo(page: bytes, base: str) -> tuple[list[RawOffer], str | None]:
    s = BeautifulSoup(page, "html.parser")
    out = []
    for card in s.select("form.oe_product_cart"):
        a = card.select_one("a[itemprop=name]") or card.select_one(".o_wsale_products_item_title a")
        price_el = card.select_one("[itemprop=price]")
        if a is None or not a.get("href") or price_el is None:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        if not _ok(price):
            continue
        title = (a.get("content") or a.get_text(" ", strip=True)).strip()
        pid = card.select_one("input[name=product_id]")
        img = card.select_one("img")
        out.append(RawOffer(pid["value"] if pid and pid.get("value") else a["href"], title, urljoin(base, a["href"]), price, True,
                            urljoin(base, img["src"]) if img and img.get("src") else ""))
    nxt = s.select_one("ul.pagination li.page-item:last-child a.page-link[href], a.page-link[aria-label=Next][href]")
    href = nxt.get("href") if nxt else None
    return out, (urljoin(base, href) if href and href not in ("#", "") else None)


# ---- Site123 shop: <div class="e-commerce-product-box" data-unique-id> with title, description and price spans
def parse_site123(page: bytes, base: str) -> list[RawOffer]:
    s = BeautifulSoup(page, "html.parser")
    out = []
    for box in s.select("div.e-commerce-product-box[data-unique-id]"):
        a = box.select_one(".product-title a, h4.product-title a, .product-image a[href]")
        title_el = box.select_one(".product-title")
        prices = [parse_price(p.get_text(" ", strip=True)) for p in box.select('[data-type="price"]')]
        prices = [p for p in prices if _ok(p)]
        if a is None or not a.get("href") or title_el is None or not prices:
            continue
        # the shop's title is short ("Laptop Lenovo V15 Gen 5 | Core i5..."); the line under it carries RAM and storage
        desc = box.select_one(".product-description")
        title = title_el.get_text(" ", strip=True)
        if desc:
            title = f"{title} | {desc.get_text(' ', strip=True)}"
        out.append(RawOffer(box["data-unique-id"], title[:400], urljoin(base, a["href"].split("?")[0]), min(prices), True, ""))
    return out


# ---- Zoho Commerce: the category page carries its products as JSON ("products":[{name, url, selling_price, ...}])
def parse_zoho(page: bytes, base: str) -> list[RawOffer]:
    text = page.decode("utf-8", "ignore")
    out: dict[str, RawOffer] = {}
    dec = json.JSONDecoder()
    for m in re.finditer(r'"products":\[', text):
        try:
            items, _ = dec.raw_decode(text, m.end() - 1)
        except ValueError:
            continue
        for p in items if isinstance(items, list) else []:
            if not isinstance(p, dict) or not p.get("name") or not p.get("url"):
                continue
            price = parse_price(str(p.get("selling_price", "")))
            if not _ok(price):
                continue
            pid = str(p.get("product_id") or p["url"])
            img = next((i.get("url") for i in p.get("images") or [] if isinstance(i, dict) and i.get("url")), "")
            out[pid] = RawOffer(pid, htmllib.unescape(p["name"]).strip(), urljoin(base, p["url"]), price,
                                not p.get("is_out_of_stock", False), urljoin(base, img) if img else "")
    return list(out.values())


def collect(client: PoliteClient, kind: str, base: str, listings: list[str], max_pages: int = 20) -> list[RawOffer]:
    out: dict[str, RawOffer] = {}
    for start in listings:
        url, pages = start, 0
        while url and pages < max_pages:
            try:
                page = client.get(url).content
            except RobotsBlocked:
                break
            pages += 1
            if kind == "odoo":
                offers, url = parse_odoo(page, base)
            else:
                offers, url = (parse_site123 if kind == "site123" else parse_zoho)(page, base), None
            for o in offers:
                out[o.external_id] = o
    return list(out.values())
