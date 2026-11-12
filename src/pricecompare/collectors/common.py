from __future__ import annotations

import re
from decimal import Decimal


def parse_price(text: str) -> Decimal | None:
    """'1.299,00 JOD' / '239,00' / '999.00 د.أ' / '1,299.00' -> Decimal."""
    m = re.search(r"\d[\d.,]*", text)
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thousands = "." if dec == "," else ","
        s = s.replace(thousands, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) else s.replace(",", "")
    return Decimal(s)


def img_url(tag, base: str = "") -> str:
    """Picture address of the first <img> in a parsed tag (lazy-load attributes too); '' if none. Never fetched, only stored."""
    from urllib.parse import quote, urljoin
    img = tag.select_one("img") if tag is not None else None
    if img is None:
        return ""
    for k in ("data-src", "data-lazy-src", "data-original", "src"):
        v = (img.get(k) or "").strip()
        if v and not v.startswith("data:"):
            return quote(urljoin(base, v), safe=":/?&=%+,@;~()!*'$#[]")[:500]  # spaces in paths break image loading
    return ""
