"""Turn a shop's product title into comparable fields (brand, family, storage, market...).

Titles are noisy ("Honon X7e 4G, 6GB & 256GB, 6.6Inch, Light Blue - 5109CJKN"), so this only
extracts what the matching rules need: brand, family key, storage, market version, connectivity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import laptop, tablet, tv

BRAND_ALIASES = {
    "apple": "Apple", "iphone": "Apple",
    "samsung": "Samsung",
    "honor": "Honor", "honon": "Honor",
    "xiaomi": "Xiaomi", "redmi": "Xiaomi", "poco": "Xiaomi",
    "infinix": "Infinix", "tecno": "Tecno", "itel": "Itel",
    "motorola": "Motorola", "moto": "Motorola",
    "tcl": "TCL", "huawei": "Huawei", "oppo": "Oppo", "realme": "Realme", "vivo": "Vivo",
    "nokia": "Nokia", "nothing": "Nothing", "oneplus": "OnePlus", "google": "Google", "pixel": "Google",
    "zte": "ZTE", "sony": "Sony", "ipad": "Apple", "lenovo": "Lenovo",
    # smaller makers sold in Jordan (added 2026-11-13 so their phones and tablets are compared too)
    "blackview": "Blackview", "hotwav": "HOTWAV", "hmd": "HMD", "doogee": "Doogee", "oukitel": "Oukitel",
    "ulefone": "Ulefone", "umidigi": "Umidigi",
}
NOT_PHONE = re.compile(
    r"\b(tablet|tab|pad|ipad|watch|buds|airpods|case|cover|charger|cable|adapter|"
    r"protector|earbuds|headphone|speaker|band|macbook|imac|mac\s?mini|mac\s?studio|laptop|chromecast|box|stick|tv|aux|lightning|"
    r"pencil|scale|smarttag|tracker|stylus|dock|stand|strap|lens|gimbal|drone|glasses|earphones?|lamp|plug|fan|scooter|hub|mouse|keyboard|router|printer|monitor|camera|projector|console|playstation|power ?bank)\b", re.I)
DROP_TOKENS = {
    "galaxy", "smartphone", "phone", "mobile", "dual", "card", "sim", "esim", "open", "market",
    "ver", "version", "new", "english", "foldable", "ai", "translator", "global", "indian", "india", "gulf", "international", "official",
}
COLORS = {
    "black", "white", "silver", "gray", "grey", "blue", "green", "red", "gold", "pink", "purple", "violet",
    "orange", "yellow", "titanium", "graphite", "midnight", "starlight", "lavender", "sage", "mist", "natural",
    "desert", "cosmic", "deep", "light", "dark", "glacier", "glacial", "burgundy", "ram", "flagship",
    "premium", "package", "frost", "baby", "night", "sky",
}
RAM_NOISE = re.compile(r"\b\d+\s?ram\b(?!\s?\d+\b(?!\s?[gt]b))|\bram\s?\d+\b(?!\s?[gt]b)", re.I)  # "RAM 8 256GB" yes, "4 GB RAM 128 GB" must keep 128 GB
STORAGE = re.compile(r"(\d+)\s?(gb|tb)\b", re.I)
SPLIT_SUFFIX = re.compile(r"(\d)(pro|max|plus|ultra|lite|fe|se|neo|air|mini|flip|fold)\b")


@dataclass
class ParsedTitle:
    brand: str | None
    family: str  # lowercase tokens, brand removed (brand kept for Apple's "iphone")
    storage_gb: int | None
    ram_gb: int | None
    market_version: str
    connectivity: str
    is_phone: bool
    category: str | None = None  # "phone", "tablet", or None for what we do not compare (accessories, bundles)

    @property
    def is_product(self) -> bool:
        return self.category is not None

    @property
    def family_key(self) -> str:
        return f"{self.brand}:{self.family}" if self.brand else ""

    @property
    def family_key_no_net(self) -> str:
        return re.sub(r"\b[45]g\b", "", self.family_key).replace("  ", " ").strip()


def _storage_ram(text: str) -> tuple[int | None, int | None]:
    vals = [int(n) * (1024 if u.lower() == "tb" else 1) for n, u in STORAGE.findall(text)]
    if not vals:
        return None, None
    if len(vals) == 1:
        return vals[0], None
    return max(vals), min(vals)  # "6GB+6GB RAM 256GB", "8GB & 256GB": storage is the largest size


def _market(text: str) -> str:
    t = text.lower()
    if re.search(r"\bindia(n)?\b", t):
        return "india"
    # "Middle East version" is the normal version sold in Jordan (owner, 2026-11-11), so it is not a foreign one.
    if re.search(r"\b(gulf|ksa|saudi|uae)\b", t):
        return "gulf"
    if re.search(r"\b(global|international)\b", t):
        return "global"
    if re.search(r"\b(jordan|official|agent)\b", t):
        return "jordan"
    return "unknown"


def category_of(family: str) -> str:
    """The category of a catalogue model, read from its name (tablet names always contain ipad/tab/pad/matepad;
    laptop names start with their model line, e.g. "vivobook 15 ...", "macbook air 13 m5")."""
    if tv.is_tv_family(family):
        return "tv"
    if tablet.is_tablet_family(family):
        return "tablet"
    return "laptop" if laptop.is_laptop_family(family) else "phone"


def _parse_tablet(title: str) -> ParsedTitle:
    found = tablet.parse(title, BRAND_ALIASES)
    if found is None:
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)
    brand, family, net = found
    storage, ram = _storage_ram(RAM_NOISE.sub(" ", tablet.strip_expandable(title)))
    if storage is not None and ram is None and storage < 32:
        storage, ram = None, storage  # "MatePad 12 X Green, 8GB": a lone small size is the memory, not the storage
    if tablet.generation_unknown(family):
        storage = None  # cannot tell which iPad it is: treated like a title with no size (shown nowhere, never compared)
    return ParsedTitle(brand, family, storage, ram, _market(title), net, False, "tablet")


TV_WORDS = re.compile(r"\b(tv|tvs|television|smart\s?tv)\b|تلفزيون", re.I)


def _parse_title(title: str) -> ParsedTitle:
    if tv.looks_like_tv(title):
        found = tv.parse(title)
        if found:
            brand, family, size = found  # the screen size sits in the size field: TVs have no storage
            return ParsedTitle(brand, family, size, None, "unknown", "unknown", False, "tv")
        if TV_WORDS.search(title) and not tablet.looks_like_tablet(title) and not laptop.says_laptop(title):
            return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # a TV without its model code
    if laptop.looks_like_laptop(title):
        found = laptop.parse(title)
        if found:
            brand, family, ram, storage = found
            return ParsedTitle(brand, family, storage, ram, "unknown", "unknown", False, "laptop")
        if laptop.says_laptop(title) and not tablet.looks_like_tablet(title):
            return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # a laptop we cannot tell apart
        # otherwise it is read as a phone or tablet ("Snapdragon 8 Elite", "ROG Phone 9" are phones)
    # "A36 8/256" is shop shorthand for 8GB RAM and 256GB storage (Ammar Mobile); only real storage sizes count
    title = re.sub(r"\b(\d{1,2})\s?[/-]\s?(32|64|128|256|512)(?:\s?gb)?\b", r"\1GB \2GB", title, flags=re.I)
    if tablet.looks_like_tablet(title):
        return _parse_tablet(title)
    t = re.sub(r"\([^)]*\)", " ", title)
    # a screen size ("6.9 inch", '6.7"') is not part of the model name
    t = re.sub(r"\b\d{1,2}(?:\.\d{1,2})?\s*(?:-?\s*inch(?:es)?\b|\"|″|”|انش|إنش|بوصة)", " ", t, flags=re.I)
    t = re.sub(r"\bsmart\s?phone\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", RAM_NOISE.sub(" ", t)).strip()  # "4 RAM", "RAM 8" are not part of the model
    head = t
    for cut in (r",", r" - ", r" [–—] ", r" \| ", STORAGE.pattern):
        m = re.search(cut, head, re.I)
        if m:
            head = head[: m.start()]
    head = re.sub(r"\be-?sim\b", " ", head, flags=re.I)  # connectivity, not part of the model name
    head = head.replace("+", " plus ")
    head = re.sub(r"([A-Za-z]{3,})(\d)", r"\1 \2", head)  # "play20a" -> "play 20a", "reno16" -> "reno 16"
    tokens = re.findall(r"[a-z0-9]+", head.lower())
    brand = None
    for tok in tokens:
        if tok in BRAND_ALIASES:
            brand = BRAND_ALIASES[tok]
            break
    kept = []
    for tok in tokens:
        if tok in COLORS or tok in DROP_TOKENS or re.fullmatch(r"\d+(mah|hz|mp|w|inch)", tok):
            continue
        if BRAND_ALIASES.get(tok) and tok != "iphone" and tok not in ("redmi", "poco", "pixel"):
            continue
        kept.append(tok)
    merged: list[str] = []
    for tok in kept:
        if tok == "e" and merged and merged[-1][-1:].isdigit():
            merged[-1] += "e"  # "iPhone 16 E" -> "16e"
        elif merged and merged[-1] == tok and not tok.isdigit():
            continue  # "Pova 7 Pova 7"
        else:
            merged.append(tok)
    family = SPLIT_SUFFIX.sub(r"\1 \2", " ".join(merged))
    family = re.sub(r"^iphone 17 air$", "iphone air", family)  # Action's name for the iPhone Air
    storage, ram = _storage_ram(RAM_NOISE.sub(" ", title))  # parentheses may hold "(12GB RAM, 256GB Storage)"
    esim = bool(re.search(r"e-?sim", t, re.I))
    is_phone = not NOT_PHONE.search(head) and bool(tokens) and tokens[0] in BRAND_ALIASES
    return ParsedTitle(
        brand=brand,
        family=family.strip(),
        storage_gb=storage,
        ram_gb=ram,
        market_version=_market(t),
        connectivity="esim_only" if esim else "unknown",
        is_phone=is_phone,
        category="phone" if is_phone else None,
    )


BIG_SCREEN = re.compile(r"(\d{1,2}(?:\.\d)?)\s*(?:-?\s*inch(?:es)?|in\b|\"|″|”|انش|إنش|بوصة)", re.I)


def parse_title(title: str) -> ParsedTitle:
    import dataclasses

    p = _parse_title(title)
    if p.category in ("phone", "tablet") and p.storage_gb:
        if p.storage_gb < 16:
            # "Nova Y90 6GB" (Platinum): a size under 16GB on a current phone is its memory, not its storage
            p = dataclasses.replace(p, storage_gb=None, ram_gb=p.ram_gb or p.storage_gb)
        elif p.storage_gb in (1000, 2000):
            p = dataclasses.replace(p, storage_gb=p.storage_gb // 1000 * 1024)   # "1000GB" written for 1TB
    if p.category == "phone" and any(8.0 <= float(x) <= 20 for x in BIG_SCREEN.findall(title)):
        # a "phone" with an 8-inch or bigger screen is a tablet we cannot name yet (Blackview Link 8, 12.7"): never filed as a phone
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)
    return p
