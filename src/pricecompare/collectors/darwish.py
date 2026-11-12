"""Darwish Electronics connector (Magento): product URLs from the shop's own sitemap, price from each product page.

The home page answers automated clients with a Cloudflare challenge, so it is never fetched (and never worked around).
The sitemap named in robots.txt and the product pages themselves are open to clients and allowed by robots.txt.
Phones and tablets are picked from the URL name; only those pages are fetched, at the polite rate, capped per run.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from ..matching.parse import parse_title
from .base import ChallengeBlocked, PoliteClient
from .shopify import RawOffer

SITEMAP = "/sitemap_en_new.xml"
# Words only TVs, laptops and earbuds use in their page names. Not "oled" or "core": phones say "p-oled", "octa-core".
NOT_PHONE_PAGE = re.compile(r"(^|-)(led|qled|uhd|4k|8k|tv|ideapad|thinkpad|thinkbook|loq|yoga|vivobook|zenbook|legion|"
                            r"intelr?|ryzen|celeron|i[3579]|ssd|win11|win|laptop|freebuds|buds|earbuds|watch|band)(-|$)")
ITEM_URL = re.compile(r"<loc>\s*https?://darwishelectronics\.jo(/en/([^<]+?)\.html)\s*</loc>")


def product_urls(sitemap_xml: str, base_url: str) -> list[str]:
    """Phone and tablet pages only, judged from the page name ("samsung-a26-sm-a266bzkimea-6gb-128gb")."""
    out = []
    for path, name in ITEM_URL.findall(sitemap_xml):
        # TVs ("tcl-55-led-55c645-4k"), laptops and earbuds can look like phone names: they are never fetched
        if parse_title(name.replace("-", " ")).is_product and not NOT_PHONE_PAGE.search(name):
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
        try:
            page = client.get(url)
        except (httpx.HTTPStatusError, ChallengeBlocked) as e:
            # The shop is refusing us (403 / too many requests / a bot check): stop politely and keep what we already
            # have. Never retried another way. With nothing collected yet, the run fails so it shows on the dashboard.
            refused = isinstance(e, ChallengeBlocked) or e.response.status_code in (403, 429)
            if refused and offers:
                break
            raise
        ro = parse_item(page.content, url)
        if ro:
            offers.append(ro)
    return offers
