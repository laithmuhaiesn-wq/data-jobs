"""Stage 3 electronics read by one shared reader (2026-11-14): earbuds and headphones, speakers, game consoles, monitors,
printers, desktop computers, Wi-Fi routers, power banks, storage (SSDs, hard drives, memory) and cameras.

A product is told apart by its maker + its model words ("Galaxy Buds 3 Pro", "Flip 6", "Archer AX55", "LaserJet Pro M211dw")
or, when the title carries one, the maker's model code alone ("WH-1000XM6", "27GR75Q-B", "SN850X"): shops write the code the
same way even when they put the other words in a different order. The size field holds what sets one version apart:
a monitor's screen in inches, a drive's or a console's capacity in GB, a power bank's mAh; 0 when the line has one version.
Only well-known makers (no-name goods carry no model a second shop would write the same way). Never guessed: a title
without a model number, a drive without its capacity, a power bank without its mAh, a desktop without its processor.
"""
from __future__ import annotations

import re

from . import laptop

# category -> (family prefix, English name). The prefix starts every catalogue name, so the category is read from the name.
PREFIX = {"audio": "audio", "speaker": "speaker", "console": "console", "monitor": "monitor", "printer": "printer",
          "desktop": "desktop", "router": "router", "powerbank": "powerbank", "storage": "storage", "camera": "camera"}

_B = {  # spelling in titles -> brand name
    "apple": "Apple", "samsung": "Samsung", "sony": "Sony", "jbl": "JBL", "anker": "Anker", "soundcore": "Anker",
    "huawei": "Huawei", "xiaomi": "Xiaomi", "redmi": "Xiaomi", "honor": "Honor", "oppo": "Oppo", "realme": "Realme",
    "oneplus": "OnePlus", "nothing": "Nothing", "cmf": "Nothing", "bose": "Bose", "beats": "Beats", "sennheiser": "Sennheiser",
    "marshall": "Marshall", "jabra": "Jabra", "skullcandy": "Skullcandy", "edifier": "Edifier", "qcy": "QCY", "haylou": "Haylou",
    "baseus": "Baseus", "ugreen": "Ugreen", "logitech": "Logitech", "hyperx": "HyperX", "razer": "Razer", "steelseries": "SteelSeries",
    "corsair": "Corsair", "lenovo": "Lenovo", "harman kardon": "Harman Kardon", "harman": "Harman Kardon",
    "ultimate ears": "Ultimate Ears", "bang & olufsen": "Bang & Olufsen", "b&o": "Bang & Olufsen", "tribit": "Tribit",
    "lg": "LG", "creative": "Creative", "microlab": "Microlab", "genius": "Genius", "porodo": "Porodo", "green lion": "Green Lion",
    "hoco": "Hoco", "awei": "Awei", "lenovo thinkplus": "Lenovo", "asus": "Asus", "rog": "Asus", "msi": "MSI", "acer": "Acer",
    "dell": "Dell", "alienware": "Dell", "hp": "HP", "aoc": "AOC", "benq": "BenQ", "viewsonic": "ViewSonic", "philips": "Philips",
    "gigabyte": "Gigabyte", "aorus": "Gigabyte", "koorui": "Koorui", "dahua": "Dahua", "hikvision": "Hikvision", "xiaomi mi": "Xiaomi",
    "canon": "Canon", "epson": "Epson", "brother": "Brother", "pantum": "Pantum", "kyocera": "Kyocera", "xerox": "Xerox",
    "tp-link": "TP-Link", "tplink": "TP-Link", "tp link": "TP-Link", "d-link": "D-Link", "dlink": "D-Link", "tenda": "Tenda",
    "mercusys": "Mercusys", "netgear": "Netgear", "linksys": "Linksys", "zte": "ZTE", "mikrotik": "MikroTik", "ubiquiti": "Ubiquiti",
    "ruijie": "Ruijie", "totolink": "Totolink", "kingston": "Kingston", "western digital": "WD", "wd": "WD", "sandisk": "SanDisk",
    "seagate": "Seagate", "crucial": "Crucial", "adata": "ADATA", "lexar": "Lexar", "transcend": "Transcend", "toshiba": "Toshiba",
    "hikvision hiksemi": "Hikvision", "hiksemi": "Hikvision", "teamgroup": "TeamGroup", "team group": "TeamGroup", "pny": "PNY",
    "verbatim": "Verbatim", "silicon power": "Silicon Power", "nikon": "Nikon", "fujifilm": "Fujifilm", "gopro": "GoPro",
    "dji": "DJI", "insta360": "Insta360", "ezviz": "Ezviz", "imou": "Imou", "nintendo": "Nintendo", "microsoft": "Microsoft",
    "xbox": "Microsoft", "playstation": "Sony", "valve": "Valve", "zagg": "Zagg", "mophie": "Mophie", "belkin": "Belkin",
    "romoss": "Romoss", "remax": "Remax", "ldnio": "Ldnio", "xundd": "Xundd", "momax": "Momax", "energizer": "Energizer",
    "aukey": "Aukey", "powerology": "Powerology", "riversong": "Riversong", "yesido": "Yesido", "dell technologies": "Dell",
    "wiwu": "WiWU", "joyroom": "Joyroom", "fantech": "Fantech", "mcdodo": "Mcdodo", "promate": "Promate", "lenyes": "Lenyes",
    "xtrike me": "Xtrike Me", "xtrike": "Xtrike Me", "redragon": "Redragon", "havit": "Havit", "kodak": "Kodak",
    "panasonic": "Panasonic",
}
_CHEAP = {"WiWU", "Joyroom", "Fantech", "Mcdodo", "Promate", "Remax", "Redragon", "Havit", "Lenyes", "Xtrike Me"}
BRAND = re.compile(r"(?<![\w&-])(" + "|".join(sorted((re.escape(b) for b in _B), key=len, reverse=True)) + r")(?![\w&-])", re.I)
# which makers are trusted in which category (a printer maker's "camera" is a webcam; a no-name power bank is no model)
MAKERS = {
    "audio": {"Apple", "Samsung", "Sony", "JBL", "Anker", "Huawei", "Xiaomi", "Honor", "Oppo", "Realme", "OnePlus", "Nothing",
              "Bose", "Beats", "Sennheiser", "Marshall", "Jabra", "Skullcandy", "Edifier", "QCY", "Haylou", "Baseus", "Ugreen",
              "Logitech", "HyperX", "Razer", "SteelSeries", "Corsair", "Lenovo", "Porodo", "Green Lion", "Hoco", "Awei", "Asus",
              "Creative", "Genius", "Microsoft", "Harman Kardon", "Bang & Olufsen", "LG"},
    "speaker": {"JBL", "Anker", "Sony", "Bose", "Marshall", "Harman Kardon", "Ultimate Ears", "Bang & Olufsen", "Tribit", "LG",
                "Samsung", "Xiaomi", "Huawei", "Edifier", "Creative", "Microlab", "Genius", "Logitech", "Porodo", "Green Lion",
                "Hoco", "Awei", "Baseus", "Ugreen", "Apple", "Beats", "Nothing", "Philips"},
    "console": {"Sony", "Nintendo", "Microsoft", "Valve", "Asus", "Lenovo", "MSI"},
    "monitor": {"Samsung", "LG", "Dell", "HP", "Asus", "Acer", "MSI", "AOC", "BenQ", "ViewSonic", "Philips", "Gigabyte", "Lenovo",
                "Xiaomi", "Huawei", "Koorui", "Dahua", "Hikvision", "Apple"},
    "printer": {"HP", "Canon", "Epson", "Brother", "Pantum", "Kyocera", "Xerox"},
    "desktop": {"HP", "Dell", "Lenovo", "Asus", "Acer", "MSI", "Apple"},
    "router": {"TP-Link", "D-Link", "Tenda", "Mercusys", "Netgear", "Linksys", "Huawei", "ZTE", "Xiaomi", "Asus", "MikroTik",
               "Ubiquiti", "Ruijie", "Totolink"},
    "powerbank": {"Anker", "Samsung", "Xiaomi", "Huawei", "Honor", "Baseus", "Ugreen", "Belkin", "Zagg", "Mophie", "Porodo",
                  "Green Lion", "Romoss", "Remax", "Ldnio", "Momax", "Energizer", "Aukey", "Powerology", "Riversong", "Yesido",
                  "Hoco", "Awei", "Oppo", "Realme", "Apple", "Lenovo"},
    "storage": {"Samsung", "Kingston", "WD", "SanDisk", "Seagate", "Crucial", "ADATA", "Lexar", "Transcend", "Toshiba",
                "Hikvision", "TeamGroup", "PNY", "Verbatim", "Silicon Power", "Dahua", "Ugreen", "MSI", "Gigabyte", "Lenovo", "HP"},
    "camera": {"Canon", "Nikon", "Sony", "Fujifilm", "GoPro", "DJI", "Insta360", "Ezviz", "Imou", "Dahua", "Hikvision", "TP-Link",
               "Xiaomi", "Logitech", "Kodak", "Panasonic", "Anker"},
}
# value makers sold in many Jordan shops: they print one model code on every box ("WiWU T37", "Joyroom JR-T03S")
for _c in ("audio", "speaker", "powerbank"):
    MAKERS[_c] |= _CHEAP
MAKERS["audio"] |= {"HP", "Dell"}

# what the title must say, per category (checked in this order: a printer's "all-in-one" is not a desktop)
SAYS = [
    ("console", re.compile(r"\b(playstation\s*(?:5|4|portal)|ps5|ps\s5|nintendo\s+switch|switch\s*(?:2|oled|lite)|xbox\s+series\s*[xs]|"
                           r"steam\s*deck|rog\s*ally|legion\s+go|msi\s+claw)\b", re.I)),
    ("printer", re.compile(r"\b(printer|laserjet|deskjet|officejet|smart\s?tank|ink\s?tank|ecotank|pixma|i-?sensys|maxify|"
                           r"workforce|mfp|multifunction|طابعة)\b", re.I)),
    ("monitor", re.compile(r"\b(monitor|monitors|odyssey|ultragear|ultrawide|ultrasharp|viewfinity|شاشة\s+كمبيوتر)\b|"
                           r"(?=.*\b\d{2,3}\s*hz\b)(?=.*\b(?:ips|va|fhd|full\s?hd|qhd|wqhd|uhd|1080p|freesync|g-?sync)\b)(?!.*\b(?:tv|laptop|notebook|"
                           r"phone|tablet|core|ryzen)\b)", re.I)),
    ("desktop", re.compile(r"\b(desktop|all[\s-]*in[\s-]*one|aio|mini\s?pc|tiny\s?pc|tower\s+pc|pc\s+tower|imac|mac\s?mini|mac\s?studio|"
                           r"optiplex|thinkcentre|thinkcenter|prodesk|elitedesk|veriton|ideacentre|expertcenter|pro\s+tower|sff)\b", re.I)),
    ("audio", re.compile(r"\b(earbuds?|ear\s?buds|earphones?|headphones?|headsets?|airpods|earpods|buds\d*|freebuds|freeclip|"
                         r"in-?ear|over-?ear|on-?ear|tws|neckband|سماعة\s+(?:أذن|اذن|رأس|راس)|ايربودز)\b", re.I)),
    ("speaker", re.compile(r"\b(speakers?|sound\s?bar|soundbar|boombox|partybox|xboom|home\s+theat(?:er|re)|سبيكر|مكبر\s+صوت)\b", re.I)),
    ("powerbank", re.compile(r"\b(power\s?bank|powerbank|powercore|battery\s+pack|magsafe\s+battery|باور\s?بانك)\b", re.I)),
    ("storage", re.compile(r"\b(ssd|nvme|m\.2|hdd|hard\s?(?:drive|disk)|portable\s+drive|external\s+drive|flash\s?(?:drive|disk|memory)|"
                           r"usb\s+(?:flash|drive|stick)|memory\s+card|micro\s?sd(?:xc|hc)?|sd\s?(?:xc|hc)?\s+card)\b", re.I)),
    ("router", re.compile(r"\b(router|mesh|wi-?fi\s+system|access\s+point|range\s+extender|extender|repeater|mifi|deco|archer|"
                          r"راوتر)\b", re.I)),
    ("camera", re.compile(r"\b(camera|webcam|web\s?cam|dash\s?cam|action\s?cam|gopro|mirrorless|dslr|instax|eos|cctv|ip\s?cam|"
                          r"كاميرا)\b", re.I)),
]
# things sold in the same sections that are not the product: parts, add-ons, games
NOT_IT = re.compile(
    r"\b(case\s+for|cover|protector|skin|sticker|strap|ear\s?tips?|ear\s?pads?|cushions?|replacement|spare|cable|cord|adapter|"
    r"converter|dongle|stand|holder|mount|bracket|arm|hook|bag|pouch|sleeve|charger|charging\s+(?:case|dock|station)|dock|"
    r"controller|dualsense|joy-?con|gamepad|game\s+for|games?\b(?!\s*(?:console|edition))|gift\s+card|membership|subscription|"
    r"psn|ink|toner|cartridge|drum|ribbon|paper|printhead|refill|bottle|enclosure|caddy|card\s+reader|reader|lens\s+(?:cap|filter)|"
    r"tripod|battery\s+for|grip|keyboard|mouse|combo|kit\b|bundle|accessor\w*|for\s+(?:iphone|samsung|galaxy|airpods|ps5|switch)|"
    r"compatible|refurb\w*|renewed|used|open\s?box|demo|tool|cleaner|cleaning|remote|dvr|nvr|xvr|recorder)\b", re.I)
CONSOLE_NOT = re.compile(r"\b(controller|dualsense|joy-?con|gamepad|game\s+for|games?\b(?!\s*console)|case|cover|skin|stand|dock|"
                         r"charger|charging|cable|bag|pouch|protector|grip|headset|camera|gift\s+card|psn|membership|"
                         r"subscription|refurb\w*|renewed|used|open\s?box|bundle|for\s+(?:ps5|switch|xbox))\b", re.I)
COMPUTER = re.compile(r"\b(core\W{0,3}(?:i[3579]|ultra|[3579])|i[3579]-\d{4,5}\w*|ryzen|celeron|pentium|snapdragon\s+x|ddr[345]\w*|"
                      r"lpddr\d\w*|rtx\s*\d{4}|gtx\s*\d{4}|mx\d{3}|laptop|notebook|macbook|chromebook|thinkpad|zenbook|vivobook|"
                      r"ideapad|thinkbook|yoga|pavilion|elitebook|probook|inspiron|latitude|aspire|swift|predator\s+helios)\b", re.I)
PHONE_SIGNS = re.compile(r"\b(\d{4,5}\s*mah|\d{2,3}\s*mp|amoled|fhd\+|smartphone|ram|5g|snapdragon\s+\d|dimensity|helio)\b", re.I)
BIG_SCREEN = re.compile(r"(?<![\d.])([5-9]\d|1\d{2})\s*(?:-?\s*inch|\"|”|″)", re.I)   # 50" and up is a TV, whatever the title says
CONSOLE_SAYS = re.compile(r"\b(console|slim|disc|digital|edition|\d+\s*(?:gb|tb)|oled\s+model|handheld)\b", re.I)
PHONE_CAMERA = re.compile(r"\d+\s*mp\b|\b(iphone|galaxy\s+[asmz]\d|ipad|redmi\s+note|phone|smartphone|laptop|notebook|ram|"
                          r"storage|\d+\s*hz)\b", re.I)
CUT = re.compile(r",|\s[-–—|]\s|\(|\[|\s[–—]|\bwith\b|\bfor\b|\bwhite\b|\bblack\b", re.I)
GEN = re.compile(r"\((\d)(?:st|nd|rd|th)\s+gen\w*\)|\b(\d)(?:st|nd|rd|th)\s+gen(?:eration)?\b", re.I)
SKIP = {  # words that say what kind of thing it is, never which model: dropped wherever they stand
    "wireless", "bluetooth", "bt", "true", "tws", "earbuds", "earbud", "earphones", "earphone", "headphones", "headphone", "headset",
    "headsets", "gaming", "noise", "cancelling", "canceling", "active", "anc", "enc", "hybrid", "in", "ear", "over", "on", "the",
    "sport", "sports", "open", "speaker", "speakers", "portable", "waterproof", "outdoor", "party", "smart", "monitor", "monitors",
    "display", "led", "lcd", "ips", "va", "oled", "qled", "flat", "curved", "fhd", "qhd", "uhd", "hd", "full", "4k", "2k", "5k",
    "printer", "printers", "laser", "inkjet", "ink", "tank", "colour", "color", "mono", "monochrome", "all", "aio",
    "wifi", "wi-fi", "wi", "fi", "multifunction", "multi", "function", "duplex", "router", "mesh", "system", "dual", "tri",
    "band", "gigabit", "access", "point", "range", "extender", "repeater", "power", "bank", "powerbank", "fast", "charging",
    "magnetic", "slim", "mini", "external", "internal", "drive", "hard", "disk", "solid", "state", "ssd", "nvme", "pcie",
    "gen4", "gen5", "sata", "usb", "type", "c", "flash", "memory", "card", "portable", "camera", "cameras", "action", "digital",
    "webcam", "security", "indoor", "desktop", "pc", "computer", "tower", "new", "original", "official", "version", "global",
    "edition", "model", "series", "inch", "inches", "with", "and", "for", "of", "by", "from", "rgb", "mic", "microphone",
    "stereo", "surround", "sound", "audio", "hifi", "hi-fi", "high", "quality", "dolby", "atmos", "deep", "bass", "extra",
    "console", "consoles", "handheld", "video", "game", "home", "office", "business", "personal", "ultra-slim", "thin",
    "frameless", "borderless", "adjustable", "height", "pivot", "speakers", "built-in", "builtin", "mfp", "scanner", "copier",
    "fax", "print", "scan", "copy", "network", "ethernet", "port", "ports", "lan", "wan", "ax", "ac", "be",
}
COLOURS = {"black", "white", "silver", "gold", "grey", "gray", "blue", "green", "pink", "red", "purple", "orange", "yellow",
           "beige", "cream", "midnight", "starlight", "graphite", "navy", "teal", "mint", "lavender", "violet", "rose", "titanium",
           "natural", "sand", "olive", "camo", "brown", "coral", "sky", "ivory", "phantom", "onyx", "obsidian"}
UNITS = re.compile(r"^\d+(?:\.\d+)?(?:mah|w|wh|gb|tb|mb|hz|mp|k|p|ms|mm|cm|m|v|a|db|h|hrs?|nits|ppm|dpi|x|in|inch|fps|ch)$")
SPEED = re.compile(r"^(?:ax|ac|be|ad|n)\d{3,5}$")                                # "AX3000": a speed class many routers share
SUFFIX = {"pro", "max", "plus", "ultra", "lite", "mini", "se", "x", "s", "e", "i", "fe", "nc", "anc", "air", "neo", "go", "slim",
          "oled", "digital", "disc", "ii", "iii", "iv", "v", "mark", "elite", "core", "gt", "open", "clip", "studio", "beam", "free"}
CODE = re.compile(r"^(?=.*[a-z])(?=(?:.*\d){2})[a-z0-9]{5,}$")                     # a maker's code: letters and 2+ digits


def category(title: str) -> str | None:
    """Which of the new categories a title says it is (None when it is none of them, or an add-on such as a case)."""
    head = CUT.split(title)[0]                     # add-ons say so up front ("Case for AirPods"); "... with stand" is the product
    for cat, says in SAYS:
        if says.search(title):
            if cat == "console":
                m = says.search(title)
                if CONSOLE_NOT.search(title) or not (CONSOLE_SAYS.search(title) or len(re.findall(r"\w+", title[:m.start()])) <= 2):
                    continue                       # "Spider-Man 2 PS5" is a game, "Headset for PS5" a headset
                return cat
            if cat != "desktop" and COMPUTER.search(title):
                continue                           # a laptop's "512GB SSD" or "Dolby speakers" is not a drive or a speaker
            if cat == "monitor" and (BIG_SCREEN.search(title) or PHONE_SIGNS.search(title)):
                continue                           # "Samsung QLED 75-inch Monitor" is a TV; "144Hz FHD+ ... 8GB RAM" a phone
            if NOT_IT.search(head) or re.search(r"\bcases?\b", head, re.I) and cat in ("audio", "storage", "camera"):
                return None
            if cat == "camera" and PHONE_CAMERA.search(title):
                return None
            return cat
    return None


def looks_like_gadget(title: str) -> bool:
    return category(title) is not None


def _brand(title: str) -> tuple[str, str] | None:
    m = BRAND.search(title)
    return (_B[m.group(1).lower()], m.group(1)) if m else None


def _words(head: str) -> list[str]:
    head = GEN.sub(lambda m: f" {m.group(1) or m.group(2)} ", head)
    head = re.sub(r"\ball[\s-]*in[\s-]*one\b", " ", head, flags=re.I)
    head = re.sub(r"\b(smart|ink|eco)\s*tank\b", r"\1tank", head, flags=re.I)              # "Smart Tank 581" is one name
    head = re.sub(r"(?<![\w.])\d+\.\d+\b", " ", head)                                # "PCIe 4.0", "Bluetooth 5.3", "23.8 inch"
    head = re.sub(r"(?<![\w.])\d{2}\s*(?:\"|″|”|''|-?\s*inch(?:es)?\b)", " ", head, flags=re.I)  # the screen size has its own field
    head = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9]{3,})", "", head, flags=re.I)          # "WH-1000XM6" -> "WH1000XM6"
    head = re.sub(r"(?<=[a-z0-9]{4})-[a-z]{1,2}\b", "", head, flags=re.I)            # "27GR75Q-B": a colour letter
    head = re.sub(r"\b([a-z]{3,})(\d+)\b", r"\1 \2", head, flags=re.I)               # "Buds3" -> "Buds 3", "Flip6" -> "Flip 6"
    head = re.sub(r"\b(\d+)(pro|max|plus|ultra|lite|mini|se)\b", r"\1 \2", head, flags=re.I)
    return re.findall(r"[a-z0-9+]+", head.lower())


CODE_ANYWHERE = {"printer", "monitor", "router", "storage", "camera"}   # maker codes these shops always copy from the box


def _generic(w: str) -> bool:
    return w in SKIP or bool(UNITS.match(w) or SPEED.match(w))


def _model(title: str, brand_word: str, cat: str) -> str | None:
    head = CUT.split(GEN.sub(lambda m: f" {m.group(1) or m.group(2)} ", re.sub(r"^\s*\W+", "", title)))[0]
    words = _words(head)
    bw = _words(brand_word)
    at = next((i for i in range(len(words)) if words[i:i + len(bw)] == bw), None)
    if at is None:
        return None
    rest = words[at + len(bw):]
    while rest and (_generic(rest[0]) or rest[0] in _B):
        rest = rest[1:]
    codes = [w for w in rest if CODE.match(w) and not UNITS.match(w) and not SPEED.match(w)]
    if codes and (cat in CODE_ANYWHERE or rest[0] == codes[0]):
        return codes[0]                                               # "WH1000XM6", "M211DW", "27GR75Q"
    out: list[str] = []
    for w in rest:
        numbered = any(ch.isdigit() for ch in " ".join(out))
        if w in COLOURS:
            break
        if _generic(w):
            if numbered:
                break                                                 # "Flip 6 Portable ...": the name has ended
            continue
        if w in _B:
            continue
        if out and w in codes:
            break                                                     # "Space One A3035021": the box code after the name
        if numbered and (w not in SUFFIX and not w.isdigit() or w.isdigit() and out[-1].isdigit()):
            break                                                     # after the number only "Pro", "Max"... belong to it
        out.append(w.replace("+", "plus"))
        if len(out) >= 5:
            break
    line = " ".join(out).strip()
    if not line or re.fullmatch(r"[\d\s]+", line):
        return None                                                   # "Dahua 27": which one?
    if not re.search(r"\d", line) and not (cat == "powerbank" or cat in ("audio", "speaker") and len(out) >= 2):
        return None                                                   # "JBL Wireless Speaker": which one?
    return line


INCH = re.compile(r"(?<![\d.])(1[5-9]|[2-4]\d)(?:\.\d)?\s*(?:\"|″|''|”|-?\s*inch(?:es)?|in\b|انش|إنش)", re.I)
CAPACITY = re.compile(r"(?<![\d.])(\d{1,4})\s*(gb|tb)\b", re.I)
MAH = re.compile(r"(?<![\d.])(\d{1,2}[,.]?\d{3}|\d{1,2})\s*(k\b|mah)", re.I)


def _size(cat: str, title: str) -> int | None:
    if cat == "monitor":
        m = INCH.search(title)
        return int(m.group(1)) if m else None
    if cat in ("storage", "console"):
        vals = {int(n) * (1024 if u.lower() == "tb" else 1) for n, u in CAPACITY.findall(title)}
        if len(vals) != 1:
            return None if cat == "storage" else 0
        return vals.pop()
    if cat == "powerbank":
        m = MAH.search(title)
        if not m:
            return None
        n = int(re.sub(r"\D", "", m.group(1)))
        return n * 1000 if m.group(2).lower() == "k" or n < 100 else n
    return 0


CONSOLES = [  # (pattern, maker, family words); the first that matches names the console
    (r"playstation\s*portal|ps\s?portal", "Sony", "playstation portal"),
    (r"(?:playstation|ps)\s*5\s*pro|ps5\s*pro", "Sony", "playstation 5 pro"),
    (r"(?:playstation|ps)\s*5.*\bdigital|(?:playstation|ps)\s*5\s*slim\s*digital", "Sony", "playstation 5 digital"),
    (r"(?:playstation|ps)\s*5", "Sony", "playstation 5"),
    (r"switch\s*2", "Nintendo", "switch 2"),
    (r"switch\s*(?:oled|-\s*oled)", "Nintendo", "switch oled"),
    (r"switch\s*lite", "Nintendo", "switch lite"),
    (r"xbox\s+series\s*x", "Microsoft", "xbox series x"),
    (r"xbox\s+series\s*s", "Microsoft", "xbox series s"),
    (r"steam\s*deck\s*oled", "Valve", "steam deck oled"),
    (r"rog\s*ally\s*x", "Asus", "rog ally x"),
    (r"rog\s*(?:xbox\s*)?ally", "Asus", "rog ally"),
    (r"legion\s+go\s*s", "Lenovo", "legion go s"),
    (r"legion\s+go\s*2", "Lenovo", "legion go 2"),
    (r"legion\s+go", "Lenovo", "legion go"),
    (r"msi\s+claw", "MSI", "claw"),
]


def _console(title: str) -> tuple[str, str] | None:
    for pat, maker, fam in CONSOLES:
        if re.search(r"\b" + pat, title, re.I):
            if maker == "Nintendo" and fam == "switch 2" and re.search(r"\bswitch\s*2\b.*\b(mario|pokemon|zelda|bundle)\b", title, re.I):
                return None                                                       # a console with a game: another price
            return maker, fam
    return None


DESK_WORDS = {"gen", "sff", "compact", "business", "tiny", "small", "form", "factor", "twr", "mt", "workstation", "ai", "2025",
              "2026", "2024", "high", "performance", "next", "level"}
SPEC_CODE = re.compile(r"\b[a-z]+\d+[a-z]+\d*\b|\b[a-z]\d{3,}[a-z]*\b", re.I)   # "X2722G", "D7VB1AT": not a memory size


def _desktop(title: str, brand: str, brand_word: str) -> str | None:
    t = title.lower()
    if brand == "Apple":
        line = "imac" if "imac" in t else "mac mini" if re.search(r"mac\s?mini", t) else "mac studio" if re.search(r"mac\s?studio", t) else None
        chip = re.search(r"\b(m[1-9])(?:\s*(pro|max|ultra))?\b", t)
        if not line or not chip:
            return None
        return f"{line} {chip.group(1)}{' ' + chip.group(2) if chip.group(2) else ''}"
    cpu = laptop.cpu_of(title)
    if not cpu:
        return None                                                               # which processor? never guessed
    words = _words(CUT.split(title)[0])
    bw = _words(brand_word)
    at = next((i for i in range(len(words)) if words[i:i + len(bw)] == bw), None)
    if at is None:
        return None
    out = []
    for w in words[at + len(bw):]:
        if re.match(r"^(i[3579]|core|intel|amd|ryzen|ultra|\d{4,5}[a-z]*|celeron|pentium|n\d{3})$", w):
            break
        if w in SKIP or w in DESK_WORDS:
            continue
        if w in COLOURS or UNITS.match(w):
            break
        out.append(w)
        if len(out) >= 5:
            break
    if not out or not re.search(r"\d", " ".join(out)):
        return None
    return f"{' '.join(out)} {cpu}"


def parse(title: str) -> tuple[str, str, str, int, int | None] | None:
    """(category, brand, family, size, ram) or None when the product cannot be told apart.
    The family starts with the category's prefix ("audio galaxy buds 3 pro", "monitor 27gr75q")."""
    cat = category(title)
    if cat is None:
        return None
    if cat == "console":
        found = _console(title)
        if not found:
            return None
        brand, fam = found
        size = _size(cat, title)
        if fam in ("xbox series s",) and size not in (512, 1024):
            size = 512
        elif fam not in ("xbox series s",):
            size = 0                                                              # one storage size per console line
        return cat, brand, f"console {fam}", size, None
    b = _brand(title)
    if not b or b[0] not in MAKERS[cat]:
        return None
    brand, word = b
    ram = None
    if cat == "desktop":
        fam = _desktop(title, brand, word)
        if not fam:
            return None
        ram, storage = laptop.ram_storage(SPEC_CODE.sub(" ", title))
        return cat, brand, f"desktop {fam}", storage or 0, ram
    fam = _model(title, word, cat)
    if not fam:
        return None
    size = _size(cat, title)
    if size is None:
        return None
    return cat, brand, f"{PREFIX[cat]} {fam}", size, ram


def is_gadget_family(family: str) -> bool:
    return family.split(" ", 1)[0] in PREFIX.values()


def category_of(family: str) -> str | None:
    head = family.split(" ", 1)[0]
    return next((c for c, p in PREFIX.items() if p == head), None)


def well_formed(family: str) -> bool:
    words = family.split()[1:]
    return 1 <= len(words) <= 6 and len(family) <= 48 and bool(re.search(r"\d", family) or len(words) >= 2)


_UPPER = {"anc", "nc", "se", "fe", "oled", "ps", "gt", "ii", "iii", "iv", "rog", "x", "s", "qled", "tws", "dw", "mfp", "aio"}


def pretty(brand: str, family: str) -> str:
    """'Samsung Galaxy Buds 3 Pro', 'Sony WH1000XM6', 'HP LaserJet Pro M211DW', 'Sony PlayStation 5 Pro'."""
    words = family.split()[1:]
    special = {"playstation": "PlayStation", "airpods": "AirPods", "freebuds": "FreeBuds", "laserjet": "LaserJet",
               "deskjet": "DeskJet", "officejet": "OfficeJet", "ecotank": "EcoTank", "imac": "iMac", "xbox": "Xbox",
               "soundcore": "Soundcore", "partybox": "PartyBox", "powercore": "PowerCore", "ultragear": "UltraGear", "smarttank": "Smart Tank", "inktank": "Ink Tank"}

    def cap(w: str) -> str:
        if w in special:
            return special[w]
        if w in _UPPER or re.search(r"\d", w) and re.search(r"[a-z]", w):
            return w.upper()
        return w.capitalize()
    name = " ".join(cap(w) for w in words)
    if family.startswith("desktop "):
        return laptop.pretty(brand, " ".join(words)) if brand != "Apple" else f"Apple {name.replace('Mac Mini', 'Mac mini')}"
    return f"{brand} {name}".strip()


def size_label(category: str, size: int | None) -> str:
    if not size:
        return ""
    if category == "monitor":
        return f'{size}"'
    if category == "powerbank":
        return f"{size:,}mAh"
    if category in ("storage", "console", "desktop"):
        return f"{size // 1024}TB" if size >= 1024 and size % 1024 == 0 else f"{size}GB"
    return ""


NAMES = {  # category -> (English plural, Arabic plural, English one, Arabic one, web path)
    "audio": ("Earbuds & headphones", "سماعات", "Headphones", "سماعة", "headphones"),
    "speaker": ("Speakers", "مكبرات الصوت", "Speaker", "سماعة خارجية", "speakers"),
    "console": ("Game consoles", "أجهزة الألعاب", "Console", "جهاز ألعاب", "consoles"),
    "monitor": ("Monitors", "شاشات الكمبيوتر", "Monitor", "شاشة كمبيوتر", "monitors"),
    "printer": ("Printers", "الطابعات", "Printer", "طابعة", "printers"),
    "desktop": ("Desktop computers", "أجهزة الكمبيوتر المكتبية", "Desktop", "كمبيوتر مكتبي", "desktops"),
    "router": ("Routers & Wi-Fi", "الراوترات", "Router", "راوتر", "routers"),
    "powerbank": ("Power banks", "الباور بانك", "Power bank", "باور بانك", "power-banks"),
    "storage": ("Storage & memory", "وحدات التخزين", "Storage", "وحدة تخزين", "storage"),
    "camera": ("Cameras", "الكاميرات", "Camera", "كاميرا", "cameras"),
}
