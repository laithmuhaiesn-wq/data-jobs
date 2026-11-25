"""Turn a shop's product title into comparable fields (brand, family, storage, market...).

Titles are noisy ("Honon X7e 4G, 6GB & 256GB, 6.6Inch, Light Blue - 5109CJKN"), so this only
extracts what the matching rules need: brand, family key, storage, market version, connectivity.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import gadget, laptop, tablet, tv, watch

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
    "ulefone": "Ulefone", "umidigi": "Umidigi", "nubia": "Nubia", "gtab": "G-Tab", "teclast": "Teclast", "vikusha": "Vikusha",
}
NOT_PHONE = re.compile(
    r"\b(tablet|tab|pad|ipad|watch|buds|airpods|case|cover|charger|cable|adapter|"
    r"protector|earbuds|headphone|speaker|band|macbook|imac|mac\s?mini|mac\s?studio|laptop|chromecast|box|stick|tv|aux|lightning|"
    r"pencil|scale|smarttag|tracker|stylus|dock|stand|strap|lens|desktop|tower|twr|sff|ssf|aio|thinkcentre|pcie|fibre|fiber|thinksystem|transceiver|sfp|server|gimbal|drone|glasses|earphones?|lamp|plug|fan|scooter|hub|mouse|keyboard|router|printer|monitor|camera|projector|console|playstation|power ?bank)\b", re.I)
DROP_TOKENS = {
    "galaxy", "smartphone", "phone", "mobile", "dual", "card", "sim", "esim", "open", "market",
    "ver", "version", "new", "english", "foldable", "ai", "translator", "amoled", "oled", "lcd", "global", "indian", "india", "gulf", "international", "official",
}
COLORS = {
    "black", "white", "silver", "gray", "grey", "blue", "green", "red", "gold", "pink", "purple", "violet",
    "orange", "yellow", "titanium", "graphite", "midnight", "starlight", "lavender", "sage", "mist", "natural",
    "desert", "cosmic", "deep", "light", "dark", "glacier", "glacial", "burgundy", "ram", "flagship",
    "premium", "package", "frost", "baby", "night", "sky", "ice", "nebula", "pantone", "bronze",
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


# "4128gb", "8256gb", "12512gb": RAM and storage written together with no space (BCI, 2026-11-19); a real size is
# never like that, so it is read as "4gb 128gb"
GLUED = re.compile(r"\b(\d{1,2})(64|128|256|512)\s?gb\b", re.I)


def _storage_ram(text: str) -> tuple[int | None, int | None]:
    text = re.sub(r"(\d)(gb|tb)(?=\d)", r"\1\2 ", text, flags=re.I)        # "4gb128gb" = "4gb 128gb" (2026-11-21)
    text = GLUED.sub(lambda m: f"{m.group(1)}gb {m.group(2)}gb" if int(m.group(1)) in (2, 3, 4, 6, 8, 12, 16, 24) else m.group(0), text)
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
    if watch.is_watch_family(family):
        return "watch"
    if gadget.is_gadget_family(family):
        return gadget.category_of(family)
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


WATCH_OR_TV = re.compile(r"\b(watch|tv|television)\b|ساعة|تلفزيون", re.I)   # "heart-rate monitor" on a watch, a TV's speakers


def _parse_title(title: str) -> ParsedTitle:
    kind = gadget.category(title)
    # a tablet's pen or keyboard names the tablet ("Magic Keyboard for iPad Pro 13"): it is still the accessory
    if kind and (kind in ("console", "router") or kind == "speaker" and re.search(r"\bsound\s?bar\b", title, re.I) or not WATCH_OR_TV.search(title)) and not laptop.says_laptop(title) and (kind == "tabletacc" or not tablet.looks_like_tablet(title)):
        found = gadget.parse(title)
        if found:
            cat, brand, family, size, ram = found  # the size field: screen inches, capacity GB, mAh (0 = one version)
            return ParsedTitle(brand, family, size, ram, "unknown", "unknown", False, cat)
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # Stage 3 electronics we cannot tell apart
    if tv.looks_like_tv(title):
        found = tv.parse(title)
        if found:
            brand, family, size = found  # the screen size sits in the size field: TVs have no storage
            return ParsedTitle(brand, family, size, None, "unknown", "unknown", False, "tv")
        if TV_WORDS.search(title) and not tablet.looks_like_tablet(title) and not laptop.says_laptop(title):
            return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # a TV without its model code
    if watch.looks_like_watch(title):
        found = watch.parse(title)
        if found:
            brand, family, size, net = found  # the case size sits in the size field (0 = one size)
            return ParsedTitle(brand, family, size, None, "unknown", net, False, "watch")
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # a watch we cannot tell apart
    if laptop.looks_like_laptop(title):
        found = laptop.parse(title)
        if found:
            brand, family, ram, storage = found
            return ParsedTitle(brand, family, storage, ram, "unknown", "unknown", False, "laptop")
        if laptop.says_laptop(title) and not tablet.looks_like_tablet(title):
            return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)  # a laptop we cannot tell apart
        # otherwise it is read as a phone or tablet ("Snapdragon 8 Elite", "ROG Phone 9" are phones)
    # "A36 8/256" is shop shorthand for 8GB RAM and 256GB storage (Ammar Mobile); only real storage sizes count
    # ("iPhone 16 - 128gb" is the model number and a dash, not 16GB RAM: a spaced dash never counts)
    title = re.sub(r"\b(\d{1,2})(?:\s?/\s?|-)(32|64|128|256|512)(?:\s?gb)?\b", r"\1GB \2GB", title, flags=re.I)
    if tablet.looks_like_tablet(title):
        return _parse_tablet(title)
    t = re.sub(r"\([^)]*\)", " ", title)
    # a screen size ("6.9 inch", '6.7"') is not part of the model name
    t = re.sub(r"\b\d{1,2}(?:\.\d{1,2})?\s*(?:-?\s*inch(?:es)?\b|\"|″|”|انش|إنش|بوصة)", " ", t, flags=re.I)
    t = re.sub(r"\bsmart\s?phone\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", RAM_NOISE.sub(" ", t)).strip()  # "4 RAM", "RAM 8" are not part of the model
    # "Apple - iPhone 18 Pro 256GB": the dash after the maker is not the end of the name (2026-11-23)
    m = re.match(r"([A-Za-z]+)\s+[-–—]\s+", t)
    if m and m.group(1).lower() in BRAND_ALIASES:
        t = m.group(1) + " " + t[m.end():]
    head = t
    for cut in (r",", r" - ", r" [–—] ", r"\|", STORAGE.pattern):
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
    # "Galaxy A37 5G - black 8gb 128gb" (Al-Aryan): Samsung's line name without the maker
    galaxy = brand is None and len(tokens) > 1 and tokens[0] == "galaxy" and bool(re.fullmatch(r"[asmf]\d{1,3}[a-z]*|z|note", tokens[1]))
    if galaxy:
        brand = "Samsung"
    is_phone = not NOT_PHONE.search(head) and bool(tokens) and (tokens[0] in BRAND_ALIASES or galaxy)
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


STORAGE_SIZES = {None, 16, 32, 64, 128, 256, 512, 1024, 2048}
# Samsung's own model codes written as names (GTS: "Samsung A055", "A256"): the name people know
SAMSUNG_CODES = {"a055": "A05", "a057": "A05s", "a065": "A06", "a155": "A15", "a156": "A15 5G", "a165": "A16 4G",
                 "a166": "A16 5G", "a256": "A25 5G", "a266": "A26 5G", "a366": "A36 5G", "a566": "A56 5G"}


_GLUED_BRAND = re.compile(r"(?<=[0-9a-z])(%s)(?=[\s\-–])" % "|".join(sorted(
    {"Samsung", "Apple", "Xiaomi", "Huawei", "Honor", "Lenovo", "Asus", "Acer", "Dell", "HP", "LG", "Sony", "Logitech",
     "Razer", "SteelSeries", "HyperX", "MSI", "Gigabyte", "Anker", "JBL", "Oppo", "Realme", "Infinix", "Tecno", "Redmi",
     "Philips", "Toshiba", "Lexar", "Kingston", "Corsair", "AOC", "BenQ", "ViewSonic"}, key=len, reverse=True)))


def _cut_glued_second_title(title: str) -> str:
    """A shop page that glued the next product's name onto this one ("... G60SD – S27DG602Samsung ViewFinity S6 ...
    S27D606", PC Circle 2026-11-17): cut at the second brand name that starts inside a word, so the listing is read
    as its own product and not joined with the other one."""
    m = _GLUED_BRAND.search(title)
    if m and m.start() > 15:
        return title[:m.start()].strip(" –-")
    return title


# Action Mobile lists its smart-home goods in Arabic: "تابو C100 كاميرا للآمان المنزلي" is the Tapo C100 camera (2026-11-25)
_ARABIC = [(r"^(?:تي بي\s*-?\s*لينك\s+)?تابو", "Tapo"), (r"^يوفي", "eufy"), (r"^شاومي", "Xiaomi"), (r"^يوني فيو", "Uniview"),
           (r"ملحق\S*|بطارية بديلة|حقيبة غبار|منظف", " accessory for "), (r"(?:مكنسة\s+)?(?:كهربائية\s+)?رو?بو?و?ت(?:ية)?(?:\s+(?:المكنسة|مكنسة|تنظيف|فاكيوم))*", " robot vacuum "),
           (r"سولو كام", " SoloCam "), (r"كاميرا(?:ت\S*)?|كام(?=\s)", " camera "), (r"برو\b", " Pro "), (r"ماكس\b", " Max "), (r"بلس\b", " Plus "), (r"[اأ]ومني", " Omni "), (r"جرس", " doorbell "), (r"قفل", " smart lock "), (r"ميزان", " smart scale ")]


def _arabic_title(title: str) -> str:
    t = re.sub(r"\s+", " ", title.strip())
    if not re.match(r"(?:تي بي\s*-?\s*لينك\s+)?تابو|يوفي|شاومي|يوني فيو", t):
        return title
    if not re.search(r"كامير|كام\s|رو?بو?و?ت|جرس|قفل|ميزان", t):
        return title                                   # an air purifier, a fryer: not one of our categories
    for pat, to in _ARABIC:
        t = re.sub(pat, to, t)
    return re.sub(r"\s+", " ", re.sub(r"\bEU\b|[؀-ۿ]+", " ", t)).strip()


def _samsung_stock_code(m: re.Match) -> str:
    """The stock code is dropped; what it says about the network stays (SM-A165 is the A16 4G, SM-A266 the A26 5G)."""
    net = re.search(r" [45]G$", SAMSUNG_CODES.get(m.group(1).lower(), ""))
    return (net.group(0) if net and not re.search(r"\b[45]g\b", m.string, re.I) else "") + " "


def parse_title(title: str) -> ParsedTitle:
    import dataclasses

    title = _cut_glued_second_title(title)
    title = re.sub(r"\b(samsung(?:\s+galaxy)?\s+)(a\d{3})\b", lambda m: m.group(1) + SAMSUNG_CODES.get(m.group(2).lower(), m.group(2)),
                   title, flags=re.I)
    title = re.sub(r"^\s*mobile\s+(?=(?:samsung|apple|iphone|xiaomi|redmi|honor|oppo)\b)", "", title, flags=re.I)   # "Mobile Samsung A16-SM-..."
    # makers' codes beside a full model name: "Oppo A5 CPH2727 APAC", "Samsung A26-SM-A266BZKIMEA" (2026-11-24)
    title = re.sub(r"(?<=\w)\s+CPH\s?\d{4}\b(?:\s+APAC\b)?", " ", title, flags=re.I)
    title = re.sub(r"(?<=\w)[\s-]+SM-([A-Z]\d{3})[A-Z0-9]{5,}\b", _samsung_stock_code, title)
    title = re.sub(r"\b(reno\s*\d{1,2})\s+f\b", r"\1F", title, flags=re.I)              # "Reno 15 F" and "Reno15F" are one phone
    title = re.sub(r"\b(spark\s+go)(\d)\b", r"\1 \2", title, flags=re.I)                 # "Spark Go3" = "Spark Go 3"

    # memory written "RAM 8", "8 RAM", "6RAM" (Leaders, Darwish) reads like "8GB RAM"
    title = re.sub(r"\bram\s*(\d{1,2})\b(?!\s*(?:gb|tb))", r"\1GB RAM", title, flags=re.I)
    title = re.sub(r"\b(\d{1,2})\s*ram\b", r"\1GB RAM", title, flags=re.I)
    title = re.sub(r"\bblack\s+view\b", "Blackview", title, flags=re.I)           # "Black view Tab 60" (SmartBuy)
    title = re.sub(r"\s[–—](?=\S)", " – ", title)                                   # "17T Pro –Leica Camera" (iService)
    title = re.sub(r"\b(\d{1,2})g\s+(\d{2,4})g\b", r"\1GB RAM \2GB", title, flags=re.I)  # "Tablet,8g 256g" (GTS)
    title = re.sub(r"\b(\d{1,2})\s*\+\s*\d{1,2}\s*gb\b", r"\1GB RAM", title, flags=re.I)  # "8+8GB/256GB": real + virtual memory
    title = re.sub(r"\bbundle\s+with\s+(?:a\s+)?cover\b|\+\s*cover(?:\s+and\s+pen)?\b", " ", title, flags=re.I)  # a gift in the box
    title = re.sub(r"\b\d(?:\.\d)?k\s+display\b|\bdisplay\b", " ", title, flags=re.I)   # "11\" 2.5K Display WiFi Tablet"
    title = re.sub(r"\bx\d{4}\b", " ", title, flags=re.I)                           # "Note 60 Pro X6878": the maker's stock code
    title = re.sub(r"\bandroid\s*\d{1,2}(?:\.\d)?\b", " ", title, flags=re.I)       # "Android 14": the system, not the model
    # "128GB Expandable up to 2TB": the size it can grow to with a memory card is not its storage
    title = re.sub(r"\b(?:expand\w*|exp\.?|extendable)\s*(?:up\s*to\s*)?\d+\s*(?:gb|tb)\b", " ", title, flags=re.I)
    title = re.sub(r"\b(?:up\s*to\s*)?\d+\s*(?:gb|tb)\s*(?:exp\w*|extended|micro\s?sd)\b", " ", title, flags=re.I)  # "1TB Exp": a memory card
    title = re.sub(r"\bplay\s?sta(?:iton|ion|toin)\b|\bplastation\b", "PlayStation", title, flags=re.I)   # "PLAYSTAITON PORTAL" (Number One 2026-11-25)
    title = re.sub(r"^\s*(?=(?:imac|mac\s?mini|mac\s?studio)\b)", "Apple ", title, flags=re.I)        # Al-Aryan leaves out the maker
    title = re.sub(r"^\s*(?=(?:camon|pova)\s*(?:\d|curve|slim))", "Tecno ", title, flags=re.I)
    title = re.sub(r"^\s*soundcore\s+by\s+anker\W+", "Anker Soundcore ", title, flags=re.I)
    if re.search(r"\b(?:geforce|radeon)\b", title, re.I):
        title = re.sub(r"[™®]", " ", re.sub(r"^\s*ASU\s", "ASUS ", title))
        if re.search(r"\b(?:geforce|radeon)\b.*\b\d{1,2}\s*GB?\b", title.split(" | ")[0], re.I):
            title = title.split(" | ")[0]                                                             # Prof. PC adds the whole description
        title = re.sub(r"\b(?:dual|triple)\s+fan\b(?=.*graphics?\s+card|.*\bgpu\b)", " ", title, flags=re.I)                          # "GeForce RTX™ 5060" (Prof. PC, 2026-11-25)
    # tablets named without the word: "DOOGEE T30 Ultra 256GB", "Blackview ZENO 5 11\"", "VIKUSHA Tablet VZ-30 Pro"
    title = re.sub(r"^\s*(doogee|teclast|vikusha)\s+(?:tablet\s+)?(?!tab\b)(?=(?:[TURAP]|VZ?-[A-Z]?)\d)", r"\1 Tab ", title, flags=re.I)
    title = re.sub(r"^\s*(blackview)\s+(?=(?:zeno|mega|active)\s+\d)", r"\1 Tab ", title, flags=re.I)
    if re.match(r"\s*(?:blackview|doogee|teclast|vikusha)\s+tab\b", title, re.I):
        title = re.sub(r"\b\d{4,5}\s?mAh\b|\brugged\b", " ", title, flags=re.I)
    title = re.sub(r"\bM650\s+L\b", "M650L", title)                                               # Logitech's large M650
    if re.match(r"\s*[؀-ۿ]", title):
        title = _arabic_title(title)
    if re.search(r"\bg[\s-]tab\b", title, re.I):
        title = re.sub(r"\bg[\s-]tab\s+(?!tab\b|pad)", "Gtab Tab ", title, flags=re.I)                    # G-Tab "P9", "MEGA13"
        title = re.sub(r"\bg[\s-]tab\b", "Gtab", title, flags=re.I)
        title = re.sub(r"\b(tab|pad|mega)\s?(\d)", r"\1 \2", title, flags=re.I)
    title = re.sub(r"^\s*OS-(?=Baseus\b)", "", title)                                              # Rokon's own prefix
    if " | " in title and re.search(r"\b(?:play\s?station\s*5|ps5|xbox\s+series)\b.*\bconsole\b", title.split(" | ")[0], re.I):
        title = title.split(" | ")[0]                                                                 # Prof. PC adds the whole description
    p = _parse_title(title)
    if p.category in ("phone", "tablet") and p.storage_gb:
        if p.storage_gb < 16:
            # "Nova Y90 6GB" (Platinum): a size under 16GB on a current phone is its memory, not its storage
            p = dataclasses.replace(p, storage_gb=None, ram_gb=p.ram_gb or p.storage_gb)
        elif p.storage_gb in (1000, 2000):
            p = dataclasses.replace(p, storage_gb=p.storage_gb // 1000 * 1024)   # "1000GB" written for 1TB
        if p.storage_gb not in STORAGE_SIZES:
            p = dataclasses.replace(p, storage_gb=None)   # "265GB" (Xmart's typo): no phone has it, so the size is unknown
    if p.category == "phone" and re.search(r"\b(twr|sff|ssf|tower|desktop|ddr\d)\b|\bi[3579]-\d{4,5}", title, re.I):
        # "Lenovo V50t,TWR,i7-11700,8GB DDR4,1TB": a desktop computer, never a phone
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)
    if p.category == "phone" and any(8.0 <= float(x) <= 20 for x in BIG_SCREEN.findall(title)):
        # a "phone" with an 8-inch or bigger screen is a tablet we cannot name yet (Blackview Link 8, 12.7"): never filed as a phone
        return ParsedTitle(None, "", None, None, "unknown", "unknown", False, None)
    return p
