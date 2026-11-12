"""Human-friendly names for the app (the database keeps lowercase matching keys)."""
from __future__ import annotations

import re

BRAND_AR = {
    "Apple": "آبل", "Samsung": "سامسونج", "Xiaomi": "شاومي", "Honor": "هونر", "Huawei": "هواوي", "Infinix": "إنفينيكس",
    "Motorola": "موتورولا", "Oppo": "أوبو", "Realme": "ريلمي", "Tecno": "تكنو", "Nokia": "نوكيا", "TCL": "تي سي إل",
    "Itel": "آيتيل", "Vivo": "فيفو", "Google": "جوجل", "OnePlus": "ون بلس", "Nothing": "ناثينج", "ZTE": "زد تي إي", "Sony": "سوني",
}
UPPER_WORDS = {"fe": "FE", "se": "SE", "gt": "GT", "ai": "AI", "nfc": "NFC", "xl": "XL",
               "ipad": "iPad", "matepad": "MatePad", "papermatte": "PaperMatte", "xpad": "XPad"}


def _token(tok: str, brand: str) -> str:
    if tok == "iphone":
        return "iPhone"
    if tok in UPPER_WORDS:
        return UPPER_WORDS[tok]
    m = re.fullmatch(r"([45])g", tok)
    if m:
        return f"{m.group(1)}G"
    if re.fullmatch(r"[a-z]+\d+[a-z]?", tok):  # a57, x8d, s26, g56, v5
        return tok[0].upper() + tok[1:]
    m = re.fullmatch(r"(\d+)([a-z])", tok)  # 17e, 15t, 15c
    if m:
        return tok if brand == "Apple" else m.group(1) + m.group(2).upper()
    return tok.capitalize()


def plain(text: str) -> str:
    """Lowercase words joined by '-', for web addresses."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def model_name(brand: str, family: str) -> str:
    words = " ".join(_token(t, brand) for t in family.split())
    if brand == "Apple":
        return words if words.lower().startswith(("iphone", "ipad")) else f"iPhone {words}"
    if brand == "Samsung" and not words.lower().startswith(("galaxy", "z ")):
        words = f"Galaxy {words}"
    if brand == "Xiaomi" and words.lower().startswith("redmi"):
        return f"Xiaomi {words}"
    return f"{brand} {words}"


def storage_label(gb: int | None) -> str:
    if not gb:
        return ""
    return f"{gb // 1024}TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb}GB"
