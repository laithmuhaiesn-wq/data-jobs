"""Plain facts a shop's list already tells us next to the title (owner's yes 2026-11-25, docs/product-data-plan.md step 1):
brand, maker's or shop's code, the shop's own kind, the section the listing stood in, and the option (colour, size).

Never descriptions, never an extra request: only what is in the page or list that was read for the price anyway.
Keys: brand, code, gtin, kind, section, option. Every value is short text; an empty one is left out."""
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urlparse

KEYS = ("brand", "code", "gtin", "kind", "section", "option")
LIMIT = 200
EMPTY = {"", "default title", "n/a", "na", "none", "null", "-", "default"}


def clean(**values) -> dict[str, str]:
    out = {}
    for key, value in values.items():
        if key not in KEYS:
            raise KeyError(key)
        text = re.sub(r"\s+", " ", str(value if value is not None else "")).strip()
        if text.lower() not in EMPTY:
            out[key] = text[:LIMIT]
    return out


def section(url: str) -> str:
    """The shop's own section of a list address: ".../product-category/mobiles/apple/?x=1" -> "mobiles/apple"."""
    skip = {"", "en", "ar", "product-category", "category", "categories", "collections", "shop", "store", "page", "products",
            "index.php", "brand", "brands"}
    parts = [unquote(p) for p in urlparse(url).path.split("/")]
    parts = [p for p in parts if p.lower() not in skip and not p.isdigit()]
    return "/".join(parts[-2:])


def add_section(facts: dict[str, str], name: str) -> None:
    """A listing can stand in several sections: all are kept, in the order seen."""
    if not name:
        return
    have = facts.get("section", "")
    if name not in have.split(" | "):
        facts["section"] = (f"{have} | {name}" if have else name)[:LIMIT]


def woo(classes: list[str], sku: str | None = None) -> dict[str, str]:
    """WooCommerce marks every card with its categories and brand as class names."""
    cats = [unquote(c[12:]) for c in classes if c.startswith("product_cat-")]
    brand = next((unquote(c.split("-", 1)[1]) for c in classes
                  if re.match(r"(?:product_brand|pa_brand|pwb-brand|yith_product_brand|berocket_brand)-", c)), "")
    return clean(brand=brand.replace("-", " "), kind=" | ".join(cats), code=sku)


def shopify(product: dict, variant: dict) -> dict[str, str]:
    option = variant.get("title") or ""
    return clean(brand=product.get("vendor"), kind=product.get("product_type"), code=variant.get("sku"), option=option)


def ld_json(html: bytes) -> dict[str, str]:
    """Brand and codes of a product page that says them for search engines (schema.org Product)."""
    text = html.decode("utf-8", "ignore")
    for raw in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", text, re.S | re.I):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if isinstance(it, dict) and it.get("@type") in ("Product", ["Product"]):
                brand = it.get("brand")
                brand = brand.get("name") if isinstance(brand, dict) else brand
                gtin = next((it[k] for k in ("gtin13", "gtin14", "gtin12", "gtin8", "gtin") if it.get(k)), None)
                return clean(brand=brand, code=it.get("mpn") or it.get("sku"), gtin=gtin, kind=it.get("category"))
    return {}
