"""Laptop titles -> comparable fields (Stage 3, first new category).

A laptop is only compared when we can read ALL of: brand, model line, the exact processor, RAM and storage.
The graphics card (RTX/GTX/RX) and the screen size join the key whenever the title states them, so two laptops
that differ in either are never merged. Anything vaguer ("ASUS Laptop TUF Gaming A18", "Lenovo Core i7 Laptop")
is not compared at all: leaving a laptop out is better than matching it wrongly.

MacBooks: model (Air/Pro/Neo) + screen size + chip (M1..M5; Pro/Max chips also need their CPU core count, because
the 15-core and 18-core M5 Pro with the same memory are different machines) + RAM + storage.
iMac, Mac mini, Mac Studio, desktops, workstations, monitors and accessories are not laptops.

Stored without any database structure change: family = "<line> <cpu> [gpu] [size]", storage_gb = storage,
ram_gb = RAM (always set for laptops, so 8GB and 16GB versions are separate products).
"""
from __future__ import annotations

import re

# model line word -> brand (the line alone is enough to know the brand)
LINES = {
    "vivobook": "Asus", "zenbook": "Asus", "expertbook": "Asus", "proart": "Asus", "rog": "Asus", "tuf": "Asus",
    "ideapad": "Lenovo", "thinkpad": "Lenovo", "thinkbook": "Lenovo", "legion": "Lenovo", "loq": "Lenovo", "yoga": "Lenovo",
    "victus": "HP", "omen": "HP", "omnibook": "HP", "pavilion": "HP", "elitebook": "HP", "probook": "HP", "envy": "HP",
    "spectre": "HP",
    "inspiron": "Dell", "vostro": "Dell", "latitude": "Dell", "xps": "Dell", "alienware": "Dell",
    "aspire": "Acer", "nitro": "Acer", "swift": "Acer", "predator": "Acer", "travelmate": "Acer",
    "katana": "MSI", "cyborg": "MSI", "stealth": "MSI", "raider": "MSI", "prestige": "MSI", "sword": "MSI",
    "matebook": "Huawei", "magicbook": "Honor", "redmibook": "Xiaomi", "galaxybook": "Samsung", "inbook": "Infinix",
    "macbook": "Apple",
}
BRANDS = {"hp": "HP", "dell": "Dell", "lenovo": "Lenovo", "asus": "Asus", "acer": "Acer", "msi": "MSI", "apple": "Apple",
          "huawei": "Huawei", "honor": "Honor", "xiaomi": "Xiaomi", "samsung": "Samsung", "microsoft": "Microsoft",
          "gigabyte": "Gigabyte", "razer": "Razer", "infinix": "Infinix"}
# shop shorthand -> the words the makers use
SHORTHAND = [(r"\bips\s?3\b", "ideapad slim 3"), (r"\bips\s?5\b", "ideapad slim 5"), (r"\blegpro\s?(\d)\b", r"legion pro \1"),
             (r"\bvivo\s+book\b", "vivobook"), (r"\bidiapad\b", "ideapad"), (r"\bgalaxy\s*book", "galaxybook"),
             (r"\bzen\s+book\b", "zenbook"), (r"\bnotbook\b", "notebook")]
LAPTOP_WORD = re.compile(r"\b(laptop|notebook|macbook|galaxybook|surface\s*laptop|chromebook|" + "|".join(LINES) + r")\b", re.I)
NOT_LAPTOP = re.compile(r"\b(imac|mac\s*mini|mac\s*studio|desktop|all[\s-]*in[\s-]*one|aio|tower|monitor|pc\s*case|"
                        r"workstation|gaming\s*pc|surface\s*pro|tablet)\b", re.I)
DASH = r"[\s\-‑–]*"
W = r"[^\w\n]{0,4}"   # "Core™ 7", "Ryzen™ 7": a trademark sign or punctuation between words
CPU_PATTERNS = [
    (re.compile(rf"\bryzen{W}ai{W}max{W}\+?{W}(\d{{3}})\b", re.I), lambda m: f"ryzen-ai-max-{m[1]}"),
    (re.compile(rf"\bryzen{W}ai{W}([579]){W}(?:hx{W})?(?:pro{W})?(\d{{3}})\b", re.I), lambda m: f"ryzen-ai-{m[1]}-{m[2]}"),
    (re.compile(rf"\bryzen{W}([3579]){W}(?:pro{W})?{DASH}(\d{{3,4}}[a-z]{{0,2}})\b", re.I), lambda m: f"ryzen{m[1]}-{m[2].lower()}"),
    (re.compile(rf"\b(?:core{W}|intel{W})?ultra{W}([3579]){DASH}(?:processor{W})?(\d{{3}}[a-z]{{0,2}})\b", re.I),
     lambda m: f"ultra{m[1]}-{m[2].lower()}"),
    (re.compile(rf"\b(?:core{W})?i([3579]){DASH}n(\d{{3}})\b", re.I), lambda m: f"i{m[1]}-n{m[2]}"),
    (re.compile(rf"\b(?:core{W})?i([3579]){DASH}(\d{{4,5}}[a-z]{{0,2}})\b", re.I), lambda m: f"i{m[1]}-{m[2].lower()}"),
    (re.compile(rf"\bcore{W}([3579]){DASH}(?:processor{W})?(\d{{3}}[a-z]{{0,2}})\b", re.I), lambda m: f"core{m[1]}-{m[2].lower()}"),
    (re.compile(rf"\b(?:celeron|pentium|intel){W}(?:processor{W})?n{W}(\d{{3,4}})\b", re.I), lambda m: f"n{m[1]}"),
    (re.compile(r"\bsnapdragon\s*x\s*(?:elite|plus)?\s*\(?\s*(x1[ep])\s*-?\s*(\d{2})\s*-?\s*(\d{3})", re.I),
     lambda m: f"snapdragon-{m[1].lower()}-{m[2]}-{m[3]}"),
]
GPU = re.compile(rf"\b(?:geforce{W})?(rtx|gtx){W}(\d{{4}})\s*(ti\b)?|\bradeon\s*rx\s*(\d{{4}}[ms]?)\b", re.I)
VRAM = re.compile(rf"\b\d{{1,2}}\s*gb\s*(?:of\s*)?(?:gddr\d+x?|vram|graphics|ddr6)\b|(?:rtx|gtx|rx){W}\d{{4}}\s*(?:ti\s*)?"
                  rf"(?:laptop\s*gpu\s*)?\s*\d{{1,2}}\s*gb\b", re.I)   # "RTX 5060 8GB"; not "RTX 3060, 16GB DDR4" (that is RAM)
SIZE = re.compile(r"(?<![\d.])(1[1-8](?:\.\d)?)\s*(?:\"|″|''|”|-?\s*inch|in\b)", re.I)
APPLE_SIZE = re.compile(r"(?<![\d.])(13|14|15|16)(?:\.\d)?\s*(?:\"|″|''|”|-?\s*inch)", re.I)
APPLE_CHIP = re.compile(r"\b(m[1-5])(?:\s*(pro|max))?\b|\b(a18)\s*pro\b", re.I)
APPLE_CPU_CORES = re.compile(r"(\d{1,2})\s*[\-‑\s]?\s*core\s*cpu", re.I)
MEM = re.compile(r"(\d{1,4})\s*(gb|tb|g)\b", re.I)
RAM_SIZES = {4, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96}
LINE_FOLLOWERS = {"slim", "pro", "plus", "air", "go", "flip", "duo", "strix", "zephyrus", "flow", "scar", "lite", "x", "s", "neo",
                  "ultra", "max", "omen"}


def normalize(title: str) -> str:
    t = title
    for pat, rep in SHORTHAND:
        t = re.sub(pat, rep, t, flags=re.I)
    return t


EXPLICIT = re.compile(r"\b(laptop|notebook|macbook)\b", re.I)


def says_laptop(title: str) -> bool:
    """The title itself says it is a laptop (not only a line name like "ROG", which Asus also uses for phones)."""
    return bool(EXPLICIT.search(normalize(title)))


def looks_like_laptop(title: str) -> bool:
    t = normalize(title)
    return bool(LAPTOP_WORD.search(t)) and not NOT_LAPTOP.search(t)


def cpu_of(title: str) -> str | None:
    for pat, fmt in CPU_PATTERNS:
        m = pat.search(title)
        if m:
            return fmt(m)
    return None


def gpu_of(title: str) -> str | None:
    m = GPU.search(title)
    if not m:
        return None
    if m[4]:
        return f"rx{m[4].lower()}"
    return f"{m[1].lower()}{m[2]}{'ti' if m[3] else ''}"


def ram_storage(title: str) -> tuple[int | None, int | None]:
    t = VRAM.sub(" ", title)                                                            # the graphics card's memory is not RAM
    t = re.sub(r"\b(\d{1,2})\s*/\s*(\d{3,4})\s*(gb)?\b", r"\1GB \2GB", t, flags=re.I)  # "16/512GB"
    t = re.sub(r"\b(\d{1,2})\s*/\s*(\d)\s*tb\b", r"\1GB \2TB", t, flags=re.I)          # "16/1TB"
    t = re.sub(r"\b(\d{1,2})\s*ram\b", r"\1GB ram", t, flags=re.I)                    # "8 RAM"
    ram, storage = None, None
    for n, unit in MEM.findall(t):
        unit = unit.lower()
        v = int(n) * (1024 if unit == "tb" else 1)
        if unit == "gb" and int(n) in RAM_SIZES and ram is None:
            ram = int(n)
        elif v >= 128 and (storage is None or v > storage):
            storage = v
    return ram, storage


def _line(t: str) -> str | None:
    """The model line: the first line word, plus up to two short series words or numbers right after it."""
    words = re.findall(r"[a-z0-9]+", t.lower())
    for i, w in enumerate(words):
        if w in LINES:
            extra = []
            for x in words[i + 1:i + 5]:
                if x in ("laptop", "notebook") or (x == "gaming" and w != "ideapad"):
                    continue                                       # "TUF Gaming Laptop A15" is the TUF A15
                if x in LINE_FOLLOWERS or x == "gaming" or re.fullmatch(r"\d{1,2}[a-z]?|[a-z]\d{1,2}[a-z]?", x):
                    extra.append(x)
                    if len(extra) == 2:
                        break
                else:
                    break
            return " ".join([w, *extra])
    m = re.search(r"\b(dell|hp)\s+(pro\s+)?(1[3-7])\b", t, re.I)    # "Dell Pro 15", "Dell 15", "HP 15-fd0133wm"
    if m:
        return f"{m[1].lower()} {'pro ' if m[2] else ''}{m[3]}"
    m = re.search(r"\bhp\s+elite\s*(\d{1,2})\b", t, re.I)           # "HP Elite 14" ("Elite" alone is also a phone chip)
    if m:
        return f"hp elite {m[1]}"
    m = re.search(r"\basus\s+(v1[4-6])\b", t, re.I)                 # "ASUS V16"
    return m[1].lower() if m else None


def _apple(t: str):
    low = t.lower()
    chip = APPLE_CHIP.search(t)
    if "neo" in low:
        model = "macbook neo"
    elif "air" in low:
        model = "macbook air"
    elif re.search(r"macbook\s*pro\b", low):
        model = "macbook pro"
    else:
        return None
    if chip is None and model != "macbook neo":
        return None
    chip_s = "a18-pro" if (chip is None or chip[3]) else chip[1].lower() + (f"-{chip[2].lower()}" if chip[2] else "")
    if chip_s.endswith(("-pro", "-max")) and chip_s != "a18-pro":
        cores = APPLE_CPU_CORES.search(t)
        if not cores:
            return None                                             # an M5 Pro comes as 15-core or 18-core: must say which
        chip_s += f"-{cores[1]}c"
    size = APPLE_SIZE.search(t)
    if model == "macbook neo":
        size_s = "13"
    elif size:
        size_s = size[1]
    else:
        return None                                                 # Air 13 and Air 15 are different laptops
    ram, storage = ram_storage(t)
    if not ram or not storage:
        return None
    return "Apple", f"{model} {size_s} {chip_s}", ram, storage


def parse(title: str):
    """(brand, family, ram_gb, storage_gb), or None when the laptop cannot be told apart from others."""
    t = normalize(title)
    if not (LAPTOP_WORD.search(t) and not NOT_LAPTOP.search(t)):
        return None
    if "macbook" in t.lower():
        return _apple(t)
    cpu = cpu_of(t)
    if cpu is None:
        return None
    words = re.findall(r"[a-z0-9]+", t.lower())
    brand = next((BRANDS[w] for w in words if w in BRANDS), None) or next((LINES[w] for w in words if w in LINES), None)
    line = _line(t)
    if brand is None or line is None:
        return None
    ram, storage = ram_storage(t)
    if not ram or not storage:
        return None
    gpu = gpu_of(t)
    size = SIZE.search(t)
    res = resolution_of(t)
    parts = [line, cpu] + ([gpu] if gpu else []) + ([re.sub(r"\.0$", "", size[1])] if size else []) + ([res] if res else [])
    return brand, " ".join(parts), ram, storage


RESOLUTIONS = [(re.compile(r"\b(4k|uhd|3840\s*x\s*2400|3840\s*x\s*2160)\b", re.I), "4k"),
               (re.compile(r"\b(3k|2\.8k|2\.9k|2880\s*x\s*1800|3200\s*x\s*2000)\b", re.I), "3k"),
               (re.compile(r"\b(2\.5k|qhd|wqxga|2560\s*x\s*1600|2560\s*x\s*1440)\b", re.I), "2.5k"),
               (re.compile(r"\b(fhd\+?|full\s*hd|wuxga|1920\s*x\s*1200|1920\s*x\s*1080)(?=\W|$)", re.I), "fhd")]


def resolution_of(title: str) -> str | None:
    """The screen resolution when the title states one: a 4K and a 3K screen are different laptops (ProArt P16)."""
    for pat, name in RESOLUTIONS:
        if pat.search(title):
            return name
    return None


def is_laptop_family(family: str) -> bool:
    first = family.split(" ", 1)[0] if family else ""
    return first in LINES or bool(re.match(r"(dell|hp) (pro |elite )?1[3-7] |v1[4-6] ", family))


# ---- names for people ------------------------------------------------------------------------------------------
_PRETTY = {"rog": "ROG", "tuf": "TUF", "loq": "LOQ", "xps": "XPS", "hp": "HP", "dell": "Dell", "macbook": "MacBook",
           "ideapad": "IdeaPad", "thinkpad": "ThinkPad", "thinkbook": "ThinkBook", "vivobook": "Vivobook", "zenbook": "Zenbook",
           "expertbook": "ExpertBook", "proart": "ProArt", "omnibook": "OmniBook", "elitebook": "EliteBook", "probook": "ProBook",
           "matebook": "MateBook", "magicbook": "MagicBook", "redmibook": "RedmiBook", "galaxybook": "Galaxy Book", "inbook": "InBook"}
CPU_START = re.compile(r"(ryzen|ultra\d|i[3579]-|core\d|n\d{3}|snapdragon|m[1-5]\b|m[1-5]-|a18)")


def _pretty_cpu(c: str) -> str:
    if c.startswith("ultra"):
        return "Core Ultra " + c[5] + " " + c.split("-", 1)[1].upper()
    if re.match(r"i[3579]-", c):
        return "Core " + c[:2] + "-" + c.split("-", 1)[1].upper()
    if c.startswith("core"):
        return "Core " + c[4] + " " + c.split("-", 1)[1].upper()
    if c.startswith("ryzen-ai-max"):
        return "Ryzen AI Max+ " + c.rsplit("-", 1)[1]
    if c.startswith("ryzen-ai"):
        _, _, tier, num = c.split("-")
        return f"Ryzen AI {tier} {num}"
    if c.startswith("ryzen"):
        return "Ryzen " + c[5] + " " + c.split("-", 1)[1].upper()
    if c.startswith("snapdragon"):
        return "Snapdragon X " + "-".join(c.split("-")[1:]).upper()
    if re.fullmatch(r"n\d+", c):
        return "Intel " + c.upper()
    if c == "a18-pro":
        return "A18 Pro"
    m = re.fullmatch(r"(m[1-5])(?:-(pro|max))?(?:-(\d+)c)?", c)          # m5-pro-15c -> M5 Pro 15-core
    if m:
        return m[1].upper() + (f" {m[2].capitalize()}" if m[2] else "") + (f" {m[3]}-core" if m[3] else "")
    return c


def pretty(brand: str, family: str) -> str:
    """'tuf a16 ryzen7-7445hs rtx4050 16' -> 'Asus TUF A16 Ryzen 7 7445HS RTX 4050 16"'."""
    words = family.split()
    cpu_at = next((k for k, w in enumerate(words) if CPU_START.match(w)), len(words))
    head = []
    for w in words[:cpu_at]:
        head.append(_PRETTY.get(w, w.upper() if re.fullmatch(r"[a-z]\d+[a-z]?", w) else w.capitalize()))
    if brand == "Apple" and head and head[-1].isdigit():
        head[-1] += '"'                                                    # MacBook Air 13"
    tail = []
    if cpu_at < len(words):
        tail.append(_pretty_cpu(words[cpu_at]))
        for w in words[cpu_at + 1:]:
            if re.fullmatch(r"(rtx|gtx)\d{4}(ti)?", w):
                tail.append(w[:3].upper() + " " + w[3:7] + (" Ti" if w.endswith("ti") else ""))
            elif w.startswith("rx"):
                tail.append("RX " + w[2:].upper())
            elif w in ("4k", "3k", "2.5k"):
                tail.append(w.upper())
            elif w == "fhd":
                tail.append("FHD")
            else:
                tail.append(w + '"')
    name = " ".join(head + tail)
    return name if brand == "Apple" else f"{brand} {name}"
