"""Filter values for one product, the same for the website and the app.

Each product gets a small dict of filter group -> value, built only from what we already know for sure (the matched
storage and RAM, and the processor, screen and graphics written in the product's own name). A product without a value
for a group simply does not show under that group's choices. The clients count the values to build the choices, so
the filters only ever offer what is really on the list.
"""
from __future__ import annotations

import re

# shown in this order; the clients know the group titles in both languages
GROUPS = {
    "phone": ["brand", "storage"],      # RAM is known for too few phones to filter by it fairly
    "tablet": ["brand", "storage"],
    "laptop": ["brand", "chip", "ram", "storage", "screen", "gpu"],
    "tv": ["brand", "size"],
    "watch": ["brand", "case", "net"],
    # Stage 3 electronics (2026-11-14), one shared reader: the size field is inches, GB or mAh depending on the category
    "audio": ["brand"], "speaker": ["brand"], "console": ["brand"], "monitor": ["brand", "size"], "printer": ["brand"],
    "desktop": ["brand", "chip", "ram", "storage"], "router": ["brand"], "powerbank": ["brand", "capacity"],
    "storage": ["brand", "storage"], "camera": ["brand"],
}

_CHIPS = [   # first match wins; the label is the same in Arabic and English (people search these words in English)
    (re.compile(r"\b(celeron|pentium|athlon)\b|\bintel\s*n\d{2,4}\b|\bi3-n\d{3}\b", re.I), "Celeron / N"),
    (re.compile(r"\bcore\s*ultra\s*([579])\b|\bultra\s*([579])\s*\d{3}", re.I), "Core Ultra {}"),
    (re.compile(r"\bcore\s*i([3579])\b|\bi([3579])-\d{4,5}", re.I), "Core i{}"),
    (re.compile(r"\bcore\s*([3579])\b", re.I), "Core {}"),
    (re.compile(r"\bryzen(?:\s*ai)?(?:\s*max\+?)?\s*([3579])\b|\bryzen([3579])-", re.I), "Ryzen {}"),
    (re.compile(r"\b(m[1-5])\b|\b(a18)\s*pro\b", re.I), "Apple"),
    (re.compile(r"\bsnapdragon\b", re.I), "Snapdragon"),
]
_SCREEN = re.compile(r"(?<![\d.])(1[1-8])(?:\.\d)?\s*(?:\"|″|''|”|-?\s*inch)", re.I)
_GPU = re.compile(r"\b(rtx|gtx)\s*\d{4}|\bradeon\s*rx\s*\d{4}|\barc\s*a\d{3}m?\b", re.I)


def size_text(gb: int) -> str:
    return f"{gb // 1024}TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb}GB"


def chip(name: str) -> str | None:
    for rx, label in _CHIPS:
        m = rx.search(name)
        if m:
            n = next((g for g in m.groups() if g), "")
            return label.format(n) if "{}" in label else label
    return None


def screen(name: str) -> str | None:
    m = _SCREEN.search(name)
    if not m:
        return None
    n = int(m.group(1))
    return '13-14"' if n <= 14 else ('15-16"' if n <= 16 else '17-18"')


def of(v: dict) -> dict:
    """The filter values of one product summary (needs category, brand, model, storage_gb, ram_gb)."""
    cat, name = v.get("category"), v.get("model") or ""
    f: dict[str, str] = {"brand": v["brand"]}
    if cat == "tv":
        if v.get("storage_gb"):
            f["size"] = f'{v["storage_gb"]}"'
        return f
    if cat in ("audio", "speaker", "console", "printer", "router", "camera"):
        return f
    if cat == "monitor":
        if v.get("storage_gb"):
            f["size"] = f'{v["storage_gb"]}"'
        return f
    if cat == "powerbank":
        if v.get("storage_gb"):
            f["capacity"] = f'{v["storage_gb"]:,}mAh'
        return f
    if cat == "desktop":
        if v.get("ram_gb"):
            f["ram"] = f"{v['ram_gb']}GB"
        if chip(name):
            f["chip"] = chip(name)
    if cat == "watch":   # the size field holds the case size in mm (0 = one size)
        if v.get("storage_gb"):
            f["case"] = f'{v["storage_gb"]}mm'
        f["net"] = "cellular" if "cellular" in (v.get("storage") or "").lower() else "gps"
        return f
    if v.get("storage_gb"):
        f["storage"] = size_text(v["storage_gb"])
    if cat == "laptop":
        if v.get("ram_gb"):
            f["ram"] = f"{v['ram_gb']}GB"
        for key, value in (("chip", chip(name)), ("screen", screen(name))):
            if value:
                f[key] = value
        f["gpu"] = "card" if _GPU.search(name) else "built-in"
    return f


# ---- smart filters: the few choices people actually start with, per category ("55 inch", "Gaming", "Under 150 JOD").
# Choices in the same set are "either" (55" or 65"); choices in different sets must all hold.
# A new category gets its row here and in GROUPS; the website and the app read both from /api/filters.json.
def _price(lo: float | None, hi: float | None):
    return lambda v, f: v.get("best_price") is not None and (lo is None or v["best_price"] >= lo) and (hi is None or v["best_price"] < hi)


def _size(lo: int, hi: int):
    return lambda v, f: v.get("storage_gb") is not None and lo <= v["storage_gb"] <= hi


def _gb(lo: int, hi: int = 10**6):
    return lambda v, f: v.get("storage_gb") is not None and lo <= v["storage_gb"] <= hi


def _fast(v, f):
    c = f.get("chip") or ""
    return bool(re.search(r"[79]$", c)) or (c == "Apple" and bool(re.search(r"\b(pro|max)\b", v.get("model") or "", re.I)))


def _words(pattern: str):
    rx = re.compile(pattern, re.I)
    return lambda v, f: bool(rx.search(v.get("model") or ""))


GAMING_AUDIO = {"HyperX", "Razer", "SteelSeries", "Corsair", "Logitech", "Fantech", "Redragon", "Havit", "Xtrike Me"}


QUICK: dict[str, list[tuple[str, str, str, str, object]]] = {   # (set, id, Arabic, English, rule)
    "phone": [
        ("price", "p150", "أقل من 150 د.أ", "Under 150 JOD", _price(None, 150)),
        ("price", "p400", "150 - 400 د.أ", "150 - 400 JOD", _price(150, 400)),
        ("price", "p800", "400 - 800 د.أ", "400 - 800 JOD", _price(400, 800)),
        ("price", "pmax", "أكثر من 800 د.أ", "Over 800 JOD", _price(800, None)),
        ("storage", "s128", "128GB", "128GB", _gb(128, 128)),
        ("storage", "s256", "256GB", "256GB", _gb(256, 256)),
        ("storage", "s512", "512GB وأكثر", "512GB+", _gb(512)),
    ],
    "tablet": [
        ("kind", "ipad", "آيباد", "iPad", lambda v, f: v["brand"] == "Apple"),
        ("kind", "android", "أندرويد", "Android", lambda v, f: v["brand"] != "Apple"),
        ("sim", "sim", "مع شريحة اتصال", "With SIM", lambda v, f: "cellular" in (v.get("storage") or "").lower()),
        ("price", "p200", "أقل من 200 د.أ", "Under 200 JOD", _price(None, 200)),
        ("price", "p500", "200 - 500 د.أ", "200 - 500 JOD", _price(200, 500)),
        ("price", "pmax", "أكثر من 500 د.أ", "Over 500 JOD", _price(500, None)),
        ("storage", "s256", "256GB وأكثر", "256GB+", _gb(256)),
    ],
    "laptop": [
        ("use", "gaming", "للألعاب (كرت شاشة)", "Gaming (graphics card)", lambda v, f: f.get("gpu") == "card"),
        ("use", "mac", "ماك بوك", "MacBook", lambda v, f: v["brand"] == "Apple"),
        ("use", "light", "خفيف 13-14 إنش", "Light 13-14\"", lambda v, f: f.get("screen") == '13-14"'),
        ("fast", "fast", "معالج قوي (i7 / Ultra 7 / Ryzen 7 وأعلى)", "Fast chip (i7, Ultra 7, Ryzen 7+)", _fast),
        ("ram", "r16", "رام 16GB وأكثر", "16GB RAM+", lambda v, f: (v.get("ram_gb") or 0) >= 16),
        ("price", "p450", "اقتصادي: أقل من 450 د.أ", "Budget: under 450 JOD", _price(None, 450)),
        ("price", "p900", "450 - 900 د.أ", "450 - 900 JOD", _price(450, 900)),
        ("price", "pmax", "أكثر من 900 د.أ", "Over 900 JOD", _price(900, None)),
    ],
    "tv": [
        ("size", "t43", "43 إنش وأصغر", "43\" or smaller", _size(1, 43)),
        ("size", "t50", "50 إنش", "50\"", _size(48, 50)),
        ("size", "t55", "55 إنش", "55\"", _size(55, 58)),
        ("size", "t65", "65 إنش", "65\"", _size(65, 70)),
        ("size", "t75", "75 إنش", "75\"", _size(75, 77)),
        ("size", "t85", "85 إنش وأكبر", "85\" and bigger", _size(82, 200)),
        ("price", "p300", "أقل من 300 د.أ", "Under 300 JOD", _price(None, 300)),
        ("price", "p700", "300 - 700 د.أ", "300 - 700 JOD", _price(300, 700)),
        ("price", "pmax", "أكثر من 700 د.أ", "Over 700 JOD", _price(700, None)),
    ],
    "watch": [
        ("kind", "apple", "آبل واتش (للآيفون)", "Apple Watch (for iPhone)", lambda v, f: v["brand"] == "Apple"),
        ("kind", "android", "ساعات أندرويد", "For Android phones", lambda v, f: v["brand"] != "Apple"),
        ("kind", "band", "أساور رياضية", "Fitness bands", lambda v, f: bool(re.search(r"\b(band|fit)\b", v.get("model") or "", re.I))),
        ("sim", "cell", "بشريحة اتصال (Cellular)", "With its own SIM (Cellular)", lambda v, f: f.get("net") == "cellular"),
        ("case", "small", "حجم صغير (حتى 42mm)", "Small case (up to 42mm)", _size(1, 42)),
        ("case", "large", "حجم كبير (44mm وأكبر)", "Large case (44mm and up)", _size(44, 60)),
        ("price", "p50", "أقل من 50 د.أ", "Under 50 JOD", _price(None, 50)),
        ("price", "p150", "50 - 150 د.أ", "50 - 150 JOD", _price(50, 150)),
        ("price", "p400", "150 - 400 د.أ", "150 - 400 JOD", _price(150, 400)),
        ("price", "pmax", "أكثر من 400 د.أ", "Over 400 JOD", _price(400, None)),
    ],
    "audio": [
        ("kind", "airpods", "إيربودز آبل", "Apple AirPods", lambda v, f: v["brand"] == "Apple"),
        ("kind", "gaming", "سماعات ألعاب", "Gaming headsets", lambda v, f: v["brand"] in GAMING_AUDIO),
        ("price", "p30", "أقل من 30 د.أ", "Under 30 JOD", _price(None, 30)),
        ("price", "p100", "30 - 100 د.أ", "30 - 100 JOD", _price(30, 100)),
        ("price", "p250", "100 - 250 د.أ", "100 - 250 JOD", _price(100, 250)),
        ("price", "pmax", "أكثر من 250 د.أ", "Over 250 JOD", _price(250, None)),
    ],
    "speaker": [
        ("kind", "party", "سماعات حفلات", "Party speakers", _words(r"partybox|xboom|party|boombox|rave")),
        ("kind", "small", "صغيرة ومحمولة", "Small and portable", _words(r"\b(go|clip|flip|mini|micro|wonderboom|soundlink)\b")),
        ("price", "p50", "أقل من 50 د.أ", "Under 50 JOD", _price(None, 50)),
        ("price", "p150", "50 - 150 د.أ", "50 - 150 JOD", _price(50, 150)),
        ("price", "pmax", "أكثر من 150 د.أ", "Over 150 JOD", _price(150, None)),
    ],
    "console": [
        ("kind", "ps", "بلايستيشن", "PlayStation", lambda v, f: v["brand"] == "Sony"),
        ("kind", "nintendo", "نينتندو", "Nintendo", lambda v, f: v["brand"] == "Nintendo"),
        ("kind", "xbox", "إكس بوكس", "Xbox", lambda v, f: v["brand"] == "Microsoft"),
        ("kind", "handheld", "أجهزة محمولة", "Handheld", _words(r"switch|steam|ally|legion|portal|claw")),
        ("price", "p400", "أقل من 400 د.أ", "Under 400 JOD", _price(None, 400)),
        ("price", "pmax", "400 د.أ وأكثر", "400 JOD and up", _price(400, None)),
    ],
    "monitor": [
        ("size", "m24", "24 إنش وأصغر", "24\" and smaller", _size(1, 24)),
        ("size", "m27", "27 إنش", "27\"", _size(25, 28)),
        ("size", "m32", "32 إنش وأكبر", "32\" and bigger", _size(29, 60)),
        ("kind", "gaming", "شاشات ألعاب", "Gaming monitors", _words(r"odyssey|ultragear|rog|tuf|aorus|\bmag\b|\bmpg\b|nitro|predator|"
                                                                  r"legion|alienware|\bg\d|\d{2}g[a-z]?\d|optix")),
        ("price", "p100", "أقل من 100 د.أ", "Under 100 JOD", _price(None, 100)),
        ("price", "p250", "100 - 250 د.أ", "100 - 250 JOD", _price(100, 250)),
        ("price", "pmax", "أكثر من 250 د.أ", "Over 250 JOD", _price(250, None)),
    ],
    "printer": [
        ("kind", "laser", "ليزر", "Laser", _words(r"laserjet|\blbp|\bmf\d|i-?sensys|\bm\d{3}|\bp\d{4}|\bhl|\bdcp-?l|\bmfc-?l")),
        ("kind", "ink", "حبر (إنك جت وتانك)", "Ink (inkjet and tank)", _words(r"deskjet|officejet|smart\s?tank|ecotank|pixma|\bl\d{4}|\bg\d{4}|\bts\d")),
        ("price", "p100", "أقل من 100 د.أ", "Under 100 JOD", _price(None, 100)),
        ("price", "p250", "100 - 250 د.أ", "100 - 250 JOD", _price(100, 250)),
        ("price", "pmax", "أكثر من 250 د.أ", "Over 250 JOD", _price(250, None)),
    ],
    "desktop": [
        ("kind", "mac", "أجهزة ماك", "Mac", lambda v, f: v["brand"] == "Apple"),
        ("kind", "aio", "الكل في واحد", "All-in-one", _words(r"imac|\baio\b|neo 50a|\ba\d{2,3}\b")),
        ("chip", "fast", "معالج قوي (i7 / Ryzen 7 وأعلى)", "Fast processor (i7 / Ryzen 7 and up)", _fast),
        ("price", "p400", "أقل من 400 د.أ", "Under 400 JOD", _price(None, 400)),
        ("price", "p800", "400 - 800 د.أ", "400 - 800 JOD", _price(400, 800)),
        ("price", "pmax", "أكثر من 800 د.أ", "Over 800 JOD", _price(800, None)),
    ],
    "router": [
        ("kind", "mesh", "نظام ميش للبيت كله", "Mesh (whole home)", _words(r"deco|mesh|velop|orbi")),
        ("kind", "extender", "مقوي إشارة", "Range extender", _words(r"\bre\d|extender|repeater")),
        ("price", "p30", "أقل من 30 د.أ", "Under 30 JOD", _price(None, 30)),
        ("price", "p100", "30 - 100 د.أ", "30 - 100 JOD", _price(30, 100)),
        ("price", "pmax", "أكثر من 100 د.أ", "Over 100 JOD", _price(100, None)),
    ],
    "powerbank": [
        ("cap", "b10", "10000mAh وأقل", "10,000mAh and less", _size(1, 10000)),
        ("cap", "b20", "20000mAh", "20,000mAh", _size(10001, 20000)),
        ("cap", "b30", "أكثر من 20000mAh", "Over 20,000mAh", _size(20001, 10**6)),
        ("price", "p20", "أقل من 20 د.أ", "Under 20 JOD", _price(None, 20)),
        ("price", "p50", "20 - 50 د.أ", "20 - 50 JOD", _price(20, 50)),
        ("price", "pmax", "أكثر من 50 د.أ", "Over 50 JOD", _price(50, None)),
    ],
    "storage": [
        ("cap", "s512", "512GB وأقل", "512GB and less", _gb(1, 512)),
        ("cap", "s1", "1TB", "1TB", _gb(900, 1100)),
        ("cap", "s2", "2TB وأكثر", "2TB and more", _gb(1800)),
        ("price", "p30", "أقل من 30 د.أ", "Under 30 JOD", _price(None, 30)),
        ("price", "p80", "30 - 80 د.أ", "30 - 80 JOD", _price(30, 80)),
        ("price", "pmax", "أكثر من 80 د.أ", "Over 80 JOD", _price(80, None)),
    ],
    "camera": [
        ("kind", "photo", "كاميرات تصوير", "Photo cameras", lambda v, f: v["brand"] in ("Canon", "Nikon", "Sony", "Fujifilm", "Kodak", "Panasonic")),
        ("kind", "action", "كاميرات أكشن", "Action cameras", lambda v, f: v["brand"] in ("GoPro", "DJI", "Insta360")),
        ("kind", "security", "كاميرات مراقبة", "Security cameras", lambda v, f: v["brand"] in ("Ezviz", "Imou", "Dahua", "Hikvision", "TP-Link", "Xiaomi")),
        ("price", "p50", "أقل من 50 د.أ", "Under 50 JOD", _price(None, 50)),
        ("price", "p300", "50 - 300 د.أ", "50 - 300 JOD", _price(50, 300)),
        ("price", "pmax", "أكثر من 300 د.أ", "Over 300 JOD", _price(300, None)),
    ],
}

GROUP_NAMES = {"brand": ("الماركة", "Brand"), "storage": ("السعة", "Storage"), "ram": ("الرام", "RAM"), "chip": ("المعالج", "Processor"),
               "screen": ("الشاشة", "Screen"), "gpu": ("كرت الشاشة", "Graphics"), "size": ("حجم الشاشة", "Screen size"),
               "case": ("حجم الساعة", "Case size"), "net": ("الاتصال", "Connection"),
               "capacity": ("السعة", "Capacity")}
CATEGORY_NAMES = {"phone": ("موبايلات", "Phones"), "tablet": ("تابلت", "Tablets"), "laptop": ("لابتوبات", "Laptops"),
                  "tv": ("شاشات", "TVs"), "watch": ("ساعات ذكية", "Smartwatches"),
                  "audio": ("سماعات", "Headphones"), "speaker": ("مكبرات صوت", "Speakers"), "console": ("أجهزة ألعاب", "Consoles"),
                  "monitor": ("شاشات كمبيوتر", "Monitors"), "printer": ("طابعات", "Printers"), "desktop": ("كمبيوتر مكتبي", "Desktops"),
                  "router": ("راوترات", "Routers"), "powerbank": ("باور بانك", "Power banks"), "storage": ("تخزين", "Storage"),
                  "camera": ("كاميرات", "Cameras")}
VALUE_NAMES = {"card": ("كرت شاشة منفصل", "Graphics card"), "built-in": ("مدمج", "Built-in"),
               "gps": ("GPS فقط", "GPS only"), "cellular": ("بشريحة (Cellular)", "Cellular (own SIM)")}


def quick(v: dict) -> list[str]:
    """The smart choices this product falls under."""
    f = of(v)
    return [qid for _, qid, _, _, rule in QUICK.get(v.get("category") or "", []) if rule(v, f)]


def config() -> dict:
    """Everything the clients need to draw the filters of every category (served as /api/filters.json)."""
    return {"categories": {cat: {"ar": CATEGORY_NAMES[cat][0], "en": CATEGORY_NAMES[cat][1], "quick": [{"set": s, "id": i, "ar": ar, "en": en} for s, i, ar, en, _ in QUICK.get(cat, [])],
                                 "groups": [{"key": g, "ar": GROUP_NAMES[g][0], "en": GROUP_NAMES[g][1]} for g in groups]}
                           for cat, groups in GROUPS.items()},
            "values": {k: {"ar": ar, "en": en} for k, (ar, en) in VALUE_NAMES.items()}}
