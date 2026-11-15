"""OpenCart connector: category listing pages (price + link + title on the listing).

Pagination follows the shop's own page links; if robots.txt forbids a page URL (City Center blocks
`?page=`) we stop there and keep what page 1 gave us rather than fetching it.
"""
from __future__ import annotations

import re
from decimal import Decimal

from bs4 import BeautifulSoup

from .base import PoliteClient, RobotsBlocked
from .common import img_url, parse_price
from .shopify import RawOffer

OUT_OF_STOCK = re.compile(r"out of stock|sold out|unavailable|نفذ", re.I)


def parse_listing(html: bytes) -> tuple[list[RawOffer], str | None]:
    s = BeautifulSoup(html, "html.parser")
    offers = []
    for c in s.select(".product-thumb"):
        a = c.select_one(".caption h4 a, h4 a, .name a")  # the Journal theme (Ammar Mobile) puts the title in .name
        # a discounted card holds both .price-old and .price-new inside .price; take the new (current) price, never the old one
        price_el = c.select_one(".price-new") or c.select_one(".price-regular, .price-normal") or c.select_one(".price")
        if a is None or not a.get("href") or price_el is None:
            continue
        price = parse_price(re.sub(r"\s+", "", price_el.get_text()))
        if price is None or Decimal(price) <= 0:  # "Price 0JD" is a placeholder for a phone the shop does not sell now
            continue
        box = c.find_parent(class_="product-layout")
        offers.append(RawOffer(
            external_id=a["href"].rstrip("/").rsplit("/", 1)[-1],
            title=a.get_text(" ", strip=True),
            url=a["href"],
            price_jod=Decimal(price),
            in_stock=not (OUT_OF_STOCK.search(c.get_text(" ", strip=True)) or (box is not None and "out-of-stock" in (box.get("class") or []))),
            image_url=img_url(c, a["href"]),
        ))
    # Oriental Store's own theme (since 2026-11-15): <article class="card"> with .card-name, .card-price and .stock
    for c in s.select("article.card"):
        a = c.select_one(".card-name a")
        price_box = c.select_one(".card-price")
        if a is None or not a.get("href") or price_box is None:
            continue
        for old in price_box.select("s, del, .old, .price-old"):      # a sale shows the old price struck through
            old.decompose()
        el = price_box.select_one(".price-new, .new, .price") or price_box
        price = parse_price(re.sub(r"\s+", "", el.get_text()))
        if price is None or Decimal(price) <= 0:
            continue
        stock = c.select_one(".stock")
        offers.append(RawOffer(
            external_id=a["href"].rstrip("/").rsplit("/", 1)[-1],
            title=a.get_text(" ", strip=True),
            url=a["href"],
            price_jod=Decimal(price),
            in_stock=not (stock is not None and OUT_OF_STOCK.search(stock.get_text(" ", strip=True))),
            image_url=img_url(c, a["href"]),
        ))
    nxt = None
    for link in s.select(".pagination a"):
        if link.get_text(strip=True) in (">", "›", "»", "Next"):
            nxt = link["href"]
    if nxt is None and offers:
        more = s.select_one('a[rel="next"][href]')
        nxt = more["href"] if more else None
    return offers, nxt


def collect(client: PoliteClient, listing_urls: list[str], max_pages: int = 20) -> list[RawOffer]:
    out: dict[str, RawOffer] = {}
    for start in listing_urls:
        url, pages = start, 0
        while url and pages < max_pages:
            try:
                html = client.get(url).content
            except RobotsBlocked:
                break
            offers, url = parse_listing(html)
            pages += 1
            for o in offers:
                out[o.external_id] = o
    return list(out.values())
