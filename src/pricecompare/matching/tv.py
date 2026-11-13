"""TV titles (Stage 3.2). A TV is compared only by its maker's model code, which names one exact set
(screen size, panel and year): "UA65U8000FUXTW" (Samsung), "65QNED70B6T.AMNE" (LG), "K-65XR80" (Sony), "55P745" (TCL).
Region tails that change by country (UXTW / UXJO, ".AMNE") are cut, so the same set sold in two shops gets one key.
Titles without a code ("Samsung 55-inch Crystal UHD TV") are never compared: many sets share those words.

Family = "tv <size> <code>", e.g. "tv 65 u8000f"; the size in the code must agree with the size the title states.
The size is also kept in the variant's size field (TVs have no storage), so nothing else needs a special case.
"""
from __future__ import annotations

import re

BRANDS = {"samsung": "Samsung", "lg": "LG", "sony": "Sony", "tcl": "TCL", "hisense": "Hisense", "toshiba": "Toshiba",
          "sharp": "Sharp", "chiq": "CHiQ", "skyworth": "Skyworth", "philips": "Philips", "panasonic": "Panasonic",
          "xiaomi": "Xiaomi"}
BRAND = re.compile(r"\b(" + "|".join(BRANDS) + r")\b", re.I)
SAYS_TV = re.compile(r"\b(tv|tvs|television|smart\s?tv|oled|qled|qned|nanocell|mini\s?led|crystal\s?uhd|uhd|4k|8k)\b|تلفزيون|شاشة", re.I)
NOT_A_TV = re.compile(r"\b(stand|mount|bracket|wall\s?mount|remote\s+control|cable|soundbar|sound\s?bar|receiver|projector|box|stick|"
                      r"frame\s+vg|vg-|cover|bezel\s+kit|monitor\s+arm|odyssey|gaming\s+monitor|chromecast\s+with)\b|شاشة\s+(?:ألعاب|العاب)", re.I)
INCH = re.compile(r"(\d{2,3})(?:\.\d)?\s*(?:-?\s*inch(?:es)?|in\b|\"|″|”|''|-?\s*انش|-?\s*بوصة)", re.I)

# Samsung: UA/QA/UE/QE/UN/QN + size + model; the tail "A?UXTW", "AEXTW", "UXJO"... is the region and is cut
SAMSUNG = re.compile(r"\b(?:UA|QA|UE|QE|UN|QN)(\d{2,3})([A-Z]{1,3}\d{1,4}[A-Z0-9]*)\b")
SAMSUNG_TAIL = re.compile(r"A?[UE]X[A-Z]{2,3}$")
LG = re.compile(r"\b(\d{2,3})((?:QNED|NANO|NU|UT|UR|UQ|UP|NA|LX|SM|QN)[A-Z0-9]{2,10})(?:\.[A-Z0-9]+)?\b")
LG_OLED = re.compile(r"\bOLED(\d{2,3})([A-Z]\d[A-Z0-9]{0,6})(?:\.[A-Z0-9]+)?\b")
SONY = re.compile(r"\b(?:K|KD|XR|KE)-?(\d{2,3})([A-Z]{1,3}\d{2,3}[A-Z]?)\b")
CHIQ = re.compile(r"\bU(\d{2,3})([A-Z]{1,3}\d{1,3}[A-Z]?)\b")
GENERIC = re.compile(r"\b(\d{2,3})([A-Z]{1,3}\d{1,4}[A-Z]{0,3})\b")   # TCL 55P745, Hisense 75A61Q, Toshiba 65C350NW


def looks_like_tv(title: str) -> bool:
    return bool(SAYS_TV.search(title) and INCH.search(title) or SAYS_TV.search(title) and BRAND.search(title) and _code(title, None))


def _code(title: str, brand: str | None) -> tuple[int, str] | None:
    t = title.upper()
    b = (brand or "").lower()
    found = None
    if b in ("samsung", ""):
        m = SAMSUNG.search(t)
        if m:
            model = SAMSUNG_TAIL.sub("", m.group(2))
            # the year letter (A 2021 ... F 2025, H 2026) can carry a spare A/B before the region: "Q6FA", "QN85DB" -> "Q6F", "QN85D"
            model = re.sub(r"(?<=\d[A-HJ-N])[AB]$", "", model) if re.search(r"\d[A-HJ-N][AB]$", model) else model
            found = (int(m.group(1)), model)
    if not found and b in ("lg", ""):
        m = LG_OLED.search(t)
        if m:
            found = (int(m.group(1)), "oled" + m.group(2))
        else:
            m = LG.search(t)
            if m:
                found = (int(m.group(1)), m.group(2))
    if not found and b == "sony":
        m = SONY.search(t)
        if m:
            found = (int(m.group(1)), m.group(2))
    if not found and b == "chiq":
        m = CHIQ.search(t)
        if m:
            found = (int(m.group(1)), m.group(2))
    if not found and b in ("tcl", "hisense", "toshiba", "skyworth", "sharp", "philips", "panasonic"):
        for m in GENERIC.finditer(t):
            if m.group(2) in ("HDMI", "USB", "HZ") or m.group(2).startswith(("HDMI", "USB", "HZ", "GB", "W")):
                continue
            found = (int(m.group(1)), m.group(2))
            break
    if not found:
        return None
    size, model = found
    if not 24 <= size <= 120 or not re.search(r"\d", model):
        return None
    return size, model.lower()


def parse(title: str) -> tuple[str, str, int] | None:
    """(brand, family, screen size in inches) for a TV title with a maker model code; None when it cannot be told apart."""
    if NOT_A_TV.search(title):
        return None
    m = BRAND.search(title)
    if not m:
        return None
    brand = BRANDS[m.group(1).lower()]
    code = _code(title, m.group(1))
    if not code:
        return None
    size, model = code
    stated = {int(x) for x in INCH.findall(title)}
    if stated and size not in stated:
        return None                     # the code says 65" but the title says 55": one of them is wrong, never guess
    return brand, f"tv {size} {model}", size


def is_tv_family(family: str) -> bool:
    return family.startswith("tv ")


def pretty(brand: str, family: str) -> str:
    """'Samsung 65" TV U8000F' from ("Samsung", "tv 65 u8000f")."""
    _, size, model = family.split(" ", 2)
    return f'{brand} {size}" TV {model.upper()}'
