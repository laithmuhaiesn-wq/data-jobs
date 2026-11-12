"""Action connector: server-rendered category pages (Nuxt) with a card per product.

The link's title attribute carries the fuller product name ("... White, e-SIM, 256GB"), the price sits
in a bold green span. Pages are walked with ?page=N until one returns no cards.
"""
from __future__ import annotations

import re
from decimal import Decimal

from bs4 import BeautifulSoup

from .base import PoliteClient
from .common import img_url, parse_price
from .shopify import RawOffer

OUT_OF_STOCK = re.compile(r"out of stock|sold out|نفذ", re.I)


def parse_page(html: bytes, base_url: str) -> list[RawOffer]:
    s = BeautifulSoup(html, "html.parser")
    offers = []
    for a in s.select('a.content[href*="/product/"]'):
        card = a.find_parent("div", class_=re.compile("card-md")) or a.parent
        price_el = card.select_one("span.text-green-700") or card.select_one("span.font-bold")
        price = parse_price(price_el.get_text(" ", strip=True).replace("\xa0", " ")) if price_el else None
        if price is None:
            continue
        href = a["href"]
        offers.append(RawOffer(
            external_id=href.rstrip("/").rsplit("/", 1)[-1],
            title=(a.get("title") or a.get_text(" ", strip=True)).strip(),
            url=href if href.startswith("http") else base_url + href,
            price_jod=Decimal(price),
            in_stock=not OUT_OF_STOCK.search(card.get_text(" ", strip=True)),
            image_url=img_url(card, base_url),
        ))
    return offers


def collect(client: PoliteClient, base_url: str, listing_url: str, max_pages: int = 25) -> list[RawOffer]:
    out: dict[str, RawOffer] = {}
    for page in range(1, max_pages + 1):
        url = listing_url if page == 1 else f"{listing_url}?page={page}"
        batch = parse_page(client.get(url).content, base_url)
        new = [o for o in batch if o.external_id not in out]
        if not new:
            break
        for o in new:
            out[o.external_id] = o
    return list(out.values())
