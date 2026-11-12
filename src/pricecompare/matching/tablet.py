"""Reading tablet titles. Shops write them very differently:

    "11-inch iPad Air M3 - Purple / 256GB / Wi-Fi+Cellular"                          (eStoreJO)
    "Apple iPad Air 11\" (M4 Chip), 8-Core CPU, ..., 128GB Storage, Wi-Fi 7 + 5G Cellular"   (GTS)
    "HONOR Pad X8b (2026) 11.0\" Android WIFI Tablet (128GB Storage / 4GB + 4GB Memory)"     (City Center)

Two tablets are the same product only when model, storage and Wi-Fi/cellular all agree, and for an iPad also the
screen size and the chip (an iPad Air 11 M3 and M4 are different products with different prices). When a title leaves
one of these out, the name it gets is shorter and simply does not meet the others: no guess is made.
Cases, keyboards and pens are not tablets, and a paid bundle ("+ cover and pen") is not the bare tablet.
"""
from __future__ import annotations

import re

TABLET_WORD = re.compile(r"\b(ipad|matepad|tab|pad|tablets?)\b", re.I)
_ACCESSORY = re.compile(r"\b(for|case|cases|cover|protector|keyboard|pencil|sleeve|stand|charger|folio|glass|holder|"
                        r"graphics|drawing|pen display|handheld|bag|adapter|cable)\b", re.I)
_BUNDLE = re.compile(r"(\+|\bwith\b|\band\b|&)\s*(a |free )?(cover|keyboard|pencil|pen\b|case|accessor|gift|bundle)", re.I)
_SIZE = r"(\d{1,2}(?:\.\d{1,2})?)\s*(?:-\s*)?(?:inch(?:es)?\b|in\b|\"|'')"
_DROP = {"galaxy", "tablet", "tablets", "wifi", "wi", "fi", "lte", "4g", "5g", "cellular", "android", "new", "the", "with",
         "edition", "version", "global", "sim", "dual", "only", "and", "or", "ai"}
_COLORS = {"black", "white", "silver", "gray", "grey", "blue", "green", "red", "gold", "pink", "purple", "yellow",
           "space", "starlight", "titanium", "natural", "lavender", "mint", "sage", "cloud", "deep", "mist", "nebula"}


def looks_like_tablet(title: str) -> bool:
    return bool(TABLET_WORD.search(title))


def is_tablet_family(family: str) -> bool:
    """Tablet model names always carry one of these words, so the category can be read back from the name."""
    return bool(re.search(r"\b(ipad|matepad|tab|pad)\b", family))


def generation_unknown(family: str) -> bool:
    """An iPad title that names neither its chip nor its generation ("iPad mini Wi-Fi 128GB", "iPad Air 11-inch").
    Shops sell two generations side by side at very different prices, so such a title cannot be compared with anything:
    two shops that both leave the chip out may still be selling different iPads."""
    if not family.startswith("ipad"):
        return False
    return not re.search(r"\b[am]\d{1,2}\b", family) and not re.fullmatch(r"ipad \d{1,2}", family)


def _clean(title: str) -> str:
    t = re.sub(r"\bmate pad\b", "MatePad", title, flags=re.I)  # SmartBuy writes "Mate Pad"
    t = t.replace("‑", "-").replace("–", "-").replace("—", "-").replace("″", '"').replace("”", '"').replace("’’", '"')
    return re.sub(r"\s+", " ", t).strip()


def connectivity(text: str) -> str:
    """Cellular when the title says so; otherwise Wi-Fi (shops always state a SIM version: it costs more)."""
    low = re.sub(r"2\.4\s?g(hz)?|\b5\s?ghz", " ", text.lower())  # Wi-Fi bands, not mobile networks
    if re.search(r"\b(cellular|lte)\b", low) or re.search(r"(?<![\d./])\b[45]g\b(?!\s*wi-?fi)", low):
        return "cellular"
    return "wifi"


def strip_expandable(text: str) -> str:
    """ "64GB ROM 1TB Expandable" has 64GB of storage, not 1TB."""
    t = re.sub(r"(expand(able)?( up)? to|up to)\s*\d+\s?(gb|tb)", " ", text, flags=re.I)
    return re.sub(r"\d+\s?(gb|tb)\s*(expand\w*|micro ?sd)", " ", t, flags=re.I)


def _ipad_family(low: str) -> str:
    line = next(l for l in ("ipad pro", "ipad air", "ipad mini", "ipad") if l in low)
    size = re.search(_SIZE, low)
    size = size.group(1).removesuffix(".0") if size else None
    chip = re.search(r"\b([am]\d{1,2})\b(?!\s?(gb|tb|-?inch|\"))", low)
    chip = chip.group(1) if chip else None
    gen = re.search(r"\bipad (\d{1,2})(?:th)?\b(?!\s*(?:-\s*)?(?:inch|in\b|\"|''|\.\d))", low)
    if line == "ipad" and chip == "a16" and not size:
        size = "11"  # the A16 iPad is made in one size only
    parts = [line] + ([size] if size and line != "ipad mini" else []) + ([chip] if chip else ([gen.group(1)] if gen and line == "ipad" else []))
    return " ".join(parts)


def _other_family(low: str, brand_words: set[str]) -> str:
    low = re.sub(r"\b\d+\s?ram\b|\bram\s?\d+\b", " ", low)                          # "4 RAM", "Ram 4"
    low = re.sub(r"\b((?:ipad|matepad|tab|pad)\b.*?)\btablets?\b.*", r"\1", low)    # nothing after "... Tablet" is the name
    head = low
    for cut in (r"\s?-\s", r",", r"\(", r"\d+\s?(gb|tb)\b", r"\b\d{1,2}\s?\+\s?\d{2,4}\b"):
        m = re.search(cut, head)
        if m:
            head = head[: m.start()]
    head = re.sub(r"\bpaper ?matte\b", "papermatte", head)
    head = re.sub(r"\bmatepad (\d{1,2}(?:\.\d)?)\s*(?:\"|'')", r"matepad \1 ", head)   # Huawei names it by size: keep it
    head = re.sub(r"(?<!matepad )" + _SIZE, " ", head)                                  # everyone else: size is a detail
    head = head.replace("+", " plus ")
    head = re.sub(r"\b(\d{1,2}) x\b", r"\1x", head)                                     # "MatePad 12 X" = "12X"
    out: list[str] = []
    for tok in re.findall(r"[a-z0-9.]+", head):
        tok = tok.strip(".")
        if not tok or tok in _DROP or tok in _COLORS or tok in brand_words or re.fullmatch(r"20\d\d|\d+(\.\d+)?k|\d+hz", tok):
            continue
        if re.fullmatch(r"\d{1,2}\.\d{1,2}", tok) and (not out or out[-1] != "matepad"):
            continue  # a bare screen size ("Redmi Pad 2 9.7"); only Huawei names a tablet by its size
        if tok not in out:
            out.append(tok)
    fam = " ".join(out)
    return re.sub(r"\bmatepad se \d{1,2}\b", "matepad se", fam)  # "MatePad SE 11": only one size is sold


def parse(title: str, brand_aliases: dict[str, str]) -> tuple[str | None, str, str] | None:
    """(brand, family, connectivity) for a tablet title, or None when it is an accessory, a bundle or an unknown make."""
    t = _clean(title)
    low = t.lower()
    word = TABLET_WORD.search(low)
    if not word or _ACCESSORY.search(low[: word.start()]) or re.search(r"\b(graphics|drawing|pen display)\b", low):
        return None
    # A tablet sold together with a keyboard or pen is a different product at a different price. A free gift
    # ("+ Free HONOR Cover", "Cover Included") is the shop's promotion on the same tablet, so that one stays.
    paid_bundle = _BUNDLE.search(low.replace("s pen", "")) or re.search(r"\bbundle\b", low)
    if paid_bundle and not re.search(r"\b(free|gift|included)\b", low):
        return None
    brand = next((brand_aliases[w] for w in re.findall(r"[a-z]+", low) if w in brand_aliases), None)
    if brand is None:
        return None
    if "ipad" in low:
        return "Apple", _ipad_family(low), connectivity(low)
    family = _other_family(low, {w for w in brand_aliases if w not in ("redmi", "poco")})
    if not is_tablet_family(family):
        return None
    return brand, family, connectivity(low)
