"""WooCommerce connector: category listing pages (+ product page for variable products).

Listing pages show one price per product. Variable products (e.g. iPhone with storage options)
show a range there, so for those we read the per-variation prices WooCommerce embeds in the
product page form (data-product_variations). Used / refurbished items are skipped (new only).
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

from bs4 import BeautifulSoup
from bs4.element import Tag

from .base import PoliteClient
from .common import img_url, parse_price
from .shopify import RawOffer

USED = re.compile(r"\b(used|like[- ]new|refurb\w*|open[- ]box|pre-?owned)\b", re.I)


def _title_case_attr(v: str) -> str:
    v = re.sub(r"-en$", "", v)
    return v.replace("-", " ")


def _tag_storage(classes: list[str]) -> str | None:
    """Storage size from product tags (e.g. product_tag-iphone-13-128gb) when the title omits it."""
    for c in classes:
        if c.startswith("product_tag-"):
            m = re.search(r"(?<!\d)(\d{2,4})-?(gb|tb)\b", c, re.I)
            if m:
                return f"{m.group(1)}{m.group(2).upper()}"
    return None


def _with_storage(title: str, storage: str | None) -> str:
    return title if not storage or re.search(r"\d\s?(gb|tb)\b", title, re.I) else f"{title} {storage}"


def _is_used(classes: list[str], title: str) -> bool:
    if USED.search(title):
        return True
    return any(c.startswith("product_tag-") and USED.search(c[len("product_tag-"):].replace("-", " ")) for c in classes)


def _variation_in_stock(v: dict) -> bool:
    """Shop text wins when present ("Available on backorder" is not in stock); else WooCommerce's flag."""
    text = BeautifulSoup(v.get("availability_html") or "", "html.parser").get_text(" ", strip=True).lower()
    if text:
        return "in stock" in text and "backorder" not in text
    return bool(v.get("is_in_stock"))


def parse_variations(html: bytes, title: str, url: str, store_prefix: str, image: str = "") -> list[RawOffer]:
    form = BeautifulSoup(html, "html.parser").select_one("form.variations_form")
    if form is None or not form.get("data-product_variations"):
        return []
    out = []
    variations = json.loads(form["data-product_variations"])
    if not isinstance(variations, list):  # "false": the shop loads this product's options later, they are not in the page
        return []
    for v in variations:
        if v.get("display_price") in (None, "", False):
            continue
        attrs = v.get("attributes") or {}
        attrs = attrs if isinstance(attrs, dict) else {}  # shops send [] when a variation has no attributes
        opts = " ".join(_title_case_attr(x) for x in attrs.values() if x)
        out.append(RawOffer(
            external_id=f"{store_prefix}-v{v['variation_id']}",
            title=f"{title} - {opts}".strip(" -"),
            url=url,
            price_jod=Decimal(str(v["display_price"])),
            in_stock=_variation_in_stock(v),
            image_url=((v.get("image") or {}).get("src") or image)[:500],
        ))
    return out


def parse_listing(html: bytes) -> tuple[list[dict], str | None]:
    """Returns (items, next_page_url). Each item: id, title, url, in_stock, variable, price, used."""
    s = BeautifulSoup(html, "html.parser")
    items = []
    for p in s.select(".type-product"):
        a = p.select_one(".woocommerce-loop-product__title a, .product-title a, .name a, h2 a, h3 a")
        title_el = a
        if a is None:   # themes such as Electro put the title inside the link: <a><h2 class="...title">
            title_el = p.select_one(".woocommerce-loop-product__title")
            a = title_el.find_parent("a") if title_el else None
        if a is None or not a.get("href"):
            continue
        classes = p.get("class", [])
        title = title_el.get_text(" ", strip=True).split(" | ")[0].strip()
        price_el = p.select_one(".price")
        price_text = price_el.get_text(" ", strip=True) if price_el else ""
        ins = price_el.select_one("ins .amount") if isinstance(price_el, Tag) else None
        first = (ins or (price_el.select_one(".amount") if price_el else None))
        pid = next((c[5:] for c in classes if re.fullmatch(r"post-\d+", c)), a["href"])
        items.append({
            "id": pid, "title": title, "url": a["href"],
            "in_stock": "instock" in classes,
            "variable": "product-type-variable" in classes or "From" in price_text or "–" in price_text,
            "price": parse_price(first.get_text(" ", strip=True)) if first else None,
            "used": _is_used(classes, title),
            "tag_storage": _tag_storage(classes),
            "image": img_url(p, a["href"]),
        })
    if not items:
        items = _cards(s)
    nxt = s.select_one("a.next.page-numbers")
    return items, nxt["href"] if nxt else None


def _cards(s: BeautifulSoup) -> list[dict]:
    """Custom WordPress shop cards (H4M): <article class="hws-card" data-cmp="{id, name, price, img}"> with a.nm link.
    The listing shows only orderable products, so each card is in stock."""
    items = []
    for card in s.select("article.hws-card[data-cmp]"):
        try:
            d = json.loads(card["data-cmp"])
        except ValueError:
            continue
        a = card.select_one("a.nm, a.ph")
        if a is None or not a.get("href") or not d.get("name") or d.get("price") in (None, ""):
            continue
        title = str(d["name"]).strip()
        items.append({"id": str(d.get("id") or a["href"]), "title": title, "url": a["href"], "in_stock": True,
                      "variable": False, "price": parse_price(str(d["price"])), "used": _is_used([], title),
                      "tag_storage": None, "image": str(d.get("img") or "")})
    return items


def collect(client: PoliteClient, store_prefix: str, listing_urls: list[str], max_pages: int = 15) -> list[RawOffer]:
    out: dict[str, RawOffer] = {}
    for start in listing_urls:
        url, pages = start, 0
        while url and pages < max_pages:
            items, url = parse_listing(client.get(url).content)
            pages += 1
            for it in items:
                if it["used"]:
                    continue
                options = parse_variations(client.get(it["url"]).content, it["title"], it["url"], store_prefix, it["image"]) if it["variable"] else []
                for ro in options:
                    ro.title = _with_storage(ro.title, it["tag_storage"])
                    out[ro.external_id] = ro
                if not options and it["price"] is not None:  # a simple product, or one whose options are not in the page
                    out[f"{store_prefix}-{it['id']}"] = RawOffer(
                        f"{store_prefix}-{it['id']}", _with_storage(it["title"], it["tag_storage"]),
                        it["url"], it["price"], it["in_stock"], it["image"])
    return list(out.values())
