"""Search text handling: people type phone names in Arabic letters, with Arabic digits, without spaces and with typos.

The catalogue is in Latin letters ("iPhone 17 Pro Max 256GB"), so a query is first turned into the same form:
"ايفون ١٧ برو ماكس ٢٥٦ جيجا" -> ["iphone", "17", "pro", "max", "256gb"].
A new category (tablets, watches, laptops) adds its words to AR_WORDS; nothing else changes.
"""
from __future__ import annotations

import re
import unicodedata

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
    # tablets
    "ايباد": "ipad", "ايبد": "ipad", "باد": "pad", "تاب": "tab", "ميتباد": "matepad",
    # sizes
    "جيجابايت": "gb", "جيجا": "gb", "جيبي": "gb", "تيرابايت": "tb", "تيرا": "tb", "رام": "ram",
    # letters in model names: "اس 26" is the S26, "اي 57" the A57, "5 جي" is 5G
    "اس": "s", "اي": "a", "ام": "m", "اكس": "x", "زد": "z", "جي": "g",
}
# written as two words
AR_PHRASES = {"اي باد": "ipad", "ميت باد": "matepad", "mate pad": "matepad", "i pad": "ipad", "اي فون": "iphone", "ريل مي": "realme", "ون بلس": "oneplus", "جي بي": "gb", "تي بي": "tb",
              "اس اي": "se", "اف اي": "fe", "برو ماكس": "pro max", "i phone": "iphone"}
# words that say what is being looked for, not which one
STOP_WORDS = {"موبايل", "موبايلات", "جوال", "جوالات", "هاتف", "هواتف", "تلفون", "تليفون", "جهاز", "سعر", "اسعار",
              "جديد", "ارخص", "احسن", "افضل", "بكم", "كم", "في", "الاردن", "عمان", "phone", "phones", "mobile",
              "smartphone", "price", "prices", "new", "cheapest", "best", "jordan", "gb", "tb", "ram",
              "تابلت", "تابلتات", "لوحي", "tablet", "tablets"}
# a word that names the kind of product narrows the search to that category ("تابلت سامسونج" = Samsung tablets)
CATEGORY_WORDS = {"تابلت": "tablet", "تابلتات": "tablet", "لوحي": "tablet", "tablet": "tablet", "tablets": "tablet",
                  "موبايل": "phone", "موبايلات": "phone", "جوال": "phone", "جوالات": "phone", "هاتف": "phone",
                  "هواتف": "phone", "تلفون": "phone", "تليفون": "phone", "phone": "phone", "phones": "phone",
                  "mobile": "phone", "smartphone": "phone"}
# common Latin misspellings that are more than one slip away
EN_WORDS = {"promax": "pro max", "galxy": "galaxy", "samsong": "samsung", "sumsung": "samsung", "ifone": "iphone",
            "ifon": "iphone", "xaiomi": "xiaomi", "xiomi": "xiaomi", "shaomi": "xiaomi", "hawawi": "huawei",
            "infinex": "infinix", "techno": "tecno", "gega": "gb", "giga": "gb", "gigabyte": "gb"}

KNOWN_WORDS = frozenset(AR_WORDS.values())  # real brand and model words: never "corrected" into another word

_AR = "؀-ۿ"
_PHRASE_RE = re.compile(rf"(?<![{_AR}a-z])(" + "|".join(re.escape(k) for k in sorted(AR_PHRASES, key=len, reverse=True)) + rf")(?![{_AR}a-z])")
_SPLIT = re.compile(rf"[{_AR}]+|[a-z0-9]+")
_ARTICLES = ("وال", "بال", "لل", "ال", "و", "ب", "ل")
_AR_LONG = [k for k in AR_WORDS if len(k) >= 4]


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
    return None


def haystack(label: str, brand: str, brand_ar: str, storage_gb: int | None) -> tuple[str, str, frozenset[str]]:
    """What a phone is searched by: its text, the same without spaces ("iphone17pro"), and its separate words."""
    text = fold(f"{label} {brand} {brand_ar} {storage_gb or ''}")
    words = frozenset(re.findall(rf"[a-z0-9{_AR}]+", text))
    return text, re.sub(rf"[^a-z0-9{_AR}]", "", text), words


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
