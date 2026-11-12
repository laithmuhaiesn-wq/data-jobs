"""Darwish Electronics connector (Magento): product URLs from the shop's own sitemap, price from each product page.

The home page answers automated clients with a Cloudflare challenge, so it is never fetched (and never worked around).
The sitemap named in robots.txt and the product pages themselves are open to clients and allowed by robots.txt.
Phones and tablets are picked from the URL name; only those pages are fetched, at the polite rate, capped per run.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..matching.parse import parse_title
from .base import PoliteClient
from .shopify import RawOffer

SITEMAP = "/sitemap_en_new.xml"
ITEM_URL = re.compile(r"<loc>\s*https?://darwishelectronics\.jo(/en/([^<]+?)\.html)\s*</loc>")


def product_urls(sitemap_xml: str, base_url: str) -> list[str]:
    """Phone and tablet pages only, judged from the page name ("samsung-a26-sm-a266bzkimea-6gb-128gb")."""
    out = []
    for path, name in ITEM_URL.findall(sitemap_xml):
        if parse_title(name.replace("-", " ")).is_product:
            out.append(base_url + path)  # the sitemap lists http:// addresses; the shop serves https
    return list(dict.fromkeys(out))


def parse_item(html: bytes, url: str) -> RawOffer | None:
    s = BeautifulSoup(html, "html.parser")
    title = s.select_one("h1.page-title")
    final = s.select_one('[data-price-type="finalPrice"]')  # the selling price, never the crossed-out old one
    if title is None or final is None:
        return None
    try:
        price = Decimal(final.get("data-price-amount", "")).quantize(Decimal("0.001"))
    except InvalidOperation:
        return None
    if price <= 0:
        return None
    out_of_stock = s.select_one(".stock.unavailable, .product-info-stock-sku .unavailable") is not None
    image = s.select_one('meta[property="og:image"]')
    return RawOffer(
        external_id=urlparse(url).path.rsplit("/", 1)[-1].removesuffix(".html"),
        title=title.get_text(" ", strip=True),
        url=url,
        price_jod=price,
        in_stock=not out_of_stock and s.select_one("#product-addtocart-button") is not None,
        image_url=(image.get("content") or "")[:500] if image else "",
    )


def collect(client: PoliteClient, base_url: str, max_items: int = 250) -> list[RawOffer]:
    xml = client.get(base_url + SITEMAP).text
    offers = []
    for url in product_urls(xml, base_url)[:max_items]:
        ro = parse_item(client.get(url).content, url)
        if ro:
            offers.append(ro)
    return offers
