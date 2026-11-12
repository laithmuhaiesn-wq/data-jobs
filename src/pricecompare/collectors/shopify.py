"""Shopify connector: public /collections/<handle>/products.json (title, price, stock)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .base import PoliteClient


@dataclass
class RawOffer:
    external_id: str
    title: str
    url: str
    price_jod: Decimal
    in_stock: bool
    image_url: str = ""


def parse_products(payload: dict, base_url: str) -> list[RawOffer]:
    offers = []
    for p in payload.get("products", []):
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
