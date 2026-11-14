"""Smartwatches and fitness bands (Stage 3, first category of the 2026-11-14 order).

A watch is told apart by maker + line ("Series 12", "Galaxy Watch 8 Classic", "GT 6 Pro", "Redmi Watch 5 Active"),
case size in mm (kept in the size field, like a TV's screen size) and GPS or Cellular (kept as the connectivity).
Lines sold in one size only (Huawei Fit and Band, Redmi Watch, Xiaomi Smart Band...) get size 0 = "one size".
Only well-known makers: the many no-name watches carry no model a second shop would write the same way.
Never guessed: an Apple Watch SE without its generation, a multi-size line without its mm, two sizes in one title.
"""
from __future__ import annotations

import re

BRANDS = {"apple": "Apple", "samsung": "Samsung", "huawei": "Huawei", "xiaomi": "Xiaomi", "redmi": "Xiaomi",
          "honor": "Honor", "google": "Google", "fitbit": "Google", "amazfit": "Amazfit", "garmin": "Garmin",
          "oppo": "Oppo", "realme": "Realme", "oneplus": "OnePlus"}
BRAND = re.compile(r"\b(" + "|".join(BRANDS) + r")\b", re.I)
SAYS_WATCH = re.compile(r"\b(watch\w*|smart\s?watch|smartband|smart\s?band|fitness\s?band|band\s?\d+)\b|ساعة|واتش", re.I)
# accessories sold in the same sections: straps, chargers, cases, screen films
NOT_A_WATCH = re.compile(r"\b(strap|straps|bracelet\s+for|charger|charging|cable|dock|stand|case\s+for|cover|protector|film|"
                         r"glass|for\s+(?:apple\s+)?watch|for\s+galaxy\s+watch|compatible|replacement|loop\s+only|band\s+only|"
                         r"watch\s+band\b(?!\s*\d)|watch\s+strap|kids?|children|child)\b", re.I)
MM = re.compile(r"(?<!\d)(3[8-9]|4[0-9]|50)\s*(?:mm|ملم|مم)\b", re.I)
CELLULAR = re.compile(r"\b(cellular|lte|4g|e-?sim)\b", re.I)
CUT = re.compile(r",|\s[-–—|]\s|\(|\s[–—]|/|\bwith\b|\bfor\b", re.I)
STOP = {"gps", "cellular", "lte", "bt", "bluetooth", "smartwatch", "smart", "and", "aluminium", "aluminum", "titanium",
        "stainless", "steel", "case", "sport", "loop", "milanese", "alpine", "trail", "ocean", "link", "amoled", "display",
        "hd", "inch", "chip", "fitness", "tracker", "mm", "new", "original", "global", "version", "black", "white",
        "silver", "gold", "grey", "gray", "blue", "green", "pink", "red", "midnight", "starlight", "natural", "rose",
        "graphite", "brown", "purple", "orange", "yellow", "beige", "cream", "jet", "space", "light", "dark", "olive",
        "lavender", "violet", "matte", "sage", "dawn", "night", "sky", "teal", "mint", "burgundy", "bronze", "esim",
        "standard", "edition", "premium", "ceramic", "leather", "silicone", "nylon", "screenless", "activity"}
WORDS = {"watch", "watches", "galaxy"}
# lines sold in two or more case sizes: the mm must be in the title
MULTI_SIZE = {"Apple": re.compile(r"^(series|se)\b"), "Samsung": re.compile(r"^galaxy (\d|ultra|classic)"),
              "Huawei": re.compile(r"^(gt|\d)\b"), "Xiaomi": re.compile(r"^s\d")}
WATCH_BRANDS = {"amazfit", "fitbit", "garmin"}                            # everything they sell here is a watch
WATCH_LINE = re.compile(r"\b(fit\s?\d+|band\s?\d*|choice\s+band)\b", re.I)
ULTRA_MM = 49


def looks_like_watch(title: str) -> bool:
    m = BRAND.search(title)
    if not m or NOT_A_WATCH.search(_head(title)):            # accessories say so up front: "Charger for Apple Watch"
        return False
    word = m.group(1).lower()
    return bool(SAYS_WATCH.search(title) or re.search(r"\b(" + "|".join(WATCH_BRANDS) + r")\b", title, re.I) or WATCH_LINE.search(title)
                or word == "huawei" and re.search(r"\bgt\s?\d", title, re.I))


def _head(title: str) -> str:
    title = re.sub(r"\((\d)(?:st|nd|rd|th)\s+gen\w*\)", r" \1 ", title, flags=re.I)   # "SE (3rd Gen)" -> "SE 3"
    return CUT.split(title)[0]


def _line(title: str, brand_word: str) -> str | None:
    head = MM.sub(" ", _head(title))
    head = re.sub(r"\d+\.\d+", " ", head)                                   # "1.82 inch"
    head = re.sub(r"\b(\d)(?:st|nd|rd|th)\s+gen(?:eration)?\b", r"\1", head, flags=re.I)
    head = re.sub(r"([A-Za-z]{2,})(\d)", r"\1 \2", head)                    # "GT6" -> "GT 6", "Watch8" -> "Watch 8"
    head = re.sub(r"(\d)(pro|max|plus|ultra|lite|active)\b", r"\1 \2", head, flags=re.I)   # "Fit 5Pro" -> "Fit 5 Pro"
    head = re.sub(r"\bchoice\s+band\b", "choice-band", head, flags=re.I)
    tokens = [x.replace("choice-band", "choice band") for x in re.findall(r"[a-z0-9+]+(?:-band)?", head.lower())]
    if brand_word.lower() not in tokens:
        return None
    tokens = tokens[tokens.index(brand_word.lower()) + 1:]
    out: list[str] = ["redmi"] if brand_word.lower() == "redmi" else []
    for tok in tokens:
        if tok in ("galaxy", "redmi", "fitbit"):
            out.append(tok)
            continue
        if tok in BRANDS or tok in WORDS:
            continue
        if tok in STOP:
            if not out or out in (["redmi"], ["galaxy"]):
                continue                                                    # "Redmi Smart Watch 5": leading words
            break
        if tok == "band" and out:
            break                                                           # "Sport Band" after the line name
        out.append(tok.replace("+", " plus").strip())
        if len(out) >= 4:
            break
    line = " ".join(out).strip()
    if not line or not re.search(r"\d", line) and len(line.split()) < 2:
        return None                                                         # "Smart Band", "Choice": which one?
    return line


def parse(title: str) -> tuple[str, str, int, str] | None:
    """(brand, family, case size in mm or 0 for one-size lines, "gps"|"cellular") or None when it cannot be told apart."""
    if not looks_like_watch(title):
        return None
    m = BRAND.search(title)
    brand_word = m.group(1)
    brand = BRANDS[brand_word.lower()]
    if brand_word.lower() == "fitbit":
        brand_word = "fitbit"
    line = _line(title, brand_word)
    if not line:
        return None
    if brand == "Apple":
        if line == "se":
            return None                                                     # SE 2 or SE 3? never guess
        if not re.match(r"^(series \d+|se \d|ultra(?: \d)?)$", line):
            return None
    sizes = {int(x) for x in MM.findall(title)}
    if len(sizes) > 1:
        return None
    size = sizes.pop() if sizes else None
    if line.startswith("ultra") and brand == "Apple":
        size = size or ULTRA_MM
    if size is None:
        if brand in MULTI_SIZE and MULTI_SIZE[brand].match(line):
            return None                                                     # two or more case sizes exist: need the mm
        size = 0
    net = "cellular" if CELLULAR.search(title) or (brand == "Apple" and line.startswith("ultra")) else "gps"
    return brand, f"watch {line}", size, net


def is_watch_family(family: str) -> bool:
    return family.startswith("watch ")


def pretty(brand: str, family: str) -> str:
    """'Apple Watch Series 12', 'Samsung Galaxy Watch 8 Classic', 'Huawei Band 11 Pro', 'Xiaomi Redmi Watch 5 Active'."""
    words = family.split()[1:]

    def cap(w: str) -> str:
        if w in ("se", "gt", "qcy") or re.fullmatch(r"[a-z]\d+[a-z]*|\d+[a-z]+", w):
            return w.upper()
        return w.capitalize()
    rest = lambda ws: " ".join(cap(w) for w in ws)
    if words[:2] == ["galaxy", "fit"]:
        return f"{brand} Galaxy Fit {rest(words[2:])}".strip()
    if words and words[0] in ("galaxy", "redmi"):
        return f"{brand} {words[0].capitalize()} Watch {rest(words[1:])}".strip()
    if words and words[0] in ("band", "fitbit") or brand in ("Amazfit", "Garmin"):
        return f"{brand} {rest(words)}".strip()
    return f"{brand} Watch {rest(words)}".strip()


def size_label(mm: int | None) -> str:
    return f"{mm}mm" if mm else ""
