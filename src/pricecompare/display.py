"""Human-friendly names for the app (the database keeps lowercase matching keys)."""
from __future__ import annotations

import re

BRAND_AR = {
    "Apple": "آبل", "Samsung": "سامسونج", "Xiaomi": "شاومي", "Honor": "هونر", "Huawei": "هواوي", "Infinix": "إنفينيكس",
    "Motorola": "موتورولا", "Oppo": "أوبو", "Realme": "ريلمي", "Tecno": "تكنو", "Nokia": "نوكيا", "TCL": "تي سي إل",
    "Itel": "آيتيل", "Vivo": "فيفو", "Google": "جوجل", "OnePlus": "ون بلس", "Nothing": "ناثينج", "ZTE": "زد تي إي", "Sony": "سوني",
    # laptop makers (Stage 3)
    "Asus": "أسوس", "Lenovo": "لينوفو", "HP": "إتش بي", "Dell": "ديل", "Acer": "أيسر", "MSI": "إم إس آي",
    "Microsoft": "مايكروسوفت", "Gigabyte": "جيجابايت", "Razer": "ريزر",
    "Blackview": "بلاك فيو", "HOTWAV": "هوتواف", "HMD": "إتش إم دي", "Doogee": "دوجي", "Oukitel": "أوكيتل",
    "Ulefone": "يولفون", "Umidigi": "يوميديجي",
    # TV makers (Stage 3.2)
    "LG": "إل جي", "Hisense": "هايسنس", "Toshiba": "توشيبا", "Sharp": "شارب", "CHiQ": "تشيك", "Skyworth": "سكاي ورث",
    "Philips": "فيليبس", "Panasonic": "باناسونيك",
}
# Categories visitors can see. A new category is collected and matched first, then switched on here after the owner's
# hand check of 50 matches and 20 prices (plan Stage 3). Until then it shows only on the owner's admin dashboard.
LIVE_CATEGORIES = ("phone", "tablet", "laptop", "tv")
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


# Arabic spellings people type in Jordan, for Arabic page titles and answers ("سعر آيفون 17" is what is searched,
# not "سعر iPhone 17"). Words not listed (model numbers like A57, S26, 5G) stay as they are.
AR_DISPLAY = {
    "iphone": "آيفون", "ipad": "آيباد", "macbook": "ماك بوك", "galaxy": "جالكسي", "redmi": "ريدمي", "note": "نوت",
    "pro": "برو", "max": "ماكس", "plus": "بلس", "ultra": "ألترا", "mini": "ميني", "lite": "لايت", "air": "إير",
    "fold": "فولد", "flip": "فليب", "z": "زد", "magic": "ماجيك", "pad": "باد", "tab": "تاب", "matepad": "ميت باد",
    "reno": "رينو", "edge": "إيدج", "fusion": "فيوجن", "nova": "نوفا", "pura": "بيورا", "hot": "هوت", "smart": "سمارت",
    "spark": "سبارك", "camon": "كامون", "play": "بلاي", "neo": "نيو", "tv": "شاشة", "go": "جو", "choice": "تشويس",
    "duo": "ديو", "moto": "موتو", "vivobook": "فيفوبوك", "zenbook": "زين بوك", "tuf": "تاف", "rog": "روج", "strix": "ستريكس",
    "zephyrus": "زيفيروس", "ideapad": "آيديا باد", "thinkpad": "ثينك باد", "legion": "ليجن", "yoga": "يوجا",
    "pavilion": "بافيليون", "victus": "فيكتوس", "omen": "أومن", "nitro": "نيترو", "aspire": "أسباير",
}


def arabic_name(name: str, brand: str) -> str | None:
    """'آيفون 17 برو ماكس' for 'iPhone 17 Pro Max'; None when nothing in the name has an Arabic spelling."""
    words, changed = [], False
    for w in name.split():
        lw = w.lower().strip('"')
        if lw == brand.lower() and brand in BRAND_AR:
            words.append(BRAND_AR[brand])
            changed = True
        elif lw in AR_DISPLAY:
            words.append(AR_DISPLAY[lw])
            changed = True
        else:
            words.append(w)
    return " ".join(words) if changed else None
