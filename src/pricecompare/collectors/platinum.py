"""Platinum connector: phone product URLs from sitemap.xml, price from each product page.

The category page only shows the first 16 items (no pagination), so the sitemap is the index.
Phones are picked from the URL slug; pages are fetched at the polite rate, capped per run.
"""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..matching.gadget import PREFIX as ELECTRONICS
from ..matching.parse import parse_title
from .base import PoliteClient
from .common import parse_price
from .shopify import RawOffer

ITEM_URL = re.compile(r"<loc>\s*(https?://[^<]*?/items/([^/<]+)\.html)\s*</loc>")


def phone_urls(sitemap_xml: str, category: str | None = None) -> list[tuple[str, str]]:
    """Product pages we compare, judged from the page name; `category` keeps only laptops ("laptop"), only the Stage 3
    electronics ("electronics": headphones, monitors...) or only the rest (phones, tablets, TVs, watches)."""
    out = []
    for url, slug in ITEM_URL.findall(sitemap_xml):
        url, slug = html.unescape(url), html.unescape(slug)   # "&amp;" in the sitemap is "&" in the address
        title = slug.replace("-", " ")
        p = parse_title(title)
        group = "laptop" if p.category == "laptop" else "electronics" if p.category in ELECTRONICS else "phone"
        if p.is_product and (category is None or group == category):
            out.append((url, title))
    return out


def parse_item(html: bytes, url: str) -> RawOffer | None:
    s = BeautifulSoup(html, "html.parser")
    h1 = next((h.get_text(" ", strip=True) for h in s.select("h1") if h.get_text(strip=True)), None)
    price = next((parse_price(e.get_text(" ", strip=True)) for e in s.select(".product-price")
                  if parse_price(e.get_text(" ", strip=True)) is not None), None)
    if not h1 or price is None:
        return None
    return RawOffer(
        external_id=urlparse(url).path.rsplit("/", 1)[-1],
        title=h1,
        url=url,
        price_jod=price,
        in_stock=bool(s.select_one(".stock-in-stock")),
        image_url=(lambda m: m["content"][:500] if m and m.get("content") else "")(s.select_one('meta[property="og:image"]')),
    )


def collect(client: PoliteClient, base_url: str, max_items: int = 150, max_laptops: int = 80, part: str = "main") -> list[RawOffer]:
    xml = client.get(f"{base_url}/sitemap.xml").text
    offers = []
    if part == "electronics":
        pages = phone_urls(xml, "electronics")[:120]
    else:
        pages = phone_urls(xml, "phone")[:max_items] + phone_urls(xml, "laptop")[:max_laptops]
    for url, _ in pages:
        try:
            page = client.get(url).content
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 410, 500):   # one broken product page: skip it (a refusal still stops the run)
                continue
            raise
        ro = parse_item(page, url)
        if ro:
            offers.append(ro)
    return offers
