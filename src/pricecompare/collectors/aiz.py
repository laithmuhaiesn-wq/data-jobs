"""Shops on the Active eCommerce (Laravel) system: Baghdad Corner / ركن بغداد (rokonbaghdad-jo.com, added 2026-11-23).

Category pages are plain HTML, 24 products a page, `?page=N` for the next one (robots.txt allows them; it only shuts
/admin, the uploader and ajax-search). Each card: <h3><a href=".../product/<slug>" title="name"> and the price in
<span class="fw-700 text-primary">259.00JOD</span>; an old price sits in <del>. The shop's terms forbid copying its texts
and pictures, so only the name (to match), the price and the link are kept: no picture address."""
from __future__ import annotations

from bs4 import BeautifulSoup

from .base import PoliteClient, RobotsBlocked
from .common import parse_price
from . import facts
from .opencart import keep
from .shopify import RawOffer

PAGE_SIZE = 24


def parse_listing(html: bytes) -> list[RawOffer]:
    s = BeautifulSoup(html, "html.parser")
    out = []
    for card in s.select(".aiz-card-box"):
        a = card.select_one("h3 a[href*='/product/']")
        price_el = card.select_one("span.fw-700.text-primary")
        if a is None or price_el is None:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        title = (a.get("title") or a.get_text(" ", strip=True)).strip()
        if not price or not title:
            continue
        url = a["href"].split("?")[0]
        out.append(RawOffer(external_id=url.rstrip("/").rsplit("/", 1)[-1], title=title, url=url, price_jod=price,
                            in_stock="out of stock" not in card.get_text(" ", strip=True).lower()))
    return out


def collect(client: PoliteClient, listing_urls: list[str], max_pages: int = 30) -> list[RawOffer]:
    out: dict[str, RawOffer] = {}
    for start in listing_urls:
        for page in range(1, max_pages + 1):
            try:
                html = client.get(start if page == 1 else f"{start}?page={page}").content
            except RobotsBlocked:
                break
            offers = parse_listing(html)
            new = [o for o in offers if o.external_id not in out]
            for o in offers:
                keep(out, o, facts.section(start))
            if len(offers) < PAGE_SIZE or not new:   # the last page, or a page that repeats the one before
                break
    return list(out.values())
