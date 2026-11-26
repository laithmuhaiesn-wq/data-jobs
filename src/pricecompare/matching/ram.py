"""RAM sticks (owner 2026-11-26: "add the ram category and be very careful with it").

A stick (or a kit of sticks) is one product only when ALL of these agree: maker, the maker's line (Fury Beast, Vengeance,
Trident Z5 ...), DDR type, total size and how it is split (2x16GB is not 1x32GB), speed, CL when the title gives it,
RGB or not, the AMD EXPO version, and desktop (DIMM) or laptop (SO-DIMM). Colour (black/white) is the same product.
A title missing the DDR type, the speed or the size, or with a word we do not know (maybe another line), is not shown:
two different sticks are never put together on a guess.
"""
from __future__ import annotations

import re

# maker spelling in titles -> maker name (HyperX before Kingston: "Kingston HyperX Fury" is HyperX's Fury)
BRANDS = [(r"hyper[\s-]?x", "HyperX"), (r"kingston", "Kingston"), (r"corsair", "Corsair"),
          (r"g\.?\s?skill|skill(?=\s+(?:trident|ripjaws|flare|aegis))", "G.Skill"),
          (r"crucial", "Crucial"), (r"adata|xpg", "ADATA"), (r"lexar", "Lexar"), (r"team\s?group|t-?force", "TeamGroup"),
          (r"patriot", "Patriot"), (r"silicon\s?power", "Silicon Power"), (r"apacer", "Apacer"), (r"pny", "PNY"),
          (r"v-?color", "V-Color"), (r"addlink", "Addlink"), (r"samsung", "Samsung"), (r"transcend", "Transcend"),
          (r"netac", "Netac"), (r"kingspec", "KingSpec"), (r"klevv", "Klevv"), (r"gigabyte|aorus", "Gigabyte")]
_BRAND = [(re.compile(r"(?<![\w.])(?:" + p + r")(?![\w])", re.I), b) for p, b in BRANDS]

# the maker's lines, longest first; the words are taken out of the title once found
LINES = {
    "Kingston": ["fury renegade", "fury beast", "fury impact", "fury"],
    "HyperX": ["fury", "predator", "impact"],
    "Corsair": ["dominator titanium", "dominator platinum", "vengeance lpx", "vengeance pro sl", "vengeance pro", "vengeance rs",
                "vengeance"],
    "G.Skill": ["trident z5 neo", "trident z5 royal", "trident z5", "trident z royal", "trident z neo", "trident z",
                "ripjaws m5", "ripjaws s5", "ripjaws v", "ripjaws", "flare x5", "aegis"],
    "Crucial": ["ballistix tactical tracer", "ballistix sport lt", "ballistix", "pro"],
    "ADATA": ["spectrix d41", "spectrix d35", "spectrix d45", "spectrix d50", "spectrix d60", "spectrix d80", "hunter", "premier pro", "lancer neon", "lancer blade", "lancer", "caster", "gammix d\\d\\d"],
    "Lexar": ["ares", "thor", "hades"],
    "TeamGroup": ["delta", "night hawk", "vulcan z", "vulcan", "xtreem", "elite plus", "elite"],
    "Patriot": ["viper elite 5", "viper steel", "viper venom", "viper", "signature premium", "signature line"],
    "Silicon Power": ["xpower zenith", "xpower turbine", "zenith", "turbine"],
    "Gigabyte": ["aorus"], "PNY": ["xlr8"], "V-Color": ["xsky", "manta", "prism"], "Apacer": ["nox", "panther"], "Addlink": ["spark"],
}
# makers that sell no plain stick: a title without the line could be any of them
NEEDS_LINE = {"G.Skill", "Corsair", "HyperX", "TeamGroup", "Patriot", "V-Color", "PNY"}
ALIAS = {"zenith": "xpower zenith", "turbine": "xpower turbine"}

DDR = re.compile(r"(?<![a-z])ddr\s?([345])(l)?(?![0-9])", re.I)
SPEEDS = {1066, 1333, 1600, 1866, 2133, 2400, 2666, 2800, 2933, 3000, 3200, 3333, 3466, 3600, 3733, 4000, 4133, 4400, 4800, 5200,
          5600, 6000, 6200, 6400, 6600, 6800, 7000, 7200, 7600, 8000, 8200, 8400}
SIZES = {2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128}
KIT = [re.compile(r"(?<![\d.])([1248])\s*[x×*]\s*(\d{1,3})\s*g(?:b)?(?![a-z])", re.I),             # 2x16GB, 2 x 16GB, 1x16GB
       re.compile(r"(?<![\d.])(\d{1,3})\s*gb?\s*[x×*]\s*([1248])(?![\d])", re.I),                    # 16GBx2, 16gb x2
       re.compile(r"(?<![\d.])([1248])\s*[x×*]\s*(\d{1,2})(?![\d.]|\s*(?:mhz|mt|gb?\b))", re.I)]     # "16gb 2x8", "1x16 Beast"
GB = re.compile(r"(?<![\d.])(\d{1,3})\s*g(?:b)?(?![a-z])", re.I)
CL = re.compile(r"(?<![a-z0-9])c(?:l)?\s?-?\s?(\d{2})(?![\d])", re.I)
RGB = re.compile(r"\brgb\b", re.I)
NO_RGB = re.compile(r"\bnon[\s-]?rgb\b", re.I)
LAPTOP = re.compile(r"\bso-?ddr|\bs(?:o)?-?dimm\b|\blaptop\b|\bnotebook\b|\bnb\b", re.I)   # "S-DIMM (NB)": a laptop stick

# a title with one of these is something else that only names its memory: a board, a card, a drive, a computer, a cable
NOT_RAM = re.compile(
    r"\b([abhxz]\d{3}[a-z]?|mother\s?board|main\s?board|chipset|lga\s?\d{4}|am[45]\b|graphics?|gpu|geforce|radeon|rtx|gtx|gt\s?\d{3,4}|vga|"
    r"ssd|nvme|m\.2|hdd|hard\s?(?:disk|drive)|\d+(?:\.\d)?\s*tb\b|flash|usb|micro\s?sd|sd\s?card|"
    r"core\s*i\d|i[3579]-\d{3,5}|ryzen|celeron|pentium|processor|cpu|"
    r"desktop\s+pc|tower|twr|sff|all[\s-]*in[\s-]*one|mini\s?pc|optiplex|thinkcentre|prodesk|nas|diskstation|"
    r"cable|cat\s?\d|ethernet|phone|tablet|keyboard|mouse|monitor|heatsink|cooler|fan|enclosure|adapter|server|ecc\s+registered|"
    r"rdimm|lrdimm|registered|ecc|refurb\w*|used|open\s?box)\b", re.I)
NON_ECC = re.compile(r"\bnon[\s-]?ecc\b", re.I)

# words that say what a stick is or how it is sold, never which one
GENERIC = {"ram", "memory", "memories", "desktop", "laptop", "notebook", "pc", "computer", "gaming", "kit", "single", "dual", "channel",
           "dimm", "udimm", "u", "so", "sodimm", "unbuffered", "non", "ecc", "for", "with", "and", "rgb", "black", "white", "grey", "gray",
           "silver", "red", "mhz", "mt", "s", "gb", "g", "cl", "c", "v", "pin", "rank", "rx", "x", "sdram", "dram", "module", "modules",
           "stick", "sticks", "xmp", "expo", "intel", "amd", "low", "voltage", "profile", "heat", "spreader", "heatspreader",
           "lighting", "light", "led", "argb", "the", "in", "of", "series", "edition", "new", "original", "speed", "high", "performance",
           "overclocking", "oc", "valueram", "value", "kvr", "kcp", "client", "premier", "gbit", "lp", "pc4", "pc5", "pc3", "gold",
           "style", "nb", "dimm", "sdimm", "drive", "ddr4l", "liquid", "cooled", "cooling",
           "ddr", "ddr3", "ddr4", "ddr5", "ddr3l", "only", "a", "w", "hmz", "mts"}


def brand_of(title: str) -> str | None:
    found = [(m.start(), b) for rx, b in _BRAND for m in [rx.search(title)] if m]
    if not found:
        return None
    names = {b for _, b in found}
    if names == {"HyperX", "Kingston"}:
        return "HyperX"
    if names == {"ADATA", "TeamGroup"} or len(names) > 1:
        return None                                    # two makers named: never guessed
    return found[0][1]


def is_ram(title: str) -> bool:
    """A memory stick or kit on its own (not a computer, board or card that names its memory)."""
    if not DDR.search(title) or NOT_RAM.search(NON_ECC.sub(" ", title)):
        return False
    return brand_of(title) is not None and bool(re.search(r"(?<![a-z])(ram|memory|s?dimm|udimm|so-?dimm|mhz|mt/?s|kit|pc[345])\b|ddr[345]l?[\s-]*\d{4}\b|\bfor\s+(?:pc|desktop|laptop)\b", title, re.I))


def parse(title: str) -> tuple[str, str, int] | None:
    """(brand, family, total GB) or None when the stick cannot be told apart for sure."""
    if not is_ram(title):
        return None
    brand = brand_of(title)
    t = " " + title.lower().replace("–", " ").replace("—", " ") + " "
    t = re.sub(r"\bnon[\s-]?rgb\b", " ", t)
    rgb = bool(RGB.search(title)) and not NO_RGB.search(title)
    ddrs = {(m.group(1), m.group(2) or "") for m in DDR.finditer(title)}
    if len(ddrs) != 1:
        return None
    gen, low = ddrs.pop()
    ddr = f"ddr{gen}{low.lower()}"
    # speed: a known DDR speed written as a number of its own ("3200MHz", "DDR4-3200", "6000MT/s-CL36", "2133 DDR4")
    nums = {int(n) for n in re.findall(r"(?<![\d.])(\d{4})(?![\d.])", t)}
    speeds = nums & SPEEDS
    if len(speeds) != 1:
        return None
    speed = speeds.pop()
    # size and split
    kits = {(int(b), int(a)) if i == 1 else (int(a), int(b)) for i, rx in enumerate(KIT) for a, b in rx.findall(t)}
    kits = {(n, per) for n, per in kits if per in SIZES}
    sizes = {int(n) for n in GB.findall(re.sub(r"\d+\s*gbit\b|\d+g\s*x\s*\d+\b", " ", t)) if int(n) in SIZES}
    if len(kits) > 1:
        return None
    if kits:
        n, per = kits.pop()
        total = n * per
        if sizes - {total, per}:
            return None                                # "32GB (2x8GB)": the title says two things
    else:
        if len(sizes) != 1:
            return None
        n, per, total = 1, sizes.pop(), 0
        total = per
    cls = {int(c) for c in CL.findall(t) if 10 <= int(c) <= 60}
    if len(cls) > 1:
        return None
    cl = cls.pop() if cls else None
    # the maker's line
    line = ""
    for ln in LINES.get(brand, []):
        m = re.search(r"(?<![a-z0-9])" + ln.replace(" ", r"[\s-]*(?:rgb[\s-]*)?") + r"(?![a-z0-9])", t)
        if m:
            line = ALIAS.get(ln, m.group(0).strip() if "\\" in ln else ln)
            t = t[:m.start()] + " " + t[m.end():]
            break
    if brand == "Kingston" and line == "fury" and (m := re.search(r"\b(beast|renegade|impact)\b", t)):
        line = f"fury {m.group(1)}"                     # "Kingston FURY 16GB 3200MHz DDR4 RGB 1x16 Beast"
        t = re.sub(r"\b(?:fury|" + m.group(1) + r")\b", " ", t)
    if brand == "Kingston" and not line and re.search(r"\bkcp\d", t):
        line = "kcp"                                    # Kingston's Client Premier (KCP...) line is not its ValueRAM (KVR...)
    line = re.sub(r"\s+", " ", line.replace("-", " "))
    # every word left must be one we know: an unknown word may be another line (keep apart, do not guess)
    rest = DDR.sub(" ", t)
    for rx, _ in _BRAND:
        rest = rx.sub(" ", rest)
    rest = re.sub(r"\bt-?force\b|\bxpg\b|\bhyper[\s-]?x\b|\bkingston\b|\bskill\b|\bsp\b(?=\s+silicon)", " ", rest)
    rest = re.sub(r"\b[a-z]{2,4}\d{2}[a-z0-9/-]{4,}\b", " ", rest)          # maker codes: KVR32N22S6/8, KF432C16BB/8
    for rx in KIT:
        rest = rx.sub(" ", rest)
    rest = GB.sub(" ", rest)
    rest = re.sub(r"\d+rx\d+|\d+-?pin|\d+(?:\.\d+)?\s*v\b|\d+gbit|\d+g\s*x\s*\d+|\(\s*\d\s*x\s*\d+\s*gb?\s*\)", " ", rest)
    words = [w for w in re.findall(r"[a-z][a-z+]*", re.sub(r"[^a-z0-9+ ]", " ", rest)) if w not in GENERIC]
    if words:
        return None
    if not line and brand in NEEDS_LINE:
        return None                                    # "G.SKILL 32GB (2x16GB) 6000MHz": Trident, Ripjaws or Flare? never guessed
    if brand == "Kingston" and line == "fury" and gen == "5":
        return None                                    # Kingston's DDR5 FURY is always Beast or Renegade: which one?
    fam = ["ram"] + ([line] if line else []) + [ddr, str(speed)] + ([f"cl{cl}"] if cl else []) + [f"{total}gb"]
    if n > 1:
        fam.append(f"{n}x{per}")
    if rgb:
        fam.append("rgb")
    if re.search(r"\bexpo\b", t):
        fam.append("expo")
    if LAPTOP.search(title):
        fam.append("sodimm")
    return brand, " ".join(fam), total


def pretty(brand: str, words: list[str]) -> str:
    """'Kingston Fury Beast RGB 32GB (2x16GB) DDR5 6000MHz CL36', '... Laptop (SO-DIMM)'."""
    line, spec, total, kit, extra = [], [], "", "", []
    for w in words:
        if re.fullmatch(r"ddr\d l?|ddr\dl?", w):
            spec.append(w.upper().replace("DDR3L", "DDR3L"))
        elif re.fullmatch(r"\d{4}", w):
            spec.append(f"{w}MHz")
        elif re.fullmatch(r"cl\d+", w):
            spec.append(w.upper())
        elif re.fullmatch(r"\d+gb", w):
            total = w.upper()
        elif re.fullmatch(r"\dx\d+", w):
            kit = f" ({w}GB)"
        elif w == "rgb":
            extra.insert(0, "RGB")
        elif w == "expo":
            extra.append("EXPO")
        elif w == "sodimm":
            extra.append("Laptop (SO-DIMM)")
        else:
            line.append(w)
    up = {"kcp": "KCP", "sl": "SL", "rs": "RS", "lt": "LT", "lpx": "LPX", "xlr8": "XLR8", "z5": "Z5", "m5": "M5", "s5": "S5", "v": "V", "x5": "X5", "z": "Z"}
    name = " ".join(up.get(w, w.upper() if re.fullmatch(r"d\d\d", w) else w.capitalize()) for w in " ".join(line).split())
    rgb = ["RGB"] if "RGB" in extra else []
    rest = [e for e in extra if e != "RGB"]
    return " ".join(p for p in [brand, name] + rgb + [total + kit] + spec + rest if p)
