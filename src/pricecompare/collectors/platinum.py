"""Platinum connector: phone product URLs from sitemap.xml, price from each product page.

The category page only shows the first 16 items (no pagination), so the sitemap is the index.
Phones are picked from the URL slug; pages are fetched at the polite rate, capped per run.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..matching.parse import parse_title
from .base import PoliteClient
from .common import parse_price
from .shopify import RawOffer

ITEM_URL = re.compile(r"<loc>\s*(https?://[^<]*?/items/([^/<]+)\.html)\s*</loc>")


def phone_urls(sitemap_xml: str) -> list[tuple[str, str]]:
    out = []
    for url, slug in ITEM_URL.findall(sitemap_xml):
        title = slug.replace("-", " ")
        if parse_title(title).is_product:
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


def collect(client: PoliteClient, base_url: str, max_items: int = 150) -> list[RawOffer]:
    xml = client.get(f"{base_url}/sitemap.xml").text
    offers = []
    for url, _ in phone_urls(xml)[:max_items]:
        ro = parse_item(client.get(url).content, url)
        if ro:
            offers.append(ro)
    return offers
