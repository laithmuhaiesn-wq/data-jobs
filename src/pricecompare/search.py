"""Search text handling: people type phone names in Arabic letters, with Arabic digits, without spaces and with typos.

The catalogue is in Latin letters ("iPhone 17 Pro Max 256GB"), so a query is first turned into the same form:
"ايفون ١٧ برو ماكس ٢٥٦ جيجا" -> ["iphone", "17", "pro", "max", "256gb"].
A new category (tablets, watches, laptops) adds its words to AR_WORDS; nothing else changes.
"""
from __future__ import annotations

import re
import unicodedata

from .display import BRAND_AR

MAX_WORDS = 8  # a longer query is cut: nobody types more, and it keeps one request cheap

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# letters that people use interchangeably (gh/q/g all stand for the "g" of Galaxy and giga)
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ی": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
                          "ک": "ك", "گ": "ج", "غ": "ج", "ق": "ج", "ـ": None})

# Arabic spelling (written with the folded letters above) -> the word used in the catalogue.
AR_WORDS = {
    # brands
    "ايفون": "iphone", "ايفن": "iphone", "افون": "iphone", "ابل": "apple", "سامسونج": "samsung", "سامسنج": "samsung",
    "سمسونج": "samsung", "جالكسي": "galaxy", "جلاكسي": "galaxy", "جالاكسي": "galaxy", "كالكسي": "galaxy",
    "شاومي": "xiaomi", "شياومي": "xiaomi", "زياومي": "xiaomi", "ريدمي": "redmi", "ردمي": "redmi", "بوكو": "poco",
    "هونر": "honor", "اونر": "honor", "هواوي": "huawei", "انفينكس": "infinix", "انفينيكس": "infinix",
    "انفنكس": "infinix", "اوبو": "oppo", "ريلمي": "realme", "تكنو": "tecno", "تيكنو": "tecno",
    "موتورولا": "motorola", "موتو": "moto", "نوكيا": "nokia", "فيفو": "vivo", "ايتل": "itel", "جوجل": "google",
    "بيكسل": "pixel", "ناثينج": "nothing", "سوني": "sony",
    # model words
    "برو": "pro", "ماكس": "max", "بلس": "plus", "بلاس": "plus", "الترا": "ultra", "اولترا": "ultra", "ميني": "mini",
    "لايت": "lite", "نوت": "note", "هوت": "hot", "سمارت": "smart", "سبارك": "spark", "كامون": "camon", "بوفا": "pova",
    "فولد": "fold", "فليب": "flip", "اير": "air", "ماجيك": "magic", "رينو": "reno", "ايدج": "edge", "نوفا": "nova",
    "بيورا": "pura", "فانتوم": "phantom", "بوب": "pop", "زيرو": "zero", "رازر": "razr", "فايند": "find",
    "بلاي": "play",
    # consoles (2026-11-25: "ps5" and "playstaion 5" found nothing)
    "بلايستيشن": "playstation", "بلاستيشن": "playstation", "بليستيشن": "playstation", "بلايستشن": "playstation",
    "اكسبوكس": "xbox", "نينتندو": "nintendo", "نينتيندو": "nintendo", "سويتش": "switch", "بورتال": "portal",
    # tablets
    "ايباد": "ipad", "ايبد": "ipad", "باد": "pad", "تاب": "tab", "ميتباد": "matepad",
    # sizes
    "جيجابايت": "gb", "جيجا": "gb", "جيبي": "gb", "تيرابايت": "tb", "تيرا": "tb", "رام": "ram",
    # kinds of product (2026-11-25: none of these words was found): the word kind_text() adds to every product of the kind
    "لابتوب": "laptop", "لابتب": "laptop", "لبتوب": "laptop", "كمبيوتر": "computer", "كومبيوتر": "computer", "حاسوب": "computer",
    "تلفزيون": "television", "تليفزيون": "television", "تلفاز": "television", "تلفزيونات": "television",
    "شاشه": "screen", "شاش": "screen", "شاشات": "screen", "مونيتور": "monitor", "ساعه": "watch", "ساعات": "watch", "سوار": "band", "اسواره": "band",
    "سماعه": "samaah", "سماعات": "samaah", "سماعتين": "samaah", "هيدفون": "headphone", "هدفون": "headphone", "هيدسيت": "headset",
    "ايربودز": "airpods", "ايربود": "airpods", "ايربودس": "airpods", "سبيكر": "speaker", "سبيكرات": "speaker", "مكبر": "speaker", "ساوندبار": "soundbar",
    "طابعه": "printer", "طابعات": "printer", "برنتر": "printer", "راوتر": "router", "راوترات": "router", "مودم": "router",
    "باوربانك": "powerbank", "هارد": "hard", "هاردسك": "hard", "فلاشه": "flash", "فلاش": "flash", "فلاشات": "flash", "ميموري": "memory",
    "كاميرا": "camera", "كاميره": "camera", "كاميرات": "camera", "كمرا": "camera", "مراجبه": "security", "ويبكام": "webcam",
    "بروجكتر": "projector", "بروجكتور": "projector", "بروجيكتور": "projector", "مكنسه": "vacuum", "مكانس": "vacuum", "روبوت": "robot",
    "جرس": "doorbell", "جفل": "lock", "كيبورد": "keyboard", "كيبوردات": "keyboard", "ماوس": "mouse", "ماوسات": "mouse", "فاره": "mouse",
    "جلم": "pencil", "معالج": "cpu", "معالجات": "cpu", "بروسيسور": "cpu", "كونسول": "console", "ذكيه": "smart", "ذكي": "smart",
    "خارجي": "external", "اليكسا": "alexa", "مجوي": "extender", "جيمنج": "gaming", "جيمينج": "gaming", "العاب": "gaming", "بلوتوث": "bluetooth", "لاسلكي": "wireless", "لاسلكيه": "wireless", "وايرلس": "wireless",
    "ماك": "mac", "ماكبوك": "macbook", "ايماك": "imac", "بودز": "buds",
    "لوجيتك": "logitech", "لوجتيك": "logitech", "لوجيتيك": "logitech", "لوجتك": "logitech", "اسوس": "asus", "ايسر": "acer", "ديل": "dell", "لينوفو": "lenovo",
    "كانون": "canon", "ابسون": "epson", "انكر": "anker", "هايسنس": "hisense", "توشيبا": "toshiba", "ريزر": "razer", "بوز": "bose",
    "هارمن": "harman", "نيكون": "nikon", "جوبرو": "gopro", "كينجستون": "kingston", "سانديسك": "sandisk", "بيلكن": "belkin",
    "جويروم": "joyroom", "هافيت": "havit", "ريماكس": "remax", "انتل": "intel", "رايزن": "ryzen", "هايبر": "hyper",
    # letters in model names: "اس 26" is the S26, "اي 57" the A57, "5 جي" is 5G
    "اس": "s", "اي": "a", "ام": "m", "اكس": "x", "زد": "z", "جي": "g",
}
# written as two words
AR_PHRASES = {"ps5": "playstation 5", "ps 5": "playstation 5", "ps4": "playstation 4", "ps 4": "playstation 4", "play station": "playstation",
              "بلاي ستيشن": "playstation", "بلي ستيشن": "playstation", "بلا ستيشن": "playstation", "اكس بوكس": "xbox", "x box": "xbox",
              "اي باد": "ipad", "ميت باد": "matepad", "mate pad": "matepad", "i pad": "ipad", "اي فون": "iphone", "ريل مي": "realme", "ون بلس": "oneplus", "جي بي": "gb", "تي بي": "tb",
              "سماعه راس": "headphone", "سماعات راس": "headphone", "اي مايس": "imice", "بي ان واي": "pny", "زد تي اي": "zte", "لاب توب": "laptop", "لاب تب": "laptop", "باور بانك": "powerbank", "بور بانك": "powerbank", "شاحن متنجل": "powerbank", "اير بودز": "airpods",
              "اير بود": "airpods", "ساوند بار": "soundbar", "sound bar": "soundbar", "واي فاي": "wifi", "wi fi": "wifi", "كرت شاشه": "gpu", "كرت الشاشه": "gpu",
              "كرت جرافيكس": "gpu", "graphics card": "gpu", "graphic card": "gpu", "داتا شو": "projector", "ويب كام": "webcam", "لوحه مفاتيح": "keyboard",
              "هارد ديسك": "hard", "كي بورد": "keyboard", "key board": "keyboard", "ماك بوك": "macbook", "mac book": "macbook", "اي ماك": "imac", "i mac": "imac",
              "سمارت ووتش": "watch", "ابل ووتش": "apple watch", "iwatch": "apple watch", "air pods": "airpods", "lap top": "laptop", "smart phone": "phone",
              "جي بي ال": "jbl", "ال جي": "lg", "اتش بي": "hp", "تي سي ال": "tcl", "ام اس اي": "msi", "تي بي لينك": "tp link", "تي في": "tv",
              "جي تاب": "g tab", "جو برو": "gopro", "جوي روم": "joyroom",
              "اس اي": "se", "اف اي": "fe", "برو ماكس": "pro max", "i phone": "iphone"}
# words that say what is being looked for, not which one
STOP_WORDS = {"موبايل", "موبايلات", "جوال", "جوالات", "هاتف", "هواتف", "تلفون", "تليفون", "جهاز", "سعر", "اسعار",
              "جديد", "ارخص", "احسن", "افضل", "بكم", "كم", "في", "الاردن", "عمان", "phone", "phones", "mobile",
              "smartphone", "price", "prices", "new", "cheapest", "best", "jordan", "gb", "tb", "ram",
              "بدي", "شراء", "اشتري", "للبيع", "عرض", "عروض", "اصلي", "من", "مع", "علي", "انش", "بوصه", "inch", "inches", "the", "for", "with",
              "تابلت", "تابلتات", "لوحي", "tablet", "tablets"}
# a word that names the kind of product narrows the search to that category ("تابلت سامسونج" = Samsung tablets)
CATEGORY_WORDS = {"تابلت": "tablet", "تابلتات": "tablet", "لوحي": "tablet", "tablet": "tablet", "tablets": "tablet",
                  "موبايل": "phone", "موبايلات": "phone", "جوال": "phone", "جوالات": "phone", "هاتف": "phone",
                  "هواتف": "phone", "تلفون": "phone", "تليفون": "phone", "phone": "phone", "phones": "phone",
                  "mobile": "phone", "smartphone": "phone"}
# words that name a kind only when nothing else is typed: "ram" alone lists the RAM sticks, while in "iPhone 16 8GB RAM"
# it only says what the 8GB is (a skipped word), so the phone is still found (2026-11-26)
ALONE_WORDS = {"ram": "ram", "rams": "ram", "رام": "ram", "رامات": "ram"}
# common Latin misspellings that are more than one slip away
EN_WORDS = {"playstaion": "playstation", "playstion": "playstation", "playsation": "playstation", "playstatoin": "playstation",
            "plastation": "playstation", "playstaton": "playstation", "playstaiton": "playstation", "pleystation": "playstation",
            "promax": "pro max", "galxy": "galaxy", "samsong": "samsung", "sumsung": "samsung", "ifone": "iphone",
            "ifon": "iphone", "xaiomi": "xiaomi", "xiomi": "xiaomi", "shaomi": "xiaomi", "hawawi": "huawei",
            "infinex": "infinix", "techno": "tecno", "gega": "gb", "giga": "gb", "processor": "cpu",
            "vga": "gpu", "harddisk": "hard", "hdd": "hard", "notebook": "laptop", "cctv": "security", "earbud": "earbuds", "earphones": "earbuds", "earphone": "earbuds",
            "labtop": "laptop", "modem": "router", "headphones": "headphone", "headsets": "headset", "mic": "microphone"}

_AR = "؀-ۿ"
_PHRASE_RE = re.compile(rf"(?<![{_AR}a-z])(" + "|".join(re.escape(k) for k in sorted(AR_PHRASES, key=len, reverse=True)) + rf")(?![{_AR}a-z])")
_SPLIT = re.compile(rf"[{_AR}]+|[a-z0-9]+")
_ARTICLES = ("وال", "بال", "لل", "ال", "و", "ب", "ل")
_AR_LONG: list[str] = [k for k in AR_WORDS if len(k) >= 4]


def fold(text: str) -> str:
    """Lowercase, Western digits, one spelling per Arabic letter, no accents or stretching marks."""
    text = unicodedata.normalize("NFKC", text).lower().translate(_DIGITS)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))  # tashkeel
    return text.translate(_LETTERS)


def near(a: str, b: str) -> bool:
    """True when a and b differ by one typing slip: one letter wrong, missing, extra, or two neighbours swapped."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _arabic_word(w: str) -> str:
    """One Arabic word -> the catalogue word, allowing "the", a plural ending and one typing slip."""
    forms = [w] + [w[len(a):] for a in _ARTICLES if w.startswith(a) and len(w) - len(a) >= 2]
    forms += [f[:-2] for f in list(forms) if f.endswith("ات") and len(f) >= 5]
    for f in forms:
        if f in STOP_WORDS:
            return ""
        if f in AR_WORDS:
            return AR_WORDS[f]
    for f in forms:
        if len(f) >= 4:
            hit = next((k for k in _AR_LONG if near(f, k)), None)
            if hit:
                return AR_WORDS[hit]
    return w


def _learn_brands() -> None:
    """Every brand's Arabic name is a real word, so it is never taken for another one with a slip ("جارد" is not "هارد")."""
    for name in BRAND_AR.values():
        for w in re.findall(rf"[{_AR}]{{4,}}", fold(name)):
            AR_WORDS.setdefault(w, w)
    _AR_LONG[:] = [k for k in AR_WORDS if len(k) >= 4]


_learn_brands()
KNOWN_WORDS = frozenset(AR_WORDS.values())  # real brand and model words: never "corrected" into another word


def query_words(q: str) -> list[str]:
    """The words a phone must contain to match the query."""
    t = _PHRASE_RE.sub(lambda m: f" {AR_PHRASES[m.group(1)]} ", fold(q))
    parts = []
    for w in _SPLIT.findall(t):  # also separates "ايفون17" and "256جيجا" into word and number
        if "؀" <= w[0] <= "ۿ":
            w = _arabic_word(w)
        parts.append(EN_WORDS.get(w, w))
    t = " ".join(p for p in parts if p)
    t = re.sub(r"\b(\d+) (gb|tb|g)\b", r"\1\2", t)       # "256 gb" -> "256gb", "5 g" -> "5g": the catalogue joins them
    t = re.sub(r"\b([asmxz]) (\d{1,3})\b", r"\1\2", t)   # "a 57", "اس 26" -> "a57", "s26"
    words: list[str] = []
    for w in t.split():
        if w not in STOP_WORDS and w not in words:
            words.append(w)
    return words[:MAX_WORDS]


def query_category(q: str) -> str | None:
    """The category named in the query, if any: "تابلت هونر" -> "tablet"."""
    for w in _SPLIT.findall(fold(q)):
        for form in (w, w[2:] if w.startswith("ال") else w):
            if form in CATEGORY_WORDS:
                return CATEGORY_WORDS[form]
    if not query_words(q):
        for w in _SPLIT.findall(fold(q)):
            for form in (w, w[2:] if w.startswith("ال") else w):
                if fold(form) in ALONE:
                    return ALONE[fold(form)]
    return None


# What every product of a kind is called besides its own name (a product's name is "HP N141A", never "HP printer N141A").
_KIND = {"ram": "ram memory", "laptop": "laptop computer", "desktop": "desktop pc computer", "tv": "tv television screen smart", "monitor": "monitor screen computer",
         "watch": "smart watch smartwatch", "audio": "samaah", "speaker": "samaah speaker", "printer": "printer", "router": "router wifi",
         "powerbank": "power bank powerbank", "storage": "storage", "camera": "camera", "projector": "projector", "console": "console gaming",
         "smarthome": "smart home"}
# Words told by the shops' own titles; for some kinds, when no title says which one it is, all of the kind's words count.
_TITLE_KIND = {
    "audio": [("headset", r"head[ -]?sets?|هيدسيت"), ("headphone", r"head[ -]?phones?|over[ -]ear|هيدفون"),
              ("earbuds", r"ear[ -]?buds?|\bbuds\b|ear[ -]?phones?|air[ -]?pods?|in[ -]ear|\btws\b")],
    "peripheral": [("keyboard", r"key[ -]?board|كيبورد|لوحة مفاتيح"), ("mouse", r"mouse|\bmice\b|ماوس")],
    "storage": [("ssd", r"ssd|nvme|\bm\.2"), ("hard", r"\bhdd\b|hard[ -]?(disk|drive)|هارد"), ("flash usb", r"flash|thumb|فلاش"),
                ("memory card", r"memory[ -]card|micro[ -]?sd|\bsd[xh]c\b")],
    "pcpart": [("gpu", r"\b(rtx|gtx|rx|arc|geforce|radeon)\b|graphic"), ("cpu", r"\b(ryzen|core|athlon|processor|cpu)\b")],
    "camera": [("security", r"security|cctv|surveillance|\bip[ -]cam|wi-?fi[ -]cam|bullet|dome|turret|مراقبة|dahua|hikvision|ezviz|imou|\bunv\b|tapo"),
               ("webcam", r"web[ -]?cam")],
    "smarthome": [("vacuum robot", r"vacuum|مكنسة"), ("doorbell", r"door[ -]?bell|جرس"), ("lock", r"\block\b|قفل"),
                  ("alexa", r"alexa|\becho\b"), ("speaker samaah", r"speaker|\becho\b|homepod|nest (mini|audio)")],
    "tabletacc": [("pencil", r"pencil|\bpen\b|stylus"), ("keyboard", r"key[ -]?board")],
    "router": [("extender", r"extender|repeater|booster|مقوي")],
    "speaker": [("soundbar", r"sound[ -]?bar")],
}
_TITLE_ANY = [("gaming", r"gaming|\bgamer|جيمنج|جيمنغ|ألعاب"), ("bluetooth", r"bluetooth|بلوتوث"), ("wireless", r"wireless|لاسلكي"), ("microphone", r"microphone"), ("external", r"external|portable|خارجي|my passport|elements|expansion")]
_ALL_IF_UNKNOWN = ("audio", "peripheral", "pcpart")


def kind_text(category: str, titles: str) -> str:
    """The kind words one product is also found by, from its category and its shops' titles (or links)."""
    t = titles.lower().replace("_", " ")
    found = [w for w, rx in _TITLE_KIND.get(category, ()) if re.search(rx, t)]
    if not found and category in _ALL_IF_UNKNOWN:
        found = [w for w, _ in _TITLE_KIND[category]]
    if category not in ("phone", "tablet"):
        found += [w for w, rx in _TITLE_ANY if re.search(rx, t)]
    return " ".join(x for x in (_KIND.get(category, ""), *found) if x)


def hay_of(v: dict) -> tuple[str, str, frozenset[str]]:
    """haystack() of one product as the API, the app's files and the website know it."""
    kinds = v["kinds"] if "kinds" in v else kind_text(v.get("category", ""), " ".join([v["label"]] + [o.get("url") or "" for o in v.get("offers", [])]))
    ps = re.search(r"\bps([45])\b", v["label"], re.I)   # "PS4" typed is read as PlayStation 4
    return haystack(v["label"], v["brand"], v["brand_ar"], v["storage_gb"], kinds + (f" playstation {ps[1]}" if ps else ""))


def haystack(label: str, brand: str, brand_ar: str, storage_gb: int | None, kinds: str = "") -> tuple[str, str, frozenset[str]]:
    """What a phone is searched by: its text, the same without spaces ("iphone17pro"), and its separate words."""
    text = fold(f"{label} {brand} {brand_ar} {storage_gb or ''}")
    compact = re.sub(rf"[^a-z0-9{_AR}]", "", text)   # kind words are not part of the joined name
    text = f"{text} {kinds}".rstrip()
    return text, compact, frozenset(re.findall(rf"[a-z0-9{_AR}]+", text))


def match(words: list[str], hay: tuple[str, str, frozenset[str]], forgive: frozenset[str] = frozenset()) -> int | None:
    """None when the phone does not match; otherwise how many words needed a typing slip forgiven (0 = exact).

    Only the words in `forgive` may be matched loosely: the caller puts a word there when no phone at all contains it,
    so "pova" never drags in "nova". A slip is forgiven only in a real word of 4+ letters, never in "a57" vs "a56".
    """
    text, compact, tokens = hay
    slips = 0
    for w in words:
        if w in text or w in compact:
            continue
        if w in forgive and len(w) >= 4 and w.isalpha() and any(near(w, t) for t in tokens if len(t) >= 4):
            slips += 1
            continue
        return None
    return slips


def find(q: str, items: list[tuple], allowed=None) -> list[tuple[int, object]]:
    """(slips, id) of the products (id, category, haystack) a typed search finds. The one rule of the API; web/search.js and
    app/lib/local_search.dart do the same (tests and the nightly search check compare them)."""
    words, cat = query_words(q), query_category(q)
    if not words and not cat:
        return []
    # a typing slip is forgiven only for a word that no product contains as typed ("samsng"), never for a real one
    # ("pova" is a real model name: with no Pova on sale the answer is nothing, not the Huawei Nova)
    forgive = frozenset(w for w in words if w not in KNOWN_WORDS and not any(w in h[0] or w in h[1] for _, _, h in items))
    out = []
    for i, c, h in items:
        if (cat and c != cat) or (allowed and not allowed(i)):
            continue
        slips = match(words, h, forgive)
        if slips is not None:
            out.append((slips, i))
    return out


ALONE = {fold(k): v for k, v in ALONE_WORDS.items()}   # what the clients get as "alone"
