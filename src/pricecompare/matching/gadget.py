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
PREFIX = {"projector": "projector", "smarthome": "smarthome", "peripheral": "peripheral", "tabletacc": "tabletacc",
          "pcpart": "pcpart", "audio": "audio", "speaker": "speaker", "console": "console", "monitor": "monitor", "printer": "printer",
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
    "xtrike me": "Xtrike Me", "xtrike-me": "Xtrike Me", "xtrike": "Xtrike Me", "redragon": "Redragon", "havit": "Havit", "kodak": "Kodak",
    "panasonic": "Panasonic",
    # 2026-11-15: projectors, smart home, keyboards and mice, tablet pens, PC parts
    "optoma": "Optoma", "infocus": "InFocus", "xgimi": "XGIMI", "wanbo": "Wanbo", "dangbei": "Dangbei", "hisense": "Hisense",
    "roborock": "Roborock", "dreame": "Dreame", "ecovacs": "Ecovacs", "irobot": "iRobot", "roomba": "iRobot", "eufy": "Anker",
    "aqara": "Aqara", "tapo": "TP-Link", "kasa": "TP-Link", "yale": "Yale", "amazon": "Amazon", "echo": "Amazon", "google": "Google",
    "nest": "Google", "keychron": "Keychron", "glorious": "Glorious", "rapoo": "Rapoo", "a4tech": "A4Tech", "marvo": "Marvo",
    "gamdias": "Gamdias", "cooler master": "Cooler Master", "attack shark": "Attack Shark", "zotac": "Zotac", "palit": "Palit",
    "gainward": "Gainward", "sapphire": "Sapphire", "powercolor": "PowerColor", "xfx": "XFX", "intel": "Intel", "amd": "AMD",
    "inno3d": "Inno3D", "asrock": "ASRock", "hp omen": "HP", "sonoff": "Sonoff", "moes": "Moes",
    # 2026-11-21: value brands many Jordan shops sell (~800 listings were filed as "not a product")
    "huntkey": "Huntkey", "meetion": "Meetion", "haing": "Haing", "sades": "Sades", "gravastar": "Gravastar", "hifuture": "HiFuture",
    "apacer": "Apacer", "onikuma": "Onikuma", "imice": "iMice", "kisonli": "Kisonli", "aula": "Aula", "ducky": "Ducky",
    "unv": "UNV", "uniview": "UNV", "gameon": "GameOn", "twisted minds": "Twisted Minds", "machenike": "Machenike", "ajazz": "Ajazz", "xpg": "ADATA", "poly": "Poly", "fifine": "Fifine", "lecoo": "Lecoo", "nubwo": "Nubwo", "ridata": "RiDATA",
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
MAKERS |= {
    "projector": {"Epson", "BenQ", "ViewSonic", "Optoma", "InFocus", "Acer", "XGIMI", "Xiaomi", "Samsung", "LG", "Wanbo", "Dangbei",
                  "Hisense", "Sony", "Canon", "Panasonic", "Dahua", "Philips", "Lenovo", "Anker", "Porodo", "Havit", "Promate",
                  "Yesido", "Green Lion"},
    "smarthome": {"Xiaomi", "Roborock", "Dreame", "Ecovacs", "iRobot", "Anker", "TP-Link", "Ezviz", "Imou", "Aqara", "Philips", "Yale",
                  "Amazon", "Google", "Samsung", "Huawei", "Honor", "Apple", "Porodo", "Green Lion", "Hikvision", "Dahua", "Sonoff", "Moes"},
    "peripheral": {"Logitech", "Razer", "Corsair", "SteelSeries", "HyperX", "Redragon", "Fantech", "Asus", "MSI", "HP", "Dell",
                   "Lenovo", "Microsoft", "Apple", "Genius", "Rapoo", "A4Tech", "Havit", "Xtrike Me", "Attack Shark", "Keychron",
                   "Glorious", "Marvo", "Gamdias", "Cooler Master", "Porodo", "Ugreen", "Baseus", "Huawei", "Xiaomi", "Gigabyte"},
    "tabletacc": {"Apple", "Samsung", "Xiaomi", "Huawei", "Honor", "Lenovo", "Logitech", "Microsoft"},
    "pcpart": {"Asus", "MSI", "Gigabyte", "Zotac", "Palit", "Gainward", "PNY", "Sapphire", "PowerColor", "XFX", "Intel", "AMD",
               "Inno3D", "ASRock"},
}
# value makers sold in many Jordan shops: they print one model code on every box ("WiWU T37", "Joyroom JR-T03S")
for _c in ("audio", "speaker", "powerbank"):
    MAKERS[_c] |= _CHEAP
MAKERS["audio"] |= {"HP", "Dell", "Meetion", "Haing", "Sades", "Gravastar", "HiFuture", "Onikuma", "Kisonli", "Nubwo", "Lecoo"}
MAKERS["speaker"] |= {"Gravastar", "HiFuture", "Kisonli", "Meetion"}
MAKERS["peripheral"] |= {"Meetion", "Sades", "Onikuma", "iMice", "Kisonli", "Aula", "Ducky", "Lecoo", "Gravastar"}
MAKERS["storage"] |= {"Apacer", "RiDATA"}
MAKERS["camera"] |= {"UNV"}
MAKERS["monitor"] |= {"GameOn", "Twisted Minds", "Huntkey", "Haing", "UNV"}
# 2026-11-25: makers whose real model codes were read in one category only
MAKERS["peripheral"] |= {"Haing", "Machenike", "Ajazz", "ADATA"}
MAKERS["speaker"] |= {"Lecoo", "Lenovo"}
MAKERS["storage"] |= {"HyperX"}
MAKERS["powerbank"] |= {"Haing"}
MAKERS["audio"] |= {"Poly", "Fifine", "Machenike", "Attack Shark", "MSI", "Marvo", "Philips", "Haing"}
MAKERS["speaker"] |= {"HP"}
MAKERS["peripheral"] |= {"AOC"}
MAKERS["camera"] |= {"Rapoo", "D-Link"}
MAKERS["router"] |= {"Imou"}

# what the title must say, per category (checked in this order: a printer's "all-in-one" is not a desktop)
SAYS = [
    ("console", re.compile(r"\b(playstation\s*(?:5|4|portal)|ps5|ps\s5|nintendo\s+switch|switch\s*(?:2|oled|lite)|xbox\s+series\s*[xs]|"
                           r"steam\s*deck|rog\s*ally|legion\s+go|msi\s+claw)\b", re.I)),
    ("printer", re.compile(r"\b(printer|laserjet|deskjet|officejet|smart\s?tank|ink\s?tank|ecotank|pixma|i-?sensys|maxify|"
                           r"workforce|mfp|multifunction|طابعة)\b", re.I)),
    ("projector", re.compile(r"\b(projector|projectors|data\s*show|beamer|بروجكتر)\b", re.I)),
    ("pcpart", re.compile(r"\b(graphics?\s+card|video\s+card|vga\s+card|gpu|processor|cpu|geforce\s+rtx|radeon\s+rx)\b|"
                          r"^\W*intel\W+(?:new\s+\d+gen\s+)?core\W+(?:i[3579]-\d{4,5}|ultra\s+[3579]\s+\d{3})\w*\b(?!.*(?:\b(?:ram|ssd|laptop|ddr\d|desktop|tower|rtx)\b|//))|"
                          r"^\W*(?:\w+\s+){0,4}(?:rtx|gtx)\s*\d{4}\b(?!.*\b(?:laptop|notebook|desktop|pc|ram|ssd)\b)", re.I)),
    ("tabletacc", re.compile(r"\b(apple\s+pencil|pencil\s+(?:pro|usb-?c|2|\(?2nd)|s\s?pen|stylus|smart\s+keyboard|magic\s+keyboard\s+for\s+ipad|"
                             r"keyboard\s+(?:case|cover|folio)|book\s+cover\s+keyboard|m-?pencil|focus\s+pen|smart\s+pen)\b", re.I)),
    ("smarthome", re.compile(r"\b(robot(?:ic)?\s+(?:vacuum|cleaner|mop)|vacuum\s+robot|robot\s+vacuum|smart\s+(?:plug|bulb|lamp|light\s?strip|"
                             r"lock|switch|socket|door\s?lock|doorbell|scale|sensor|display|hub|curtain)|video\s+doorbell|door\s?bell|"
                             r"echo\s+(?:dot|show|pop)|nest\s+(?:mini|hub|audio))\b", re.I)),
    ("monitor", re.compile(r"\b(monitor|monitors|odyssey|ultragear|ultra\s?wide|ultrasharp|viewfinity|شاشة\s+كمبيوتر)\b|"
                           r"(?=.*\b\d{2,3}\s*hz\b)(?=.*\b(?:ips|va|fhd|full\s?hd|qhd|wqhd|uhd|1080p|freesync|g-?sync)\b)(?!.*\b(?:tv|laptop|notebook|"
                           r"phone|tablet|core|ryzen)\b)", re.I)),
    ("desktop", re.compile(r"\b(desktop|all[\s-]*in[\s-]*one|aio|mini\s?pc|tiny\s?pc|tower\s+pc|pc\s+tower|imac|mac\s?mini|mac\s?studio|"
                           r"optiplex|thinkcentre|thinkcenter|prodesk|elitedesk|veriton|ideacentre|expertcenter|pro\s+tower|sff)\b", re.I)),
    ("audio", re.compile(r"\b(earbuds?|ear\s?buds|earphones?|headphones?|headsets?|airpods|earpods|buds\d*|freebuds|freeclip|airbuds(?=\s*(?:pro|max|\d))|fitbuds|lightbuds|cubuds|"
                         r"soundcore\s+(?:aeroclip|space\s+one|liberty|[pqrvkc]\d{1,2}i)|jbl\s+(?:tune|live|wave)\b(?=.*(?:\d{3}nc|\d{3}bt|pro\s+\d|beam|buds|flex|vibe))|redragon\s+(?:\w+(?:-x)?\s+)?h\d{3}\b|"
                         r"in-?ear|over-?ear|on-?ear|neckband|سماعة\s+(?:أذن|اذن|رأس|راس)|ايربودز)\b", re.I)),
    ("speaker", re.compile(r"\b(speakers?|sound\s?bar|soundbar|boombox|partybox|xboom|home\s+theat(?:er|re)|سبيكر|مكبر\s+صوت)\b", re.I)),
    ("powerbank", re.compile(r"\b(power\s?bank|powerbank|powercore|battery\s+pack|magsafe\s+battery|باور\s?بانك)\b", re.I)),
    ("storage", re.compile(r"\b(ssd|nvme|m\.2|hdd|hard\s?(?:drive|disk)|portable\s+drive|external\s+drive|flash\s?(?:drive|disk|memory)|"
                           r"usb\s+(?:flash|drive|stick)|memory\s+card|micro\s?sd(?:xc|hc)?|sd\s?(?:xc|hc)?\s+card)\b", re.I)),
    ("router", re.compile(r"\b(router(?=\d)|router|mesh\s+(?:wi-?fi|system|router|network|node)|(?:wi-?fi|whole[\s-]home)\s+mesh|wi-?fi\s+system|mobile\s+wi-?fi|access\s+point|range\s+extender|extender|repeater|mifi|deco|archer|"
                          r"راوتر)\b", re.I)),
    ("peripheral", re.compile(r"\b(keyboards?|mouse|mice|keyboard\s+(?:and|&|\+)\s+mouse)\b|كيبورد|ماوس", re.I)),
    ("camera", re.compile(r"\b((?:solo|indoor|wired|floodlight)\s?cam|camera|webcam|web\s?cam|dash\s?cam|action\s?cam|gopro|mirrorless|dslr|instax|eos|cctv|ip\s?cam|"
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
                         r"subscription|refurb\w*|renewed|used|open\s?box|bundle|compatible|card|expansion|stick|mount|"
                         r"charging|adapter|power\s+supply|lens|film|glass|strap)\b", re.I)   # "AddLink 2TB SSD | PS5 Compatible"
# storage words name an add-on only BEFORE the console ("NVMe SSD for PS5"); after it they describe the console
# ("PS5 Slim Disc Edition Console – 1TB SSD", "PS5 Slim 1TB with Ultra HD Blu-ray Disc Drive")
CONSOLE_PART = re.compile(r"\b(for|ssd|nvme|m\.2|heatsink|hdd|drive|memory)\b", re.I)
COMPUTER = re.compile(r"\b(core\W{0,3}(?:i[3579]|ultra|[3579])|i[3579]-\d{4,5}\w*|ryzen|celeron|pentium|snapdragon\s+x|ddr[345]\w*|"
                      r"lpddr\d\w*|rtx\s*\d{4}|gtx\s*\d{4}|mx\d{3}|laptop|notebook|macbook|chromebook|thinkpad|zenbook|vivobook|"
                      r"ideapad|thinkbook|yoga|pavilion|elitebook|probook|inspiron|latitude|aspire|swift|predator\s+helios)\b", re.I)
PHONE_SIGNS = re.compile(r"\b(\d{4,5}\s*mah|\d{2,3}\s*mp|amoled|fhd\+|smartphone|ram|5g|snapdragon\s+\d|dimensity|helio)\b", re.I)
BIG_SCREEN = re.compile(r"(?<![\d.])([5-9]\d|1\d{2})\s*(?:-?\s*inch|\"|”|″)", re.I)   # 50" and up is a TV, whatever the title says
CONSOLE_BOX = re.compile(r"\bconsole\b", re.I)
CONSOLE_SAYS = re.compile(r"\b(console|slim|disc|digital|\d+\s*(?:gb|tb)|oled\s+model|handheld)\b", re.I)
GAME = re.compile(r"\b(standard|deluxe|launch|ultimate|gold|premium|complete|collector'?s?|definitive|legendary)\s+edition\b|"
                  r"\b(backpack|carrying|game|games|fifa|fc\s?\d{2}|remote\s+play(?!er))\b|"
                  r"\bswitch\s?2\s+edition\b", re.I)   # "Hades II – Nintendo Switch 2 Edition": a game (iGeek 2026-11-22)
PHONE_CAMERA = re.compile(r"\b(iphone|galaxy\s+[asmz]\d|ipad|redmi\s+note|phone|smartphone|laptop|notebook|ram|"
                          r"storage|\d+\s*hz)\b", re.I)
CUT = re.compile(r",|\s[-–—|]\s|\(|\[|\s[–—]|\bwith\b|\bfor\b|\bwhite\b|\bblack\b", re.I)
GEN = re.compile(r"\(\s*(\d)(?:st|nd|rd|th)\s+gen\w*\s*\)|\b(\d)(?:st|nd|rd|th)\s+gen(?:eration)?\b", re.I)
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
    "webcam", "cam", "security", "indoor", "desktop", "pc", "computer", "tower", "new", "original", "official", "version", "global",
    "edition", "model", "series", "inch", "inches", "with", "and", "for", "of", "by", "from", "rgb", "mic", "microphone",
    "stereo", "surround", "sound", "audio", "hifi", "hi-fi", "high", "quality", "dolby", "atmos", "deep", "bass", "extra",
    "overear", "inear", "onear", "openear", "semi", "down", "multigigabit", "dualband", "triband", "nextgen", "whole",
    "resolution", "ultrahighdefinition", "or", "eos", "nas", "hdd", "pixart", "sensor", "dpi", "ngenuity", "ultralightweight",
    "membrane", "mechanical", "optical", "kailh", "pbt", "smooth", "2280", "2242", "2230", "sata", "sataiii", "foldable", "surround", "surroundsound", "drivers", "driver", "dts", "virtual",
    "spatial", "multiplatform", "platform", "mobile", "app", "multipoint", "pairing", "battery", "handsfree", "voice", "control",
    "multisensory", "hearing", "lightweight", "ultralight", "aux", "noisecancelling", "inline", "multidevice", "connectivity",
    "wrls", "wirless", "plantronics", "powered", "usbpowered", "technology", "suppression", "ensure", "sporty", "comfort", "analog", "voip", "multimedia", "wired", "w", "gamenote",
    "soundbar", "channel", "subwoofer", "projector", "projectors", "lumens", "ansi", "robot", "robotic", "vacuum", "cleaner", "mop", "plug", "bulb", "keyboard", "mouse", "combo", "mice", "console", "consoles", "handheld", "video", "game", "home", "office", "business", "personal", "ultra-slim", "thin",
    "frameless", "borderless", "adjustable", "height", "pivot", "speakers", "built-in", "builtin", "mfp", "scanner", "copier",
    "fax", "print", "scan", "copy", "network", "ethernet", "port", "ports", "lan", "wan", "ax", "ac", "be",
}
COLOURS = {"black", "white", "silver", "gold", "grey", "gray", "blue", "green", "pink", "red", "purple", "orange", "yellow",
           "beige", "cream", "midnight", "starlight", "graphite", "navy", "teal", "mint", "lavender", "violet", "rose", "titanium",
           "natural", "sand", "olive", "camo", "brown", "coral", "sky", "ivory", "phantom", "clear", "transparent", "onyx", "obsidian"}
UNITS = re.compile(r"^\d+(?:\.\d+)?(?:rpm|mah|w|wh|gb|tb|mb|mbps|gbps|ghz|hz|mp|k|p|ms|mm|cm|m|v|a|db|h|hrs?|nits|ppm|dpi|x|in|inch|fps|ch)$")
PRINTER_MODEL = re.compile(r"^\d{3}[a-z]{1,3}$|^1\d{3}[a-z]$")          # Neverstop 1000a; HP Laser 107w, 150a, 135w: models, not watts or amps
HP_SKU = re.compile(r"^(?=.*\d[a-z]{1,2}\d)[0-9a-z]{5,7}(?:a|b|c|aa|ab)$")   # "Y0F71A", "499M6A": HP's stock numbers, not the model
SPEED = re.compile(r"^(?:ax|ac|be|ad|n)\d{3,5}$")                                # "AX3000": a speed class many routers share
SUFFIX = {"pro", "max", "plus", "ultra", "lite", "mini", "se", "x", "s", "e", "i", "fe", "nc", "anc", "air", "neo", "go", "slim",
          "oled", "digital", "disc", "ii", "iii", "iv", "v", "mark", "elite", "core", "gt", "open", "clip", "studio", "beam", "free", "lightspeed", "hero", "superlight", "professor"}
CODE = re.compile(r"^(?=.*[a-z])(?=(?:.*\d){2})[a-z0-9]{5,}$")                     # a maker's code: letters and 2+ digits


OWN_NOT = {
    "peripheral": re.compile(r"\b(mouse\s?pads?|mousepad|desk\s?mat|wrist\s+rest|keycaps?|keyboard\s+(?:cover|protector|skin|sticker|film)|"
                             r"cable|adapter|receiver|dongle|batter(?:y|ies)|charger|stand|bag|case|sleeve|sticker|replacement|spare|"
                             r"refurb\w*|used|open\s?box|switch(?:es)?\s+(?:pack|set)|skates|feet|for\s+ipad|for\s+(?:galaxy\s+)?tab|"
                             r"headset|kit|bundle|for\s+(?:iphone|samsung))\b", re.I),
    "tabletacc": re.compile(r"\b(tips?|nibs?|replacement|spare|cable|adapter|charger|holder|sleeve|grip|cap|film|protector|glass|"
                            r"skin|sticker|refurb\w*|used|compatible|for\s+iphone|loop|pouch)\b", re.I),
    "pcpart": re.compile(r"\b(cable|riser|bracket|holder|support|backplate|waterblock|cooler|fan|thermal|paste|case|bundle|refurb\w*|"
                         r"used|open\s?box|laptop|notebook|desktop|gaming\s+pc|all[\s-]*in[\s-]*one|monitor|kit)\b", re.I),
    "projector": re.compile(r"\b(screen|mount|bracket|ceiling|lamp|bulb|remote|bag|case|cable|adapter|stand|tripod|pointer|presenter|"
                            r"refurb\w*|used)\b", re.I),
}


MAC_OR_PC = re.compile(r"\b(mac\s?mini|mac\s?studio|imac|macbook|ipad|iphone|\d+[\s‑-]*core\s+(?:cpu|gpu)|mini\s?pc|tower|all[\s-]*in[\s-]*one|"
                       r"thinkcentre|optiplex|prodesk|veriton|ideacentre|expertcenter)\b", re.I)


LAPTOP_SPECS = re.compile(r"\b(ssd|nvme|storage|ips|oled|fhd\+?|wuxga|\d{2,3}\s*hz|loq|rog\s+(?:strix|zephyrus|flow)\s+[gsx]\d{2}|"
                          r"tuf\s+gaming\s+[af]\d|legion|thinkbook|thinkpad|victus|omen|nitro\s+v|predator\s+helios|katana|cyborg|zephyrus)\b|\d{2}(?:\.\d)?\s*(?:\"|”|″|-?\s*inch)", re.I)


# "... Console with Wireless Controller" names what every console has in the box; "with 2 controllers" is a bundle
WITH_PAD = re.compile(r"\b(?:with|and|\+|&)\s+(?:(?:a|an|one|1|its)\s+)?(?:dualsense\s+)?wireless\s+controller\b(?!\s+\w*\s*(?:for|case|charg))", re.I)
DESKTOP_CPU = re.compile(r"\bdesktop\b(?=\s*(?:\d+\w*\s+gen\w*\s+)?(?:processor|cpu)\b)", re.I)   # "Ryzen 7 9800X3D Desktop Processor" is a part
# what a mouse or a drive works WITH: "for PC/Mac/Laptop", "Laptop Internal Hard Drive"
WORKS_WITH = re.compile(r"\b(?:pc|mac|windows|desktop|multi-device)s?\s*(?:[/,&]|and|or)\s*(?:mac\s*[/,&]\s*)?(?:laptops?|notebooks?|chromebook|macbook)\b|"
                        r"\bfor\s+(?:laptops?|notebooks?|chromebook|macbook)\b|"
                        r"\blaptops?\s+(?=internal|hard\s+drive|\(3d|/?\s*ssd)|\bswift\s+gr[ae]y\b", re.I)        # Logitech's colour "Swift Grey", not Acer's laptop


def _pcpart_ok(title: str) -> bool:
    """A graphics card or a processor on its own (not a computer that has one)."""
    return bool(GPU_CHIP.search(title) or laptop.cpu_of(title)) and not re.search(r"\b\d+\s*gb\s*(?:ddr\d\w*\s*)?ram\b.*\bssd\b", title, re.I)


def category(title: str) -> str | None:
    """Which of the new categories a title says it is (None when it is none of them, or an add-on such as a case)."""
    title = DESKTOP_CPU.sub(" ", title)
    if re.search(r"\b(?:mouse|keyboard|ssd|solid\s+state)\b", title, re.I):
        title = WORKS_WITH.sub(" ", title)
    head = CUT.split(title)[0]                     # add-ons say so up front ("Case for AirPods"); "... with stand" is the product
    for cat, says in SAYS:
        if says.search(title):
            if cat == "console":
                title = WITH_PAD.sub(" ", title) if CONSOLE_BOX.search(title) else title
                m = says.search(title)
                # "... for PC & PS5" is an add-on; "PlayStation Portal Remote Player for PlayStation 5" is the product
                if CONSOLE_NOT.search(title) or CONSOLE_PART.search(title[:m.start()]) or not (CONSOLE_SAYS.search(title) or len(re.findall(r"\w+", title[:m.start()])) <= 2):
                    continue                       # "Spider-Man 2 PS5" is a game, "Headset for PS5" a headset
                return cat
            if cat in ("peripheral", "tabletacc", "pcpart", "projector"):
                if cat == "peripheral" and (COMPUTER.search(title) or laptop.looks_like_laptop(title)):
                    continue                       # a laptop's "Backlit Keyboard" is the laptop
                if cat == "tabletacc" and (PHONE_SIGNS.search(title) or re.search(r"\b\d+\s*gb\b", title, re.I)):
                    continue                       # "Galaxy S26 Ultra 256GB ... S Pen Included" is the phone
                card = cat == "pcpart" and re.search(r"\bgraphics?\s+card\b", title, re.I) and not laptop.says_laptop(title) and not laptop.cpu_of(title)
                if cat == "pcpart" and not card and (laptop.looks_like_laptop(title) or LAPTOP_SPECS.search(title)):
                    continue                       # "ThinkBook 16 ... Intel Core Ultra 7 processor" is a laptop
                if cat == "pcpart" and (OWN_NOT["pcpart"].search(title) or MAC_OR_PC.search(title) or not _pcpart_ok(title)):
                    continue                       # a computer that names its processor ("Mac mini ... 12-Core CPU") is not a part
                if cat == "peripheral" and re.search(r"\b(?:MK|KM)\s?\d{3,4}", title):
                    head = re.sub(r"\bkit\b|\b(?:unifying\s+)?usb[\s-]receiver\b", " ", head, flags=re.I)   # "Logitech Wireless Kit MK220"
                if OWN_NOT[cat].search(head):
                    return None
                return cat
            if cat == "desktop" and re.search(r"\b(?:sound\s?bars?|speakers?)\b", head, re.I) and not laptop.cpu_of(title):
                continue                           # "RGB 2.0 ... Soundbar ... Desktop Speakers" are speakers
            if cat == "desktop" and re.search(r"\b(?:keyboard|mouse)\b", head, re.I) and not laptop.cpu_of(title) and not re.search(r"\d\s*[gt]b\b|thinkcent", title, re.I):
                continue                           # "Logitech MK120 Desktop Keyboard and Mouse"
            if cat == "storage" and re.search(r"\bmi-?fi\b|\brouter\b", head, re.I):
                continue                           # a pocket router with a memory card slot
            if cat == "smarthome" and re.search(r"\brobot", head, re.I):
                head = re.sub(r"\bcombo\b|\b(?:vacuum|mop)\s+(?:and\s+mop\s+)?clean(?:er|ing)\b|\bcleaner\b", " ", head, flags=re.I)
            if cat != "desktop" and COMPUTER.search(title):
                continue                           # a laptop's "512GB SSD" or "Dolby speakers" is not a drive or a speaker
            if cat == "monitor" and (BIG_SCREEN.search(title) or PHONE_SIGNS.search(title)):
                continue                           # "Samsung QLED 75-inch Monitor" is a TV; "144Hz FHD+ ... 8GB RAM" a phone
            if cat == "smarthome" and re.search(r"\b(keyboard|mouse|monitor|laptop|tablet|phone|dual\s+sim)\b|\dgb\s+ram\b", title, re.I):
                continue                           # a keyboard "with OLED Smart Display" is a keyboard
            if cat == "speaker" and re.search(r"\b(built[\s-]*in|with|w/?)\s+(?:stereo\s+)?speakers?\b", title, re.I):
                continue                           # a monitor or TV "with built-in speakers" is not a speaker
            if cat == "printer":                   # "Ink Tank Printer", "DeskJet Ink Advantage": the printer, not a bottle of ink
                head = re.sub(r"\bink[\s-]*(?:tank|advantage|jet)\b|\b(?:full\s+)?ink\s+included\b", " ", head, flags=re.I)
            if cat == "monitor":
                head = re.sub(r"\b(?:\w+[\s-]+)?adjust\w*\s+stand\b|\bergo\s+stand\b", " ", head, flags=re.I)
            if cat == "router":
                head = re.sub(r"\b(ceiling|wall|desk)\s+mount\b", " ", head, flags=re.I)   # an access point's own mount
            if NOT_IT.search(head) or re.search(r"\bcases?\b", head, re.I) and cat in ("audio", "storage", "camera") \
                    or cat == "audio" and re.search(r"\b(case|cover|skin|sleeve)\s+for\b", title, re.I):   # "BP005 - AirPods Case for ..."
                return None
            if cat == "printer" and re.search(r"\b(cartridges?|toners?|ink\s+bottles?|drum\s+unit|ribbon|printhead|maintenance\s+box)\b", title, re.I):
                return None                        # "Canon PG-440XL High Yield Black Ink Cartridge"
            if cat == "storage" and re.search(r"\b(i[3579]|ram|laptop|desktop|motherboard|mainboard|[bhxz]\d{3}m?)\b", title, re.I):
                continue                           # "HP 250 G9 i5 8GB 512GB", "MSI B550M Pro": not a drive
            if cat == "camera" and re.search(r"\b(film\s+pack|single\s+pack|twin\s+pack|\d+\s*sheets?|photo\s+paper)\b|instant\s+film(?!\s+camera)", title, re.I):
                return None                        # Instax film packs are not cameras
            if cat == "camera" and PHONE_CAMERA.search(title):
                return None
            return cat
    # "TWS" alone ("JBL Live Pro 2 TWS") means earbuds; next to "speaker" it means two speakers paired
    if re.search(r"\btws\b", title, re.I) and not NOT_IT.search(head) and not COMPUTER.search(title):
        return "audio"
    return None


def looks_like_gadget(title: str) -> bool:
    return category(title) is not None


def _brand(title: str) -> tuple[str, str] | None:
    if re.search(r"\bhyperx\b", title, re.I):
        return "HyperX", "HyperX"                 # "HP HyperX Alloy Origins": HyperX is the product's maker name
    m = BRAND.search(title)
    return (_B[m.group(1).lower()], m.group(1)) if m else None


def _words(head: str) -> list[str]:
    head = GEN.sub(lambda m: f" {m.group(1) or m.group(2)} ", head)
    head = re.sub(r"\b4g\s+lte\b", " ", head, flags=re.I)                                             # a router's or camera's network, not its name
    head = re.sub(r"\bultra\s+(gear|wide|fine|sharp)\b", r"ultra\1", head, flags=re.I)            # LG "Ultra Gear"
    if re.search(r"\bhaing\b", head, re.I):
        head = re.sub(r"\bHI-(?=[A-Z0-9])|\b2\.4\s*G(?:Hz)?\b", " ", head, flags=re.I)             # "HI-GM700" and "GM700" are one mouse
    head = re.sub(r"\bultimate\s+ears\b", " ", head, flags=re.I)
    # drive and keyboard specs are not names: "M.2", "Gen 4x4", "Read up to 520MB", "3D NAND", "SSDNow", "Western Digital"
    head = re.sub(r"\bm\.2\b|\bgen\s?\d(?:\s?x\s?\d)?\b|\bread\s*(?:up\s*to\s*)?\d+\s*(?:mb/?s?)?|\bup\s+to\b|\b3d\s*(?:nand)?\b|"
                  r"\bssdnow\b|\bwestern\s+digital\b|\bwestern\b", " ", head, flags=re.I)
    head = re.sub(r"\b([a-z]\d+)(pro|max|plus|ultra|lite|mini|se)\b", r"\1 \2", head, flags=re.I)   # "X82PRO" = "X82 Pro"
    head = re.sub(r"\b([a-z]+\d+[a-z]*?)rgb\b", r"\1", head, flags=re.I)                           # "K642WGORGB" = "K642WGO"
    head = re.sub(r"\bmark\s+(ii|iii|iv|v|\d)\b", r"\1", head, flags=re.I)                 # "R6 Mark II" = "R6 II"
    head = re.sub(r"\bwi-?fi\s*(?:5|6e?|7)\b", " ", head, flags=re.I)                 # "WiFi 6 plus AX3": the Wi-Fi version                    # Logitech's speaker brand, not the name
    head = re.sub(r"\ball[\s-]*in[\s-]*one\b", " ", head, flags=re.I)
    head = re.sub(r"\b(smart|ink|eco)\s*tank\b", r"\1tank", head, flags=re.I)              # "Smart Tank 581" is one name
    head = re.sub(r"(?<![\w.])\d+\.\d+\b", " ", head)                                # "PCIe 4.0", "Bluetooth 5.3", "23.8 inch"
    head = re.sub(r"(?<![\w.])\d{2}\s*(?:\"|″|”|''|-?\s*inch(?:es)?\b)", " ", head, flags=re.I)  # the screen size has its own field
    head = re.sub(r"-(?=\d+\s*(?:lumens?|lm|ansi)\b)", " ", head, flags=re.I)          # "PA503S-3600 Lumens"
    # Ezviz "CS-H6c-R105-1J4WF" = H6c R105 (R105 and R200 are two cameras); Dahua "DH-IPC-HFW2831T" = HFW2831T
    head = re.sub(r"\bCS-([A-Z0-9]+)-R\d{3}-[A-Z0-9]+\b", r"\1", head, flags=re.I)
    head = re.sub(r"\b(?:DH-)?(?:IPC|HAC)-(?=[A-Z]{1,4}\d)", "", head, flags=re.I)
    head = re.sub(r"\bmr\.([a-z0-9]{4,6})\.\d{3}\b", r"\1", head, flags=re.I)              # Acer "MR.JPV11.002" = JPV11
    head = re.sub(r"\b([a-z]{2})-([a-z]\d{2})\b", r"\1\2", head, flags=re.I)                 # Epson "EB-E10", "EB-X49"
    head = re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9]{3,})", "", head, flags=re.I)          # "WH-1000XM6" -> "WH1000XM6"
    head = re.sub(r"(?<=[a-z0-9]{4})-[a-z]{1,2}\b", "", head, flags=re.I)            # "27GR75Q-B": a colour letter
    head = re.sub(r"\b(?!eb[a-z]\d|j[a-z]{2}\d)([a-z]{3,})(\d+)\b", r"\1 \2", head, flags=re.I)              # "Buds3" -> "Buds 3", "Flip6" -> "Flip 6"
    head = re.sub(r"\b(\d+)(pro|max|plus|ultra|lite|mini|se)\b", r"\1 \2", head, flags=re.I)
    return re.findall(r"[a-z0-9+]+", head.lower())


CODE_ANYWHERE = {"printer", "monitor", "router", "storage", "camera", "projector", "tabletacc"}   # maker codes these shops always copy from the box


def _generic(w: str, cat: str = "") -> bool:
    if cat == "printer" and PRINTER_MODEL.match(w):
        return False
    return w in SKIP or bool(UNITS.match(w) or SPEED.match(w))


def _model(title: str, brand_word: str, cat: str) -> str | None:
    head = CUT.split(GEN.sub(lambda m: f" {m.group(1) or m.group(2)} ", re.sub(r"^\s*\W+", "", title)))[0]
    words = _words(head)
    bw = _words(brand_word)
    at = next((i for i in range(len(words)) if words[i:i + len(bw)] == bw), None)
    if at is None:
        return None
    rest = words[at + len(bw):]
    while rest and (_generic(rest[0], cat) or rest[0] in _B):
        rest = rest[1:]
    if cat == "monitor" and (exact := _exact_monitor(title, brand_word.lower())):
        return exact
    codes = [w for w in rest if _is_code(w) and not (brand_word.lower() == "hp" and cat == "printer" and HP_SKU.match(w))]
    # the maker's code also stands in brackets or at the very end: "Odyssey G6 (FG600) 27"", "Soundbar ... - HW-B450F"
    tail = re.split(r"\s[-–—|]\s", title)[-1] if re.search(r"\s[-–—|]\s", title) else ""
    last = re.findall(r"[A-Za-z0-9-]+", title)[-1:]                     # "... Quantum Dot LS27DG612SMXUE"
    # a code at the very end is trusted for monitors and Samsung's own codes only: shops put their stock codes there
    # ("- JBLPBSTAGE320U", "AX6G1AA"), which differ per colour and per shop
    ends = [w for part in [tail] + last for w in _words(part) if _is_code(w) and (cat in ("monitor", "router") or SAMSUNG_CODE.match(w))]
    boxed = [w for part in re.findall(r"\(([^)]{3,30})\)", title) for w in _words(part) if _is_code(w)] + ends
    boxed += [w for part in re.findall(r"\(([a-z]{1,2}\d{3}[a-z]?)\)", title, re.I) for w in _words(part)]   # "(F320)"
    boxed = [w for w in boxed if not ((brand_word.lower() == "hp" and cat == "printer" or brand_word.lower() == "poly") and HP_SKU.match(w))]
    if not codes and not boxed and cat in ("printer", "router"):
        # "HP Color LaserJet Pro MFP(print,scan) Wireless 3303sdw (499M6A)": the model sits anywhere in the title
        boxed = [w for w in _words(title) if _is_code(w) and not (brand_word.lower() == "hp" and cat == "printer" and HP_SKU.match(w))]
    if not codes and not boxed and cat == "monitor":
        anywhere = {w for w in _words(title) if _is_code(w) and len(w) > 4 and not re.search(r"hz|bit", w)
                    and (brand_word.lower() not in ("samsung", "huawei") or re.match(r"[scfu]\d{2}[a-z]{2}", w))}            # "Monitor 27-inch 200Hz \ DHI-LM27-E331Y / Warranty": the only code there is
        boxed = list(anywhere) if len(anywhere) == 1 else []
    code = codes[0] if codes else boxed[0] if boxed else None
    if code and (cat in CODE_ANYWHERE or not rest or rest[0] == code or cat in ("speaker", "powerbank") or not codes and boxed):
        base = _samsung_code(code, cat) if brand_word.lower() == "samsung" else code
        if rest and rest[0] == code:                                  # "S1000 Plus", "G502 X Lightspeed": the version words after it
            for w in rest[1:]:
                if w not in SUFFIX:
                    break
                base += f" {w}"
        if cat == "monitor" and brand_word.lower() == "msi":
            base = re.sub(r"^mag(?=\d)", "", re.sub(r"^(\d{3}[a-z]{2,4})(e\d{2})$", r"\1", base))   # "MAG274UPF", "342CQRF-E20"
            base += _msi_panel(title)
        if cat == "monitor" and brand_word.lower() == "xiaomi" and base == "g27qi" and (y := re.search(r"\b(20[2-3]\d)\b", title)):
            base += f" {y.group(1)}"
        return base + _variant_words(title, cat)      # "WH1000XM6", "M211DW", "27GR75Q", "FG600"
    if cat == "monitor" and brand_word.lower() in SHORT_MONITOR:
        short = [w for w in rest[:4] if SHORT_MONITOR[brand_word.lower()].match(w)]
        if short and not _generic(short[0], cat):
            after = rest[rest.index(short[0]) + 1:][:1]              # "L22e-20" (60Hz) and "L22e-40" (75Hz): the generation
            gen = f" {after[0]}" if brand_word.lower() == "lenovo" and after and re.fullmatch(r"[1-5]0|4e", after[0]) else ""
            if brand_word.lower() == "lenovo" and re.fullmatch(r"[a-z]\d{2}", short[0]) and not gen:
                return None                                              # "Lenovo G27": G27-10, G27-20 and G27-30 are three screens
            if brand_word.lower() == "lenovo" and re.fullmatch(r"2\d[a-z]", short[0]) and re.search(r"\blegion\s+pro\b", title, re.I):
                short[0] = "pro " + short[0]                             # Legion Pro 27Q-10 is OLED (455), Legion 27Q-10 is IPS (205)
            if brand_word.lower() == "xiaomi" and (y := re.search(r"\b(20[2-3]\d)\b", title)):
                gen = f" {y.group(1)}"                                   # the A24i (69) and the A24i 2026 (89) sell side by side
            return short[0] + (_msi_panel(title) if brand_word.lower() == "msi" else gen)
    if cat == "monitor":
        return None                       # "Odyssey G6 27"" is five different screens (OLED or not, flat or curved)
    out: list[str] = []
    for i, w in enumerate(rest):
        numbered = any(ch.isdigit() for ch in " ".join(out))
        if cat == "storage" and not out and brand_word.lower() in ("wd", "western digital") and w in DRIVE_LINES:
            kind = {m.lower() for m in re.findall(r"\b(ssd|hdd)\b|\b(?:hard\s+d(?:rive|isk))\b", title, re.I)}
            kind = "ssd" if "ssd" in kind or re.search(r"\bnvme\b", title, re.I) else "hdd" if kind else ""
            if kind:                                # "WD Purple 2TB Surveillance HDD": the colour is the line
                return f"{w}{f" {rest[i + 1]}" if rest[i + 1:i + 2] in (["pro"], ["plus"]) else ""} {kind}"
        if w in COLOURS or re.fullmatch(r"[a-z]\d{7}", w):
            break                                   # a colour, or a stock number ("Space One A3035021")
        if len(out) >= 3 and not numbered and not any(ch.isdigit() for ch in w) and w not in SUFFIX:
            break                                   # a words-only name ends at three words ("Space One Pro"), unless a number follows
        # "Huntsman Mini", "One 2 Mini", "Apex 9 Mini" are other keyboards and mice than the full ones (2026-11-22);
        # "Wireless Mini Mouse", "USB Mini Receiver" only describe it
        keep_mini = w == "mini" and cat == "peripheral" and bool(out) and rest[i - 1] == out[-1]
        # "Redmi Buds 8 Active" (25) and "Buds 6 Play" (10) are other earbuds than "Buds 8" (49) and "Buds 6";
        # "Buds 3 Pro Active Noise Cancelling" only describes it (2026-11-23)
        nxt = rest[i + 1] if i + 1 < len(rest) else ""
        if (cat == "audio" and w in ("active", "play") and numbered and rest[i - 1] == out[-1]
                and not nxt.startswith(("noise", "nc", "anc", "cancel", "hybrid"))):
            out.append(w)
            continue
        if cat == "audio" and w == "light" and numbered and rest[i - 1] == out[-1]:
            out.append("lite")                       # "Redmi Buds 4 Light" is the Buds 4 Lite (same 17 JOD)
            continue
        if _generic(w, cat) and not keep_mini:
            if numbered:
                break                                                 # "Flip 6 Portable ...": the name has ended
            continue
        if w in _B:
            continue
        if out and w in codes and (len(w) > 6 or numbered):
            break                                                     # "Space One A3035021": the box code after the name
        # a short code right after a line word is the model number: "Tune 245NC", "Live 770NC" (2026-11-21)
        if numbered and (w not in SUFFIX and not w.isdigit() or w.isdigit() and (out[-1].isdigit() or len(w) >= 3)):
            break                                                     # after the number only "Pro", "Max"... belong to it
        out.append(w.replace("+", "plus"))
        if len(out) >= 5:
            break
    line = " ".join(out).strip()
    if not line or re.fullmatch(r"[\d\s]+", line) and not (cat == "powerbank" and re.fullmatch(r"\d{3}", line)):
        return None                                                   # "Dahua 27": which one?
    # words only: a power bank or a drive has its capacity beside it ("IronWolf Pro 4TB"); a headphone or speaker needs two
    # words, or one real model word ("Skullcandy Hesh"), never a generic one
    if not re.search(r"\d", line) and not (cat in ("powerbank", "storage") or cat in ("audio", "speaker", "peripheral", "camera")
                                           and (len(out) >= 2 or len(line) >= 3 and line.isalpha())):
        return None                                                   # "JBL Wireless Speaker": which one?
    if not re.search(r"\d", line) and cat in ("speaker", "audio", "peripheral"):
        # "Xtrike Me Dream My Life ..., SK-503" and "... with Backlight SK-612" are two speakers under one line name:
        # one hyphenated maker code anywhere in the title is the model (2026-11-22)
        hy = {c.lower().replace("-", "") for c in re.findall(r"(?<![\w-])([A-Za-z]{1,3}-\d{3,4}[A-Za-z]?)(?![\w-])", title)}
        if len(hy) == 1 and _is_code(next(iter(hy))):
            return next(iter(hy)) + _variant_words(title, cat)
    if not re.search(r"\d", line):
        # words only, and the maker's own code at the end says which one (2026-11-25)
        maker = brand_word.lower()
        if cat == "speaker" and maker == "jbl" and (m := re.search(r"\bJBL(FLIP|CHARGE|CLIP)(\d)(?=[A-Z])", title)):
            return f"{m.group(1).lower()} {m.group(2)}"                # "JBL Portable Waterproof ... Flip 7 – JBLFLIP7WHTAM"
        if cat == "speaker" and maker == "sony" and (m := re.search(r"\bSRS-ULT([1357])0\b", title)):
            return f"ult field {m.group(1)}"
        if cat == "audio" and maker == "sony" and (m := re.search(r"\bW([FH])-(C\d{3}N?)\b", title)):
            return f"w{m.group(1)}{m.group(2)}".lower()
        if cat == "audio" and maker == "meetion" and (m := re.search(r"\bMT-(HP\d{3}U?)\b", title)):
            return m.group(1).lower()
        if cat == "audio" and maker == "wiwu" and (m := re.search(r"\b(T\d{2})\s*$", title)):
            return m.group(1).lower()
        if cat == "audio" and line == "aeroclip" and maker in ("anker", "soundcore"):
            return "aeroclip clip"                                     # Anker makes one AeroClip: the same name with and without "Clip-On"
        if maker == "remax" and len(out) == 1 and (m := re.search(r"\b(?:RB-[A-Z]{1,2}|RPP-)\d{1,3}\b", title)):
            return " ".join(_words(m.group(0))) + _variant_words(title, cat)
        # "Havit Gamenote MS969WB" (14) and "Gamenote MS963WB" (25): the one code after the line name is the model (2026-11-24)
        if cat == "peripheral" and len(set(codes)) == 1:
            named = re.sub(r"^([a-z]\d{3}[a-z]{2,})rgb$", r"\1", codes[0])
            if re.fullmatch(r"(?=.{4,7}$)[a-z]{1,2}\d{3}[a-z]*", named):
                return named + _variant_words(title, cat)
        # "JBL Tune ANC Wireless Over Ear Headphones, Purple - JBLT770NCPUR": JBL's code says which Tune (2026-11-24)
        if cat == "audio" and brand_word.lower() == "jbl" and (m := re.search(r"\bJBLT(\d{3})(BT|NC)", title)):
            return f"tune {m.group(1)}{m.group(2).lower()}" + _variant_words(title, cat)
    # "JBL Headphone Junior 320, Bluetooth - JBLJR320BTBLU" is the Junior 320BT (54.99), not the wired Junior 320 (32):
    # JBL's own stock code says it (2026-11-23)
    if cat == "audio" and brand_word.lower() == "jbl" and (n := re.search(r"(\d{1,4})$", line)) and \
            re.search(rf"\bJBL[A-Z]*{n.group(1)}BT", title):
        line += "bt"
    return line + _variant_words(title, cat)


# codes of 3-4 characters, trusted only for these monitor makers: MSI "MAG 272F", Xiaomi "A24i", Lenovo "R24e"
SHORT_MONITOR = {"msi": re.compile(r"\d{3}[a-z]{1,4}$"), "xiaomi": re.compile(r"(?:pro)?[ag]?\d{2}q?i$|[ag]\d{2}q?i$"),
                 "lenovo": re.compile(r"[a-z]\d{2}[a-z]?$|2\d[a-z]$"), "koorui": re.compile(r"gn\d{2}$")}


# Samsung's short names and the code they stand for: the same shops write both, with the same specs and prices
# (2026-11-25). Others (G60F) stay unread: one short name can hide several screens
SAMSUNG_SHORT = {"g50f": "fg502e", "g53f": "fg532", "g40h": "hg402", "g55c": "cg552", "g55t": "g55t", "g35t": "g35t", "g60sf": "fg602",
                 "g70d": "dg702", "g80hf": "hg806"}
SAMSUNG_LONG = re.compile(r"\bL?[SCFU](\d{2})([A-Z]{1,2}\d{3})([A-Z]?)[A-Z]{0,9}\b")
# the version stands after a dash and makes another screen: "L22e-20" (60Hz) and "L22e-40" (75Hz), "T27QD-4v", "Legion 27Q-10"
LENOVO_VERSION = re.compile(r"\b(?:[A-Z]\d{2}[A-Z]{0,2}|[2-4]\d[A-Z]{0,2})[-‑–](?:[1-6]0|4[EV])\b", re.I)
DRIVE_LINES = {"purple", "red", "gold"}   # WD Blue, Green and Black are sold as several drives (2.5", 3.5", M.2): never guessed


def _exact_monitor(title: str, maker: str) -> str | None:
    """Monitor makers whose code is certain wherever it stands in the title."""
    if maker == "lenovo" and (m := LENOVO_VERSION.search(title)):
        name = re.sub(r"[-‑–]", " ", m.group(0).lower())
        # Legion Pro 27Q-10 is OLED (455), Legion 27Q-10 is IPS (205)
        return ("pro " if re.search(r"\blegion\s+pro\b", title, re.I) else "") + name
    if maker == "samsung":
        if m := SAMSUNG_LONG.search(title):
            code, letter = m.group(2).lower(), m.group(3).lower()
            if code == "d300" and letter == "n":
                return None                                        # S22D300NY (2014) is not the D300 of 2024
            return code + letter if code == "fg502" else code      # FG502E is IPS (179), FG502S is OLED (379)
        if re.search(r"\bodyssey\b", title, re.I) and (m := re.search(r"\b(?:\d{2})?(" + "|".join(SAMSUNG_SHORT) + r")\b", title, re.I)):
            return SAMSUNG_SHORT[m.group(1).lower()]
    return None


def _msi_panel(title: str) -> str:
    """MSI sells one name with several panels: "272QP QD-OLED X24" is 240Hz (499), "X50" 500Hz (719); "PRO MP251" is 100Hz,
    "MP251 E2" 120Hz, "MP251 E14L" 144Hz (2026-11-25)."""
    m = re.search(r"\b(?:MAG|MPG|MEG|PRO|Modern|MSI)\b[^,|]{0,40}?[\s-]([EX]\d{1,2}[A-Z]{0,2})(?![\w-])", title, re.I)
    return f" {m.group(1).lower()}" if m else ""


NOT_CODE = re.compile(r"^([a-z]\d{7}|hdr\d+|\d+r|\d+x\d+p?|\d+cd|usb\d\w*|ddr\d\w*|gen\d+|wifi\d\w*|ipx?\d+|\d+(?:th|nd|rd|st)|\d{3,4}p\d*|"
                      r"hdmi\d\w*|dp\d\w*|cat\d\w*|v\d+|bt\d\w*|\d+in\d|rtx\d+|gtx\d+)$")


# makers' own codes that shops copy at the end of a title: Samsung HW-B450F soundbars and LS27FG600 monitors,
# Sony MHC-V43D / SRS-XB100 / HT-S400 audio systems
SAMSUNG_CODE = re.compile(r"^(hw[a-z]\d{3}|l[scu]\d{2}[a-z]{1,3}\d{3}|mhc[a-z]+\d{2}|srs[a-z]+\d{2,3}|ht[a-z]+\d{3})")


def _is_code(w: str) -> bool:
    return bool(CODE.match(w)) and not UNITS.match(w) and not SPEED.match(w) and not NOT_CODE.match(w)


def _samsung_code(code: str, cat: str = "") -> str:
    """'LS27FG600SMXUE' and '(FG600)' are the same Samsung monitor: the part after the size is the model."""
    m = re.match(r"^l[a-z]\d{2}([a-z]{1,3}\d{3})[a-z0-9]*$", code)
    if cat == "monitor" and not m and code not in SAMSUNG_SHORT:
        m = re.match(r"^(?!s22d300n)(?:[scfu])?\d{2}([a-z]{1,2}\d{3})[a-z0-9]*$", code)      # "S27B800P", "34BG850", "U32J590"
    return m.group(1) if m else SAMSUNG_SHORT.get(code, code)


WIRED_TWINS = {"HyperX", "Razer", "SteelSeries", "Logitech", "Corsair", "Skullcandy"}   # gaming headsets sold wired AND wireless


def _variant_words(title: str, cat: str) -> str:
    """Words that make another product of the same name: a Mono or Duo headset, a 2-pack mesh system."""
    extra = ""
    if cat == "audio" and (m := re.search(r"\b(mono|duo)\b", title, re.I)):
        extra += f" {m.group(1).lower()}"
    if cat == "camera" and (m := re.search(r"\bCS-[A-Z0-9]+-(R\d{3})-", title, re.I)):
        extra += f" {m.group(1).lower()}"   # Ezviz H6c R105 (16.99) and H6c R200 (21.99) are two cameras
    maker = (_brand(title) or ("", ""))[0]
    if cat == "audio" and maker in WIRED_TWINS and re.search(r"\b(headsets?|headphones?|over-?ear|on-?ear)\b", title, re.I):
        # "SLYR Pro Wired" (59 JOD) and "SLYR Pro Wireless" (99 JOD) are two headsets; "wired & wireless" says neither
        wired, wireless = re.search(r"\bwired\b", title, re.I), re.search(r"\bwireless\b", title, re.I)
        if wired and not wireless:
            extra += " wired"             # only "wired" is marked: many shops leave "wireless" out of a wireless name
    if cat == "speaker" and maker == "Meetion" and re.search(r"\bSP2011\b.*\b2\.1\b", title, re.I):
        extra += " 2.1"                   # SP2011 (7) and SP2011 2.1 with a subwoofer (16), same shop
    if cat == "audio" and maker == "Apple" and re.search(r"\bairpods\s*\(?4\b.*(?:\bANC\b|noise\s+cancel)", title, re.I) and             not re.search(r"\bwithout\b|\bnon[\s-]?anc\b|\bno\s+(?:anc|active)\b", title, re.I):
        extra += " anc"                   # AirPods 4 (100) and AirPods 4 with noise cancelling (150) are two products
    if cat == "peripheral" and re.search(r"\bMS969WB\b.*\bKeyd\b", title, re.I):
        extra += " keyd"                  # Havit MS969WB (14) and its Keyd edition (33), same shop
    if cat == "audio" and maker == "HyperX" and re.search(r"\bstinger\s+3\b.*\bwireless\b", title, re.I):
        extra += " wireless"              # Cloud Stinger 3 (49) and Stinger 3 Wireless (79), same shop
    if cat == "peripheral" and maker == "Machenike" and re.search(r"\bM7\s+Pro\s+Wired\b", title, re.I):
        extra += " wired"
    if cat == "peripheral" and maker == "Lenovo" and re.search(r"\bM120\s?Pro\s+Wired\b", title, re.I):
        extra += " wired"                 # M120 Pro is sold wired (4) and wireless (7) by the same shop (2026-11-24)
    if cat == "peripheral" and (m := re.search(r"\b([2-5])\s*-?in-?\s*1\b[^,]{0,40}\bset\b", title, re.I)):
        extra += " set"                   # "K552-BA-2 3-in-1 Gaming Essentials Set" is a keyboard, mouse and pad together
    if m := re.search(r"\b([2-9])\s*-?\s*(?:pack|pcs|pieces)\b|\bpack\s+of\s+([2-9])\b", title, re.I):
        extra += f" {m.group(1) or m.group(2)}pack"
    return extra


INCH = re.compile(r"(?<![\d.])((?:1[5-9]|[2-4]\d)(?:\.\d)?)\s*(?:\"|″|''|”|-?\s*inch(?:es)?|in\b|انش|إنش)", re.I)
CAPACITY = re.compile(r"(?<![\d.])(\d{1,4})\s*(gb|tb)\b", re.I)
MAH = re.compile(r"(?<![\d.])(\d{1,2}[,.]?\d{3}|\d{1,2})\s*(k\b|mah)", re.I)


def _size(cat: str, title: str) -> int | None:
    if cat == "monitor":
        # LG and Twisted Minds start the code with the size: "24GS50F", "TM27FHD165IPS"
        m = INCH.search(title) or re.search(
            r"\b(?:LG\s+|TM[AC]?)(2[2-9]|3[0-9]|4[0-9])[A-Z]{2}|\bDahua\s+LM(2[2-9]|3\d)-|\bDell\b.*\b(?:SE|E|P|S|U)(2[0-9]|3[0-9])\d{2}[A-Z]|"
            r"\bAsus\s+VG(2[457]|32)\d|\bXiaomi\b.*\b[AG](2[47]|3[24])Q?i\b", title, re.I)
        # 23.8" is sold as "24-inch" by one shop and "23.8"" by another: rounded, both read 24 (31.5 -> 32, 24.5 -> 25)
        return int(float(next(x for x in m.groups() if x)) + 0.5) if m else None
    if cat in ("storage", "console"):
        title = re.sub(r"\b\d+(?:\.\d+)?\s*Gb(?:/s|ps)", " ", title, flags=re.I)        # "SATA 6 Gb/s" is the speed
        vals = {int(n) * (1024 if u.lower() == "tb" else 1) for n, u in CAPACITY.findall(title)}
        if len(vals) != 1:
            return None if cat == "storage" else 0
        n = vals.pop()
        return n // 1000 * 1024 if cat == "console" and n in (1000, 2000) else n       # "1000GB" written for 1TB
    if cat == "powerbank":
        m = MAH.search(title)
        if not m:
            return None
        n = int(re.sub(r"\D", "", m.group(1)))
        return n * 1000 if m.group(2).lower() == "k" or n < 100 else n
    return 0


CONSOLES = [  # (pattern, maker, family words); the first that matches names the console
    (r"playstation\s*portal|ps\s?5?\s?portal", "Sony", "playstation portal"),
    (r"(?:playstation|ps)\s*5\s*pro|ps5\s*pro", "Sony", "playstation 5 pro"),
    # the Slim (CFI-20xx, CFI-21xx) is another machine than the first PS5, at another price (owner 2026-11-25)
    (r"(?:playstation|ps)\s*5(?=.*\b(?:slim|cfi-?2[01]\d\d)\b).*\bdigital", "Sony", "playstation 5 slim digital"),
    (r"(?:playstation|ps)\s*5.*\b(?:slim|cfi-?2[01]\d\d)\b", "Sony", "playstation 5 slim"),
    (r"(?:playstation|ps)\s*5.*\bdigital", "Sony", "playstation 5 digital"),
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
SPEC_CODE = re.compile(r"\b[a-z]+\d+[a-z]+\d*\b|\b[a-z]\d{3,}[a-z]*\b|\b\d{4,5}(?:g|f|x|k|kf|h|hx|u|t|x3d)\b", re.I)   # "X2722G", "D7VB1AT": not a memory size


def _desktop(title: str, brand: str, brand_word: str) -> str | None:
    t = title.lower()
    if brand == "Apple":
        line = "imac" if "imac" in t else "mac mini" if re.search(r"mac\s?mini", t) else "mac studio" if re.search(r"mac\s?studio", t) else None
        # "Mac mini M4 - Apple M4 Pro chip": the most exact mention wins (M4 Pro is another computer)
        chips = re.findall(r"\b(m[1-9])(?:\s*(pro|max|ultra))?\b", t)
        if not line or not chips:
            return None
        chip, tier = max(chips, key=lambda c: bool(c[1]))
        if len({c for c, _ in chips}) > 1:
            return None                                                          # two different chips named: which one?
        # the iMac M4 is sold with 8 cores (1200) and 10 cores (1440): two machines (2026-11-25)
        low = " 8c" if line == "imac" and re.search(r"\b8[\s\-‑]*core\s+cpu", t) else ""
        return f"{line} {chip}{' ' + tier if tier else ''}{low}"
    cpu = laptop.cpu_of(title)
    if not cpu:
        return None                                                               # which processor? never guessed
    words = _words(CUT.split(title)[0])
    for i in range(len(words) - 1):                                               # Dell's "QCT1250", "ECT1250": one word
        if re.fullmatch(r"[qef]c[ts]|qvt", words[i]) and re.fullmatch(r"1\d{3}|2\d{3}", words[i + 1]):
            words[i:i + 2] = [words[i] + words[i + 1], "new"]
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
    line = clean_desktop_line(" ".join(out))
    if not line or not re.search(r"\d", line):
        return None
    return f"{line} {cpu}"


DESK_SPELL = [(r"\bthink\s*cent(?:re|er)\b|\bthinkcenter\b", "thinkcentre"), (r"\bthink\s+neo\b", "thinkcentre neo"),
              (r"\bidea\s*cent(?:re|er)\b|\bideacenter\b", "ideacentre"), (r"\bexpert\s*cent(?:re|er)\b|\bexpertcentre\b", "expertcenter"),
              (r"\bneo\s?(\d{2}[a-z])\b", r"neo \1"), (r"\bv(\d{2,3})(s|t|a)\b", r"v\1\2")]
DESK_NOISE = re.compile(r"^(\d{1,2}(?:st|nd|rd|th|gen|g)|\d{1,2}|g\d{1,2}|gen\d*|i[3579]\d{4,5}\w*|\d{4,6}|pci|micro|microtower|"
                        r"minitower|mt|non|touch|hp|lenovo|dell|asus|acer|msi|\w*\d{6,}\w*)$")


def clean_desktop_line(line: str) -> str:
    """One desktop, one name: shops add generations ("13th", "12gen", "G5": the processor already says it), spell the line
    differently ("Think Centre", "Thinkcenter"), or repeat the processor code ("I512400"). Keep the series and model."""
    for pat, to in DESK_SPELL:
        line = re.sub(pat, to, line)
    words = [w for w in line.split() if not DESK_NOISE.match(w) or re.fullmatch(r"\d{1,2}", w)]
    if sum(bool(re.search(r"\d", w)) for w in words) > 1:     # "neo 50t 4": the generation; "ideacentre 5": the model
        words = [w for w in words if not re.fullmatch(r"\d{1,2}", w)]
    out = []
    for w in words:
        if not out or out[-1] != w:
            out.append(w)
    return " ".join(out)


GPU_CHIP = re.compile(r"\b(rtx|gtx)\s*-?\s*(\d{4})\s*(ti\s*super|super|ti)?\b|\b(?:radeon\s+)?rx\s*-?\s*(\d{4})\s*(xtx|xt|gre)?\b|"
                      r"\barc\s*([ab]\d{3})\b", re.I)
VRAM = re.compile(r"\b(\d{1,2})\s*gb?\b", re.I)
GPU_LINES = {   # the maker's card lines: the same chip in another line is another card at another price
    "Asus": ["rog strix", "rog astral", "tuf gaming", "tuf", "prime", "dual", "proart", "ko", "lp brk"],
    "MSI": ["suprim liquid", "suprim", "lightning", "gaming trio", "gaming x trio", "gaming x slim", "gaming slim", "gaming x", "vanguard",
            "ventus 3x", "ventus 2x", "ventus", "shadow 3x", "shadow 2x", "shadow", "inspire", "aero", "expert", "gaming"],
    "Gigabyte": ["aorus master", "aorus elite", "aorus", "gaming oc", "windforce", "eagle", "aero", "aero oc"],
    "Zotac": ["amp extreme", "amp", "twin edge", "trinity", "solid", "gaming"], "Palit": ["gamerock", "gamingpro", "jetstream", "infinity", "dual"],
    "Gainward": ["phantom", "phoenix", "ghost", "python"], "PNY": ["xlr8", "verto", "argb", "triplefan", "dualfan"], "Inno3D": ["ichill", "twin x2", "x3"],
    "Sapphire": ["nitro+", "nitro", "pure", "pulse"], "PowerColor": ["red devil", "hellhound", "reaper", "fighter"],
    "XFX": ["mercury", "quicksilver", "swift", "speedster"], "ASRock": ["taichi", "phantom gaming", "steel legend", "challenger"],
}


def _gpu(title: str, brand: str) -> str | None:
    m = GPU_CHIP.search(title)
    if not m:
        return None
    if m.group(1):
        chip = f"{m.group(1).lower()} {m.group(2)}" + (f" {m.group(3).lower().replace(' ', '')}" if m.group(3) else "")
    elif m.group(4):
        chip = f"rx {m.group(4)}" + (f" {m.group(5).lower()}" if m.group(5) else "")
    else:
        chip = f"arc {m.group(6).lower()}"
    t = re.sub(r"[-_]", " ", title.lower())
    line = next((ln for ln in GPU_LINES.get(brand, []) if re.search(r"\b" + re.escape(ln) + r"(?=\W|$)", t)), None)
    vram = {int(x) for x in VRAM.findall(title) if int(x) in (4, 6, 8, 10, 12, 16, 20, 24, 32)}
    if not line or len(vram) != 1:
        return None                                   # which card of that maker, how much memory? never guessed
    oc = " oc" if re.search(r"\boc\b|overclock", t) else ""
    return f"gpu {line} {chip} {vram.pop()}gb{oc}"


COMPUTER_MAKER = re.compile(r"^\W*(laptop\s+|notebook\s+)?(lenovo|hp|dell|acer|asus|msi|apple|huawei|microsoft|samsung|"
                            r"gigabyte|honor|xiaomi|alienware|razer)\b", re.I)


def _cpu(title: str) -> str | None:
    if GPU_CHIP.search(title) and not re.search(r"\b(processor|cpu)\b", title, re.I):
        return None
    if COMPUTER_MAKER.search(title):
        return None                               # "Lenovo V14 G5 ... Core i7 13620H" is a laptop, not a processor
    cpu = laptop.cpu_of(title)
    if not cpu:
        return None
    return f"cpu {cpu}" + (" tray" if re.search(r"\btray\b|\boem\b", title, re.I) else "")


def _tablet_acc(title: str, brand: str, word: str) -> str | None:
    t = title.lower()
    if brand == "Apple":
        if "pencil" in t:
            kind = ("pencil pro" if re.search(r"pencil\s+pro", t) else "pencil usb c" if re.search(r"usb-?\s?c", t)
                    else "pencil 2" if re.search(r"2nd|\b2\b|second", t) else "pencil 1" if re.search(r"1st|first", t) else None)
            return kind
        if re.search(r"magic\s+keyboard|smart\s+keyboard", t) and "ipad" in t:
            # "Magic Keyboard for iPad Pro (M4-M5) 13-inch - Arabic", "... iPad Pro 12.9_inch 5th": line, size, chip or generation
            line = re.search(r"ipad\s+(pro|air)", t)
            size = re.search(r"(?<![\d.])(11|12[.,_]9|13)\s*[-‑_]?\s*inch", t)
            chips = sorted(set(re.findall(r"\b(m[1-9])\b", t)))
            gen = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", t)
            if not size or not (chips or gen):
                return None
            base = "magic keyboard" if "magic" in t else "smart keyboard folio"
            which = " ".join(chips) if chips else f"gen {gen.group(1)}"
            return f"{base} ipad {line.group(1) if line else ''} {re.sub(r'[.,_]', '', size.group(1))} {which}".replace("  ", " ")
        return None
    return _model(title, word, "tabletacc")


def parse(title: str) -> tuple[str, str, str, int, int | None] | None:
    """(category, brand, family, size, ram) or None when the product cannot be told apart.
    The family starts with the category's prefix ("audio galaxy buds 3 pro", "monitor 27gr75q")."""
    if re.match(r"\W*air\s?pods\b", title, re.I):
        title = "Apple " + title                       # "AirPods Pro (2nd generation)": Apple's shops leave out the maker
    # HyperX "Cloud Earbuds III" (39) is not the "Cloud III" headset (59): "earbuds" is part of its name here
    title = re.sub(r"\b(hyperx\s+)cloud\s+earbuds\b", r"\1CloudEarbuds Earbuds", title, flags=re.I)
    cat = category(title)
    if cat is None:
        return None
    if cat == "console":
        b = _brand(title)
        if GAME.search(title) or b and b[0] not in MAKERS["console"]:
            return None                       # a game, a bag, or another maker's headset "for PS5"
        found = _console(title)
        if not found:
            return None
        brand, fam = found
        # the storage tells versions apart (PS5 825GB first model, 1TB Slim, 2TB Pro); 0 when the title does not say
        size = _size(cat, title)
        if fam == "xbox series s" and size not in (512, 1024):
            size = 512
        return cat, brand, f"console {fam}", size or 0, None
    if cat == "pcpart":
        cpu = _cpu(title)
        if cpu:
            maker = "AMD" if "ryzen" in cpu else "Intel"
            return cat, maker, f"pcpart {cpu}", 0, None
    b = _brand(title)
    if not b and cat == "tabletacc" and re.search(r"\bipad\b|apple\s+pencil|^\W*pencil\b", title, re.I):
        b = ("Apple", "apple")                         # Apple's own shops write "Magic Keyboard for iPad Pro", no maker name
    if not b or b[0] not in MAKERS[cat]:
        return None
    brand, word = b
    ram = None
    if cat == "pcpart":
        fam = _gpu(title, brand)
        if fam and re.search(r"\bdhahab\b", title, re.I):
            fam += " dhahab"                           # the gold ROG Astral: 2199, the plain one 1389 (2026-11-25)
        return (cat, brand, f"pcpart {fam}", 0, None) if fam else None
    if cat == "tabletacc":
        fam = _tablet_acc(title, brand, word)
        return (cat, brand, f"tabletacc {fam}", 0, None) if fam else None
    if cat == "desktop":
        fam = _desktop(title, brand, word)
        if not fam:
            return None
        ram, storage = laptop.ram_storage(SPEC_CODE.sub(" ", title))
        return cat, brand, f"desktop {fam}", storage or 0, ram
    fam = _model(title, word, cat)
    if not fam and cat == "smarthome" and " - " in title:
        fam = _model(re.sub(r"\s-\s", " ", title), word, cat)     # "EZVIZ Robot Vacuum & Mop Combo - RE5 Plus": the model after the dash
    if cat == "peripheral" and (brand == "Lenovo" and (m := re.search(r"\blenovo\s+(\d{3})\b", title, re.I))
                                or brand == "HP" and not fam and (m := re.search(r"\b([2-9]\d0)\b(?!\s*dpi)", title, re.I))):
        # Lenovo's plain numbers: "300 Wired Mouse" (2.5), "300 Combo" (12), "400 Wireless Mouse" (9)
        what = "combo" if re.search(r"\bcombo\b|keyboard.*mouse|mouse.*keyboard", title, re.I) else "mouse" if re.search(r"\bmouse\b", title, re.I) else "keyboard"
        fam = f"{m.group(1)} {what}" + (" wired" if re.search(r"\bwired\b", title, re.I) and not re.search(r"\bwireless\b", title, re.I) else "")
    if not fam and cat == "smarthome" and (m := re.search(r"\b(echo\s+dot\s+max|nest\s+mini|nest\s+audio)\b", title, re.I)):
        fam = re.sub(r"\s+", " ", m.group(1)).lower()           # one generation on sale: the words are the model
    if not fam:
        return None
    if cat == "smarthome":
        fam = _home_kind(title, fam)
    if cat == "audio" and brand == "Xiaomi" and re.search(r"\bredmi\b", title, re.I) and not fam.startswith("redmi"):
        fam = f"redmi {fam}"                           # Redmi Buds 5 (25) is not Xiaomi Buds 5 (79), same shop (2026-11-23)
    if cat == "audio" and brand == "Apple" and fam in ("airpods", "airpods pro"):
        return None                                    # "Apple AirPods Pro": which generation? (2 and 3 sell side by side)
    if cat == "audio" and brand == "Fifine" and re.search(r"\bmixer\b|\bxlr\b", title, re.I):
        return None                                    # a mixer or a microphone, not a headset
    if fam.split()[0] in ("cam", "basic", "8khz", "4g", "media"):
        return None                                    # "eufy Indoor Cam (2K ...)", "Haing Keyboard Basic": which one?
    size = _size(cat, title)
    if size is None:
        return None
    return cat, brand, f"{PREFIX[cat]} {fam}", size, ram


HOME_KIND = [("robot vacuum", r"robot(?:ic)?\s+(?:vacuum|cleaner|mop)|vacuum\s+robot|robot\s+vacuum"), ("doorbell", r"doorbell"),
             ("lock", r"\block\b"), ("scale", r"\bscale\b"), ("light strip", r"light\s?strip"), ("bulb", r"\bbulb\b"),
             ("plug", r"\bplug\b"), ("switch", r"\bswitch\b"), ("camera", r"\bcamera\b")]


def _home_kind(title: str, fam: str) -> str:
    fam = re.sub(r"^(?:alexa\s+)?(?:echo\s+)?(show|dot|pop|spot)\b", r"echo \1", fam)   # "Alexa Echo Show 5" = "Echo Show 5"
    if fam.startswith("echo "):
        return fam
    found = [(m.start(), kind) for kind, pat in HOME_KIND for m in [re.search(pat, title, re.I)] if m]
    if not found:
        return fam
    kind = min(found)[1]                     # the first one said: "Smart Fingerprint Lock ... Built-In Doorbell" is a lock
    return fam if kind in fam else f"{kind} {fam}"


def is_gadget_family(family: str) -> bool:
    return family.split(" ", 1)[0] in PREFIX.values()


def category_of(family: str) -> str | None:
    head = family.split(" ", 1)[0]
    return next((c for c, p in PREFIX.items() if p == head), None)


def well_formed(family: str) -> bool:
    words = family.split()[1:]
    longest = (9, 64) if family.startswith("pcpart ") else (6, 48)   # "pcpart gpu twin edge rtx 5060 ti 8gb oc"
    return 1 <= len(words) <= longest[0] and len(family) <= longest[1] and bool(re.search(r"\d", family) or len(words) >= 2)


_UPPER = {"anc", "nc", "se", "fe", "oled", "ps", "gt", "ii", "iii", "iv", "rog", "x", "s", "qled", "tws", "dw", "mfp", "aio", "mx"}


def pretty(brand: str, family: str) -> str:
    """The register's spelling (data/products), or one made from the matching key."""
    from . import settled
    return settled.shown_name(brand, family) or made_pretty(brand, family)


def made_pretty(brand: str, family: str) -> str:
    """The name made from the matching key. Web addresses are made from it, so a corrected name never moves a page."""
    """'Samsung Galaxy Buds 3 Pro', 'Sony WH1000XM6', 'HP LaserJet Pro M211DW', 'Sony PlayStation 5 Pro'."""
    words = family.split()[1:]
    special = {"playstation": "PlayStation", "airpods": "AirPods", "freebuds": "FreeBuds", "laserjet": "LaserJet",
               "deskjet": "DeskJet", "officejet": "OfficeJet", "ecotank": "EcoTank", "imac": "iMac", "xbox": "Xbox",
               "soundcore": "Soundcore", "partybox": "PartyBox", "cloudearbuds": "Cloud Earbuds", "powercore": "PowerCore", "ultragear": "UltraGear", "smarttank": "Smart Tank", "inktank": "Ink Tank"}

    def cap(w: str) -> str:
        if w in special:
            return special[w]
        if w in _UPPER or re.search(r"\d", w) and re.search(r"[a-z]", w):
            return w.upper()
        return w.capitalize()
    if family.startswith("pcpart "):
        return _pretty_part(brand, words).replace("Triplefan", "Triple Fan").replace("Dualfan", "Dual Fan")
    words = [{"ipad": "iPad", "usb": "USB"}.get(w, w) for w in words]
    name = " ".join(w if w in ("iPad", "USB") else cap(w) for w in words).replace("USB C", "USB-C")
    if family.startswith("desktop "):
        return laptop.pretty(brand, " ".join(words)) if brand != "Apple" else f"Apple {name.replace('Mac Mini', 'Mac mini')}"
    return f"{brand} {name}".strip()


def _pretty_part(brand: str, words: list[str]) -> str:
    tray = " (tray)" if words[-1:] == ["tray"] else ""
    words = [w for w in words if w != "tray"]
    if words[:1] == ["cpu"]:
        c = words[1] if len(words) > 1 else ""
        m = re.match(r"(ryzen)(\d)-(\w+)$", c) or re.match(r"(ultra)(\d)-(\w+)$", c) or re.match(r"(i\d)-(\w+)$", c)
        if m and m.group(1) == "ryzen":
            name = f"Ryzen {m.group(2)} {m.group(3).upper()}"
        elif m and m.group(1) == "ultra":
            name = f"Core Ultra {m.group(2)} {m.group(3).upper()}"
        elif m:
            name = f"Core {m.group(1)}-{m.group(2).upper()}"
        else:
            name = c.upper()
        return f"{brand} {name}{tray}"
    up = {"rtx": "RTX", "gtx": "GTX", "rx": "RX", "oc": "OC", "ti": "Ti", "super": "Super", "xlr8": "XLR8", "tuf": "TUF",
          "rog": "ROG", "ko": "KO", "lp": "LP", "brk": "BRK", "xt": "XT", "xtx": "XTX", "gre": "GRE", "arc": "Arc"}
    out = [up.get(w, w.upper() if re.fullmatch(r"\d+gb", w) else w.capitalize()) for w in words if w != "gpu"]
    return f"{brand} {' '.join(out)}{tray}"


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
    "projector": ("Projectors", "البروجكترات", "Projector", "بروجكتر", "projectors"),
    "smarthome": ("Smart home", "المنزل الذكي", "Smart home", "منزل ذكي", "smart-home"),
    "peripheral": ("Keyboards & mice", "الكيبورد والماوس", "Keyboard or mouse", "كيبورد أو ماوس", "keyboards-mice"),
    "tabletacc": ("Tablet pens & keyboards", "أقلام وكيبوردات التابلت", "Tablet accessory", "ملحق تابلت", "tablet-pens-keyboards"),
    "pcpart": ("Graphics cards & processors", "كروت الشاشة والمعالجات", "PC part", "قطعة كمبيوتر", "pc-parts"),
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
