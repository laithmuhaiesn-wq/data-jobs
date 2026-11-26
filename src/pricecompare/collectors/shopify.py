"""Shopify connector: public /collections/<handle>/products.json (title, price, stock)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from . import facts
from .base import PoliteClient


@dataclass
class RawOffer:
    external_id: str
    title: str
    url: str
    price_jod: Decimal
    in_stock: bool
    image_url: str = ""
    facts: dict[str, str] = field(default_factory=dict)   # see facts.py
    specs: dict[str, str] = field(default_factory=dict)   # see shop_specs.py (from the list already read; never an extra request)


def parse_products(payload: dict, base_url: str) -> list[RawOffer]:
    from ..shop_specs import from_html
    offers = []
    for p in payload.get("products", []):
        specs = from_html(p.get("body_html") or "") if p.get("body_html") else {}
        for v in p.get("variants", []):
            title = p["title"]
            if v.get("title") and v["title"] != "Default Title":
                title = f"{title} - {v['title']}"
            img = ((p.get("images") or [{}])[0] or {}).get("src") or (p.get("image") or {}).get("src") or ""
            offers.append(
                RawOffer(
                    external_id=str(v["id"]),
                    title=title,
                    url=f"{base_url}/products/{p['handle']}?variant={v['id']}",
                    price_jod=Decimal(str(v["price"])),
                    in_stock=bool(v.get("available", False)),
                    image_url=img[:500],
                    facts=facts.shopify(p, v),
                    specs=specs,
                )
            )
    return offers


def collect(client: PoliteClient, base_url: str, collection_handle: str, page_size: int = 250, max_pages: int = 10) -> list[RawOffer]:
    out: list[RawOffer] = []
    for page in range(1, max_pages + 1):
        url = f"{base_url}/collections/{collection_handle}/products.json?limit={page_size}&page={page}"
        payload = client.get(url).json()
        if not payload.get("products"):
            break
        out.extend(parse_products(payload, base_url))
        if len(payload["products"]) < page_size:
            break
    return out


def collect_pages(client: PoliteClient, base_url: str, start_page: int = 1, pages: int = 3, page_size: int = 250,
                  max_pages: int = 40) -> tuple[list[RawOffer], int, Exception | None]:
    """A few pages of the shop's one full product list (/products.json), products only (no cases or cables).

    2026-11-17: Shopify answers the per-section lists with "slow down" (429, "local_rate_limited") from a home
    connection, while the full list answers; one list of ~5-10 pages is also far fewer requests than ~25 sections.
    2026-11-18: even the full list was cut at page 2 run after run, so the whole read was lost every time. Now each
    run reads up to `pages` pages from `start_page` and keeps what it read. Returns (offers, next_page, error):
    next_page is where the next run starts (1 once the list is finished); error is the "slow down" that stopped the
    read early (offers read before it are kept), or None."""
    from ..matching.parse import parse_title

    out: list[RawOffer] = []
    page = max(1, start_page)
    for _ in range(pages):
        try:
            payload = client.get(f"{base_url}/products.json?limit={page_size}&page={page}").json()
        except Exception as e:
            if not out:
                raise
            return out, page, e
        products = payload.get("products") or []
        out.extend(o for o in parse_products(payload, base_url) if parse_title(o.title).is_product)
        if not products or len(products) < page_size or page >= max_pages:
            return out, 1, None
        page += 1
    return out, page, None


def collect_all(client: PoliteClient, base_url: str, page_size: int = 250, max_pages: int = 40) -> list[RawOffer]:
    """The whole list in one go (used by tests and one-off reads)."""
    offers, _, error = collect_pages(client, base_url, 1, max_pages, page_size, max_pages)
    if error:
        raise error
    return offers
