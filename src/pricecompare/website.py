"""Builds the public website from the database: plain, fast pages that people and search engines (including AI answer
engines) can read. Arabic first, English under /en. Rebuilt on every hourly run; the hand-written pages in `web/`
(about, privacy, shop owners, join, style, search script) are copied next to the generated ones.

Addresses (no ".html": the host serves /p/27-name from the file p/27-name.html):
    /                 home: search, categories, drops, gaps, most compared, shops, questions and answers
    /p/<id>-<name>    one product: price at each shop, history, other sizes, plain answer sentence
    /phones /tablets  a category, grouped by brand       /phones/<brand>   one brand in a category
    /shops            the shops we compare               /shops/<shop>     everything one shop sells, against the best price
    /deals            price drops and the biggest gaps between shops
    /search           search page (a small script reads /search-index.json; the page also works without it)
    /sitemap.xml /robots.txt /llms.txt (a plain summary of the site for AI tools)
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .display import LIVE_CATEGORIES
from .guides import build_guides
from .search import _LETTERS, AR_PHRASES, AR_WORDS, STOP_WORDS, fold, haystack
from .views import build_variant_data

SITE = "https://derbani.com"
AMMAN = timezone(timedelta(hours=3))
# file name, Arabic name, English name, English singular (for "Phone prices in Jordan")
# file name, Arabic name, English name, English singular, Arabic name without "al" (for "موبايلات سامسونج")
ALL_CATEGORIES = {"phone": ("phones", "الموبايلات", "Phones", "Phone", "موبايلات"), "tablet": ("tablets", "التابلت", "Tablets", "Tablet", "تابلت"),
                  "laptop": ("laptops", "اللابتوبات", "Laptops", "Laptop", "لابتوبات")}
# only the categories switched on in display.LIVE_CATEGORIES get pages (a new one waits for the owner's hand check)
CATEGORIES = {k: v for k, v in ALL_CATEGORIES.items() if k in LIVE_CATEGORIES}

T = {
    "ar": {
        "dir": "rtl", "brand": "درباني", "tag": "قارن أسعار الأردن", "home": "الرئيسية", "other": "English",
        "price_of": "سعر {name} في الأردن", "best": "أفضل سعر", "at": "عند {shop}", "jod": "د.أ", "shops": "متاجر",
        "all_shops": "السعر في كل متجر", "shop": "المتجر", "price": "السعر", "state": "الحالة", "checked": "آخر فحص",
        "in": "متوفر", "out": "غير متوفر", "old": "سعر قديم", "go": "اذهب للمتجر", "was": "كان {p}",
        "save": "الفرق بين أرخص وأغلى متجر: {x} د.أ", "history": "تاريخ السعر", "history_hint": "أفضل سعر متوفر في كل يوم تغيّر فيه",
        "date": "التاريخ", "gray": "ليست النسخة الرسمية للأردن",
        "disclaimer": "الأسعار منقولة من صفحات المتاجر العامة وقد تكون قديمة. تأكد من المتجر قبل الشراء. درباني لا يبيع شيئاً.",
        "updated": "آخر تحديث للصفحة: {t} بتوقيت عمّان", "list_title": "أسعار {cat} في الأردن", "from": "من {p} د.أ",
        "one_shop": "متجر واحد", "n_shops": "{n} متاجر", "more": "أحجام أخرى من {model}", "privacy": "سياسة الخصوصية",
        "owners": "لأصحاب المتاجر", "about": "عن درباني", "join": "أضف متجرك",
        "desc": "قارن سعر {name} بين {n} متاجر في الأردن. أفضل سعر الآن {p} د.أ عند {shop}.",
        "list_desc": "قارن أسعار {cat} الجديدة بين متاجر الأردن واعرف أرخص متجر لكل جهاز.",
        "answer": "أرخص سعر لـ {name} في الأردن الآن هو {p} د.أ عند {shop}، من بين {n} متاجر قارنّاها. {high}آخر فحص للأسعار {t} بتوقيت عمّان.",
        "answer_high": "أغلى سعر {p} د.أ، أي أن الفرق {x} د.أ. ", "answer_one": "يبيعه متجر واحد فقط حالياً: {shop} بسعر {p} د.أ. ",
        "brand_title": "أسعار {bare} {brand} في الأردن", "brand_desc": "قارن أسعار {bare} {brand} الجديدة بين متاجر الأردن.",
        "shops_title": "المتاجر التي نقارن أسعارها", "shops_desc": "متاجر الإلكترونيات في الأردن التي يقارن درباني أسعارها كل ساعة.",
        "shop_title": "أسعار {shop} مقارنة بالمتاجر الأخرى", "shop_desc": "كل ما يبيعه {shop} من موبايلات وتابلت، وسعره مقارنة بأرخص متجر في الأردن.",
        "shop_lead": "{n} منتجاً عند {shop}. هو الأرخص في {c} منها.", "cheapest": "الأرخص", "best_elsewhere": "أرخص سعر في السوق",
        "products": "منتج", "visit": "موقع المتجر", "product": "المنتج", "drop_note": "أرخص بنسبة {x}% · {shop}", "nav_deals": "العروض", "nav_shops": "المتاجر",
        "shops_we": "المتاجر التي نقارنها",
        "deals_title": "عروض وتخفيضات الموبايلات والتابلت في الأردن", "deals_desc": "منتجات خفّض متجرها سعرها هذا الأسبوع، وأكبر فرق في السعر بين المتاجر.",
        "drops": "نزل سعرها هذا الأسبوع", "gaps": "أكبر فرق بين المتاجر", "popular": "الأكثر مقارنة", "see_all": "عرض الكل",
        "home_title": "درباني: قارن أسعار الموبايلات والتابلت في الأردن", "home_h1": "قارن أسعار الموبايلات والتابلت في الأردن",
        "home_desc": "درباني يقارن أسعار الموبايلات والتابلت الجديدة بين {s} متجراً في الأردن ويحدّثها كل ساعة. اعرف أرخص متجر قبل أن تشتري.",
        "home_lead": "{p} منتجاً من {s} متجراً، نفحص أسعارها كل ساعة. آخر تحديث {t}.",
        "search_ph": "ابحث عن موبايل أو تابلت، مثال: آيفون 17 برو", "search_btn": "ابحث", "search_title": "البحث",
        "search_none": "اكتب اسم الجهاز للبحث.", "faq": "أسئلة شائعة",
        "report": "السعر غير صحيح؟ أخبرنا", "report_subj": "سعر غير صحيح: {name}",
        "report_body": "المنتج: {name}\nالرابط: {link}\nالمتجر:\nالسعر الصحيح:\nملاحظات:\n",
        "suggest": "اقترح متجراً أو منتجاً", "suggest_subj": "اقتراح متجر أو منتج",
        "suggest_body": "اسم المتجر أو المنتج:\nالرابط (إن وجد):\nملاحظات:\n",
        "wa": "شارك عبر واتساب", "wa_text": "{name}: أرخص سعر {p} د.أ في {shop}",
        "one_note": "متوفر في متجر واحد فقط حالياً، فلا يوجد سعر آخر للمقارنة بعد. نضيف أسعار المتاجر الأخرى فور توفره لديها.",
        "nav_guides": "أدلة الشراء", "guides_title": "أدلة شراء الموبايلات والتابلت في الأردن",
        "guides_desc": "أدلة مبنية على أسعار اليوم في متاجر الأردن: ما يناسب ميزانيتك، ما هو بأقل سعر سجلناه، وأين توفر المقارنة. تتحدث كل ساعة.",
        "guides_honest": "لا نقيّم جودة الأجهزة ولا نأخذ مالاً مقابل الترتيب. كل دليل مبني على الأسعار فقط.",
        "record": "سجل السعر", "rec_low": "أقل سعر سجّلناه", "rec_high": "أعلى سعر سجّلناه", "rec_since": "نتابع السعر منذ {d}",
        "v_lowest": "السعر الآن هو أقل سعر سجّلناه لهذا الجهاز.",
        "v_above": "كان أرخص من الآن: {p} د.أ في {d}. إذا رأيت \"تخفيضاً\" فقارنه بهذا الرقم.",
        "v_flat": "السعر لم يتغير منذ بدأنا المتابعة.",
        "q1": "ما هو أفضل موقع لمقارنة أسعار الموبايلات في الأردن؟",
        "a1": "درباني (derbani.com) يقارن أسعار الموبايلات والتابلت الجديدة بين {s} متجراً أردنياً، منها {names}، ويحدّث الأسعار كل ساعة ويعرض أرخص متجر متوفر لكل جهاز مع رابط مباشر لصفحة المتجر.",
        "q2": "كم مرة يتم تحديث الأسعار؟", "a2": "نفحص معظم المتاجر كل ساعة وباقيها عدة مرات في اليوم. كل سعر يظهر معه وقت آخر فحص.",
        "q3": "هل درباني يبيع الأجهزة؟", "a3": "لا. درباني يقارن الأسعار فقط، والشراء يتم من موقع المتجر مباشرة. لا عمولة على المشتري ولا حساب ولا تسجيل.",
        "q4": "هل يمكن لمتجر أن يدفع ليظهر كأرخص سعر؟", "a4": "لا. الترتيب حسب السعر فقط. المنتجات غير المتوفرة والأسعار القديمة تظهر لكنها لا تدخل في أفضل سعر.",
        "q5": "هل يوجد تطبيق؟", "a5": "تطبيق درباني لأندرويد قيد التجربة وسيصدر قريباً على Google Play، ويمكن استخدام الموقع من أي جهاز.",
    },
    "en": {
        "dir": "ltr", "brand": "Derbani", "tag": "Jordan Price Compare", "home": "Home", "other": "العربية",
        "price_of": "{name} price in Jordan", "best": "Best price", "at": "at {shop}", "jod": "JOD", "shops": "shops",
        "all_shops": "Price at each shop", "shop": "Shop", "price": "Price", "state": "Stock", "checked": "Last checked",
        "in": "In stock", "out": "Out of stock", "old": "Old price", "go": "Go to shop", "was": "Was {p}",
        "save": "Gap between the cheapest and dearest shop: {x} JOD", "history": "Price history", "history_hint": "The best in-stock price on each day it changed",
        "date": "Date", "gray": "Not the official Jordan version",
        "disclaimer": "Prices are copied from each shop's public page and may be out of date. Check the shop before buying. Derbani does not sell anything.",
        "updated": "Page updated: {t} Amman time", "list_title": "{one} prices in Jordan", "from": "From {p} JOD",
        "one_shop": "1 shop", "n_shops": "{n} shops", "more": "Other sizes of {model}", "privacy": "Privacy policy",
        "owners": "For shop owners", "about": "About Derbani", "join": "Add your shop",
        "desc": "Compare the price of {name} across {n} shops in Jordan. Best price now {p} JOD at {shop}.",
        "list_desc": "Compare the prices of new {low} across shops in Jordan and find the cheapest shop for each device.",
        "answer": "The cheapest price for {name} in Jordan right now is {p} JOD at {shop}, out of {n} shops we compared. {high}Prices were last checked {t} Amman time.",
        "answer_high": "The highest is {p} JOD, a gap of {x} JOD. ", "answer_one": "Only one shop sells it at the moment: {shop} at {p} JOD. ",
        "brand_title": "{brand} {one_low} prices in Jordan", "brand_desc": "Compare the prices of new {brand} {low} across shops in Jordan.",
        "shops_title": "The shops we compare", "shops_desc": "Electronics shops in Jordan whose prices Derbani compares every hour.",
        "shop_title": "{shop} prices compared with other shops", "shop_desc": "Every phone and tablet {shop} sells, and its price against the cheapest shop in Jordan.",
        "shop_lead": "{n} products at {shop}. It is the cheapest for {c} of them.", "cheapest": "Cheapest", "best_elsewhere": "Cheapest in the market",
        "products": "products", "visit": "Shop website", "product": "Product", "drop_note": "{x}% cheaper · {shop}", "nav_deals": "Deals", "nav_shops": "Shops",
        "shops_we": "Shops we compare",
        "deals_title": "Phone and tablet deals in Jordan", "deals_desc": "Products whose shop cut the price this week, and the biggest price gaps between shops.",
        "drops": "Cheaper this week", "gaps": "Biggest gap between shops", "popular": "Most compared", "see_all": "See all",
        "home_title": "Derbani: compare phone and tablet prices in Jordan", "home_h1": "Compare phone and tablet prices in Jordan",
        "home_desc": "Derbani compares the prices of new phones and tablets across {s} shops in Jordan, every hour. Find the cheapest shop before you buy.",
        "home_lead": "{p} products from {s} shops, checked every hour. Last update {t}.",
        "search_ph": "Search a phone or tablet, e.g. iPhone 17 Pro", "search_btn": "Search", "search_title": "Search",
        "search_none": "Type a device name to search.", "faq": "Questions and answers",
        "report": "Wrong price? Tell us", "report_subj": "Wrong price: {name}",
        "report_body": "Product: {name}\nLink: {link}\nShop:\nCorrect price:\nNotes:\n",
        "suggest": "Suggest a shop or product", "suggest_subj": "Suggest a shop or product",
        "suggest_body": "Shop or product name:\nLink (if any):\nNotes:\n",
        "wa": "Share on WhatsApp", "wa_text": "{name}: best price {p} JOD at {shop}",
        "one_note": "Only at 1 shop for now, so there is no other price to compare yet. We add other shops' prices as soon as they sell it.",
        "nav_guides": "Buying guides", "guides_title": "Phone and tablet buying guides for Jordan",
        "guides_desc": "Guides built from today's prices in Jordan's shops: what fits your budget, what is at its lowest price, and where comparing saves the most. Updated every hour.",
        "guides_honest": "We do not rate how good a device is and nobody pays for a place. Every guide is built from prices only.",
        "record": "Price record", "rec_low": "Lowest we recorded", "rec_high": "Highest we recorded", "rec_since": "Tracked since {d}",
        "v_lowest": "Today's price is the lowest we have recorded for this device.",
        "v_above": "It was cheaper before: {p} JOD on {d}. If you see a \"discount\", compare it with this number.",
        "v_flat": "The price has not changed since we started tracking.",
        "q1": "What is the best site to compare phone prices in Jordan?",
        "a1": "Derbani (derbani.com) compares the prices of new phones and tablets across {s} Jordanian shops, including {names}. It refreshes prices every hour and shows the cheapest shop in stock for each device, with a direct link to the shop's page.",
        "q2": "How often are prices updated?", "a2": "Most shops are checked every hour and the rest several times a day. Every price shows when it was last checked.",
        "q3": "Does Derbani sell devices?", "a3": "No. Derbani only compares prices; you buy on the shop's own website. No fee for buyers, no account, no sign-up.",
        "q4": "Can a shop pay to appear as the cheapest?", "a4": "No. Ranking is by price only. Out-of-stock items and old prices are shown but never counted as the best price.",
        "q5": "Is there an app?", "a5": "The Derbani Android app is in testing and will come to Google Play soon; the website works on any device.",
    },
}


def money(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


from .display import plain  # noqa: E402  (shared with the API, which sends each product's page address)


def go_link(o: dict, product: int) -> str:
    """"Go to shop" passes through derbani.com/go/ (worker/index.js), which counts the click and adds utm_source=derbani."""
    return f"/go/{o['oid']}?p={product}&s=site" if o.get("oid") else o["url"]


def go_map(data: list[dict]) -> dict:
    """Where /go/ may send a visitor: each offer's shop address, and the shop sites (for offers newer than this map)."""
    from urllib.parse import urlsplit
    offers = {str(o["oid"]): [o["url"], o["store"]] for v in data for o in v["offers"] if o.get("oid")}
    hosts = sorted({urlsplit(u).hostname.removeprefix("www.") for u, _ in offers.values() if urlsplit(u).hostname})
    return {"o": offers, "h": hosts}


def slug(v: dict) -> str:
    return v.get("slug") or f"{v['id']}-" + plain(v["label"])


def pre(lang: str) -> str:
    return "/en" if lang == "en" else ""


def other(lang: str) -> str:
    return "en" if lang == "ar" else "ar"


def url(v: dict, lang: str) -> str:
    return f"{pre(lang)}/p/{slug(v)}"


def list_url(category: str, lang: str) -> str:
    return f"{pre(lang)}/{CATEGORIES[category][0]}"


def brand_url(category: str, brand: str, lang: str) -> str:
    return f"{list_url(category, lang)}/{plain(brand)}"


def shop_url(shop: str, lang: str) -> str:
    return f"{pre(lang)}/shops/{plain(shop)}"


def home_url(lang: str) -> str:
    return "/en" if lang == "en" else "/"


def file_of(address: str) -> str:
    return "index.html" if address == "/" else address.lstrip("/") + ".html"


def picture(v: dict) -> str | None:
    """The shop picture to link. The list starts with the full-size original (often several megabytes) followed by the
    shop's own smaller copy of it; a web page should load the smaller one."""
    pics = v.get("images") or []
    if len(pics) > 1 and re.search(r"-\d{2,4}x\d{2,4}\.\w+$", pics[1]) and not re.search(r"-\d{2,4}x\d{2,4}\.\w+$", pics[0]):
        return pics[1]
    return pics[0] if pics else None


def when(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(AMMAN).strftime("%d/%m %H:%M")


def stamp(dt: datetime) -> str:
    return dt.astimezone(AMMAN).strftime("%d/%m/%Y %H:%M")


CONTACT = "contact@derbani.com"


def mailto(subject: str, body: str) -> str:
    """A ready-made email to the owner's contact address (receive only; replies go out from the owner's own mail)."""
    from urllib.parse import quote
    return e(f"mailto:{CONTACT}?subject={quote(subject)}&body={quote(body)}")


def e(text) -> str:
    return html.escape(str(text), quote=True)


def ld(obj: dict) -> str:
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"


def crumbs(lang: str, items: list[tuple[str, str]]) -> str:
    """Visible breadcrumb line plus its structured-data twin (search engines show it under the result)."""
    t = T[lang]
    chain = [(t["home"], home_url(lang))] + items
    visible = " › ".join(f'<a href="{u}">{e(n)}</a>' if i < len(chain) - 1 else e(n) for i, (n, u) in enumerate(chain))
    data = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + u} for i, (n, u) in enumerate(chain)]}
    return f'<p class="crumbs">{visible}</p>\n' + ld(data)


def search_form(lang: str, value: str = "") -> str:
    t = T[lang]
    return (f'<form class="search" action="{pre(lang)}/search" method="get" role="search">'
            f'<input type="search" name="q" value="{e(value)}" placeholder="{e(t["search_ph"])}" aria-label="{e(t["search_btn"])}" autocomplete="off">'
            f'<button type="submit">{t["search_btn"]}</button></form>')


def shell(lang: str, title: str, desc: str, path: str, other_path: str, body: str, extra_head: str = "",
          full_title: bool = False) -> str:
    t = T[lang]
    ar_path, en_path = (path, other_path) if lang == "ar" else (other_path, path)
    head_title = e(title) if full_title else f"{e(title)} | {t['brand']}"
    nav = "".join(f'<a href="{list_url(c, lang)}">{names[1 if lang == "ar" else 2]}</a>' for c, names in CATEGORIES.items())
    return f"""<!doctype html>
<html lang="{lang}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{head_title}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{path}">
<link rel="alternate" hreflang="ar" href="{SITE}{ar_path}">
<link rel="alternate" hreflang="en" href="{SITE}{en_path}">
<link rel="alternate" hreflang="x-default" href="{SITE}{ar_path}">
<meta property="og:site_name" content="{t['brand']}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}/logo.png">
<meta property="og:locale" content="{'ar_JO' if lang == 'ar' else 'en_JO'}">
<link rel="stylesheet" href="/style.css">
<link rel="icon" href="/logo.png">
{extra_head}</head>
<body>
<div class="stripe"></div>
<main>
<header><a href="{home_url(lang)}"><img src="/logo.png" alt="{t['brand']}" width="56" height="56"></a><div><div class="brand">{t['brand']}</div><div class="mute">{t['tag']}</div></div></header>
<nav><a href="{home_url(lang)}">{t['home']}</a>{nav}<a href="{pre(lang)}/deals">{t['nav_deals']}</a><a href="{pre(lang)}/guides">{t['nav_guides']}</a><a href="{pre(lang)}/shops">{t['nav_shops']}</a><a href="{pre(lang)}/search">{t['search_title']}</a><a href="{other_path}" lang="{other(lang)}">{t['other']}</a></nav>
{body}
<footer><p>{t['disclaimer']}</p><p><a href="/about{'#en' if lang == 'en' else ''}">{t['about']}</a> · <a href="/privacy{'#en' if lang == 'en' else ''}">{t['privacy']}</a> · <a href="/remove{'#en' if lang == 'en' else ''}">{t['owners']}</a> · <a href="/join{'#en' if lang == 'en' else ''}">{t['join']}</a> · <a href="{mailto(t['suggest_subj'], t['suggest_body'])}">{t['suggest']}</a> · © 2026 Derbani</p></footer>
</main>
</body>
</html>
"""


def card(v: dict, lang: str, note: str = "") -> str:
    t = T[lang]
    shops = t["one_shop"] if v["shops"] == 1 else t["n_shops"].format(n=v["shops"])
    was = f'<s class="mute">{t["was"].format(p=money(v["was"]))}</s>' if v.get("was") else ""
    return (f'<li><a href="{url(v, lang)}"><span class="name">{e(v["label"])}</span>'
            f'<span class="tag">{t["from"].format(p=money(v["best_price"]))}</span>{was}'
            f'<span class="mute">{e(note) if note else shops}</span></a></li>')


def answer(v: dict, lang: str, built: datetime) -> str:
    """One plain sentence that answers "how much is X in Jordan": what search engines and AI answers quote."""
    t = T[lang]
    ranked = [o for o in v["offers"] if o["rank"]]
    if len(ranked) == 1:
        high = t["answer_one"].format(shop=v["best_store"], p=money(v["best_price"]))
        return high + t["updated"].format(t=stamp(built))
    high = t["answer_high"].format(p=money(v["highest_price"]), x=money(v["save"])) if v["save"] > 0 else ""
    return t["answer"].format(name=v["label"], p=money(v["best_price"]), shop=v["best_store"], n=len(ranked), high=high,
                              t=stamp(built))


def product_page(v: dict, lang: str, siblings: list[dict], built: datetime) -> str:
    t = T[lang]
    name = v["label"]
    best = v["best_price"]
    title = t["price_of"].format(name=name)
    desc = t["desc"].format(name=name, n=v["shops"], p=money(best), shop=v["best_store"])
    rows = []
    for o in v["offers"]:
        is_best = o["rank"] and o["price"] == best
        state = t["out"] if not o["stock"] else (t["old"] if o["stale"] else t["in"])
        was = f' <s class="mute">{t["was"].format(p=money(o["was"]))}</s>' if o.get("was") and o["was"] > o["price"] else ""
        flag = f' <span class="flag">{t["best"]}</span>' if is_best else ""
        rows.append(
            f'<tr class="{"best" if is_best else ("dim" if not o["rank"] else "")}"><td><a href="{shop_url(o["store"], lang)}">{e(o["store"])}</a>{flag}</td>'
            f'<td class="num"><b>{money(o["price"])}</b> {t["jod"]}{was}</td><td>{state}</td><td class="num">{when(o["checked"])}</td>'
            f'<td><a class="go" href="{e(go_link(o, v["id"]))}" rel="nofollow noopener" target="_blank">{t["go"]}</a></td></tr>')
    record = ""
    if v.get("verdict"):
        day = lambda iso: datetime.fromisoformat(iso).strftime("%d/%m/%Y")
        verdict = {"lowest": t["v_lowest"], "flat": t["v_flat"],
                   "above_low": t["v_above"].format(p=money(v["record_low"]), d=day(v["record_low_at"]))}[v["verdict"]]
        cls = {"lowest": "good", "flat": "", "above_low": "warn"}[v["verdict"]]
        record = (f'<h2>{t["record"]}</h2><div class="record">'
                  f'<div><span class="mute">{t["rec_low"]}</span><b>{money(v["record_low"])} {t["jod"]}</b><span class="mute">{day(v["record_low_at"])}</span></div>'
                  f'<div><span class="mute">{t["rec_high"]}</span><b>{money(v["record_high"])} {t["jod"]}</b><span class="mute">{day(v["record_high_at"])}</span></div>'
                  f'</div><p class="verdict {cls}">{e(verdict)}</p><p class="mute">{t["rec_since"].format(d=day(v["tracked_since"]))}</p>')
    history = ""
    if len(v.get("history") or []) > 1:
        hist = "".join(f'<tr><td class="num">{e(h["d"])}</td><td class="num"><b>{money(h["p"])}</b> {t["jod"]}</td></tr>' for h in reversed(v["history"]))
        history = (f'<h2>{t["history"]}</h2><p class="mute">{t["history_hint"]}</p>'
                   f'<table class="hist"><thead><tr><th>{t["date"]}</th><th>{t["price"]}</th></tr></thead><tbody>{hist}</tbody></table>')
    more = ""
    if siblings:
        links = "".join(f'<a class="chip" href="{url(s, lang)}">{e(s["storage"])} · {money(s["best_price"])}</a>' for s in siblings)
        more = f'<h2>{t["more"].format(model=e(v["model"]))}</h2><div class="chips">{links}</div>'
    pic = picture(v)
    shot = f'<img class="shot" src="{e(pic)}" alt="{e(name)}" width="150" height="150" referrerpolicy="no-referrer">' if pic else ""
    gap = f'<div class="gap">{t["save"].format(x=money(v["save"]))}</div>' if v["save"] > 0 else ""
    ticket = (f'<div class="ticket"><div>{t["best"]} · {t["at"].format(shop=e(v["best_store"]))}</div>'
              f'<div class="big">{money(best)} <small>{t["jod"]}</small></div>{gap}</div>')
    gray = f'<p class="warn">{t["gray"]}</p>' if v["gray"] else ""
    from urllib.parse import quote
    wa_link = e("https://wa.me/?text=" + quote(t["wa_text"].format(name=name, p=money(best), shop=v["best_store"]) + "\n" + SITE + url(v, lang)))
    one = f'<p class="verdict">{e(t["one_note"])}</p>' if v["ranked_shops"] == 1 else ""
    ranked = [o for o in v["offers"] if o["rank"]]
    product_ld = ld({
        "@context": "https://schema.org", "@type": "Product", "name": name, "brand": {"@type": "Brand", "name": v["brand"]},
        "category": CATEGORIES[v["category"]][3], **({"image": pic} if pic else {}),
        "offers": {"@type": "AggregateOffer", "priceCurrency": "JOD", "lowPrice": min(o["price"] for o in ranked),
                   "highPrice": max(o["price"] for o in ranked), "offerCount": len(ranked),
                   "availability": "https://schema.org/InStock"},
    })
    cat = v["category"]
    path = crumbs(lang, [(CATEGORIES[cat][1 if lang == "ar" else 2], list_url(cat, lang)),
                         (v["brand_ar"] if lang == "ar" else v["brand"], brand_url(cat, v["brand"], lang)), (name, url(v, lang))])
    body = f"""<article>
{path}<h1>{e(title)}</h1>{gray}
<p class="answer">{e(answer(v, lang, built))}</p>
<div class="top">{shot}{ticket}</div>{one}
<h2>{t['all_shops']}</h2>
<div class="scroll"><table class="offers"><thead><tr><th>{t['shop']}</th><th>{t['price']}</th><th>{t['state']}</th><th>{t['checked']}</th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{record}{history}{more}
<p class="report"><a class="wa" href="{wa_link}" rel="noopener" target="_blank">{t['wa']}</a> <a href="{mailto(t['report_subj'].format(name=name), t['report_body'].format(name=name, link=SITE + url(v, lang)))}">{t['report']}</a></p>
<p class="mute">{t['updated'].format(t=stamp(built))}</p>
</article>"""
    return shell(lang, title, desc, url(v, lang), url(v, other(lang)), body, product_ld)


def grouped(items: list[dict], lang: str, category: str, link_brands: bool = True) -> str:
    by_brand: dict[str, list[dict]] = {}
    for v in items:
        by_brand.setdefault(v["brand"], []).append(v)
    parts = []
    for brand, vs in sorted(by_brand.items(), key=lambda kv: -len(kv[1])):
        name = vs[0]["brand_ar"] if lang == "ar" else brand
        head = f'<a href="{brand_url(category, brand, lang)}">{e(name)}</a>' if link_brands else e(name)
        cards = "".join(card(v, lang) for v in sorted(vs, key=lambda v: (-v["ranked_shops"], v["label"])))
        parts.append(f'<h2>{head}</h2><ul class="list">{cards}</ul>')
    return "".join(parts)


def list_page(category: str, items: list[dict], lang: str, guides: list[dict] | None = None) -> str:
    t = T[lang]
    mine = [g for g in guides or [] if g["category"] == category]
    cat = CATEGORIES[category][1 if lang == "ar" else 2]
    title = t["list_title"].format(cat=cat, one=CATEGORIES[category][3])
    lead = t["list_desc"].format(cat=cat, low=cat.lower())
    body = (crumbs(lang, [(cat, list_url(category, lang))]) + f"<h1>{e(title)}</h1><p class=\"mute\">{lead}</p>"
            + search_form(lang) + (f'<h2>{t["nav_guides"]}</h2>' + guide_chips(mine, lang) if mine else "") + grouped(items, lang, category))
    return shell(lang, title, lead, list_url(category, lang), list_url(category, other(lang)), body)


def brand_page(category: str, brand: str, items: list[dict], lang: str) -> str:
    t = T[lang]
    cat = CATEGORIES[category][1 if lang == "ar" else 2]
    bname = items[0]["brand_ar"] if lang == "ar" else brand
    words = dict(cat=cat, brand=bname, low=cat.lower(), one_low=CATEGORIES[category][3].lower(), bare=CATEGORIES[category][4])
    title = t["brand_title"].format(**words)
    lead = t["brand_desc"].format(**words)
    cards = "".join(card(v, lang) for v in sorted(items, key=lambda v: (-v["ranked_shops"], v["label"])))
    body = (crumbs(lang, [(cat, list_url(category, lang)), (bname, brand_url(category, brand, lang))])
            + f'<h1>{e(title)}</h1><p class="mute">{e(lead)}</p><ul class="list">{cards}</ul>')
    return shell(lang, title, lead, brand_url(category, brand, lang), brand_url(category, brand, other(lang)), body)


def shop_pages(data: list[dict], shops: dict[str, str], lang: str) -> dict[str, str]:
    """Address -> page, for the shops list and one page per shop."""
    t = T[lang]
    sold: dict[str, list[tuple[dict, dict]]] = {}
    for v in data:
        for o in v["offers"]:
            sold.setdefault(o["store"], []).append((v, o))
    out = {}
    rows = []
    for shop in sorted(sold, key=lambda s: -len(sold[s])):
        pairs = sold[shop]
        cheapest = sum(1 for v, o in pairs if o["rank"] and o["price"] == v["best_price"])
        rows.append(f'<li><a href="{shop_url(shop, lang)}"><span class="name">{e(shop)}</span>'
                    f'<span class="mute">{len(pairs)} {t["products"]} · {t["cheapest"]}: {cheapest}</span></a></li>')
        lines = []
        for v, o in sorted(pairs, key=lambda p: (p[0]["category"], p[0]["label"])):
            mine = o["rank"] and o["price"] == v["best_price"]
            tag = f'<span class="flag">{t["cheapest"]}</span>' if mine else f'<span class="mute">{t["best_elsewhere"]}: {money(v["best_price"])}</span>'
            lines.append(f'<tr class="{"best" if mine else ("dim" if not o["rank"] else "")}"><td><a href="{url(v, lang)}">{e(v["label"])}</a></td>'
                         f'<td class="num"><b>{money(o["price"])}</b> {t["jod"]}</td><td>{tag}</td></tr>')
        title = t["shop_title"].format(shop=shop)
        desc = t["shop_desc"].format(shop=shop)
        site = shops.get(shop)
        visit = f' <a class="go" href="{e(site)}" rel="nofollow noopener" target="_blank">{t["visit"]}</a>' if site else ""
        body = (crumbs(lang, [(t["nav_shops"], f"{pre(lang)}/shops"), (shop, shop_url(shop, lang))])
                + f'<h1>{e(title)}</h1><p>{e(t["shop_lead"].format(n=len(pairs), shop=shop, c=cheapest))}{visit}</p>'
                + f'<div class="scroll"><table><thead><tr><th>{t["product"]}</th><th>{t["price"]}</th><th></th></tr></thead><tbody>{"".join(lines)}</tbody></table></div>')
        out[shop_url(shop, lang)] = shell(lang, title, desc, shop_url(shop, lang), shop_url(shop, other(lang)), body)
    title, desc = t["shops_title"], t["shops_desc"]
    body = crumbs(lang, [(t["nav_shops"], f"{pre(lang)}/shops")]) + f'<h1>{e(title)}</h1><p class="mute">{e(desc)}</p><ul class="list">{"".join(rows)}</ul>'
    out[f"{pre(lang)}/shops"] = shell(lang, title, desc, f"{pre(lang)}/shops", f"{pre(other(lang))}/shops", body)
    return out


def guide_url(g: dict, lang: str) -> str:
    return f"{pre(lang)}/guides/{g['id']}"


def guide_chips(guides: list[dict], lang: str) -> str:
    return '<div class="chips">' + "".join(f'<a class="chip" href="{guide_url(g, lang)}">{e(g["title_" + lang])}</a>' for g in guides) + "</div>"


def guide_page(g: dict, lang: str, built: datetime) -> str:
    t = T[lang]
    title, intro = g["title_" + lang], g["intro_" + lang]
    cards = "".join(card(v, lang, note_ar if lang == "ar" else note_en) for v, note_ar, note_en in g["items"])
    data = ld({"@context": "https://schema.org", "@type": "ItemList", "name": title, "itemListOrder": "https://schema.org/ItemListOrderAscending",
               "numberOfItems": len(g["items"]),
               "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": SITE + url(v, lang), "name": v["label"]}
                                   for i, (v, _, _) in enumerate(g["items"])]})
    body = (crumbs(lang, [(t["nav_guides"], f"{pre(lang)}/guides"), (title, guide_url(g, lang))])
            + f'<h1>{e(title)}</h1><p class="lead">{e(intro)}</p><ol class="list">{cards}</ol>'
            + f'<p class="mute">{e(t["guides_honest"])} {t["updated"].format(t=stamp(built))}</p>')
    return shell(lang, title, intro, guide_url(g, lang), guide_url(g, other(lang)), body, data)


def guides_index(guides: list[dict], lang: str) -> str:
    t = T[lang]
    body = crumbs(lang, [(t["nav_guides"], f"{pre(lang)}/guides")]) + f'<h1>{e(t["guides_title"])}</h1><p class="lead">{e(t["guides_desc"])}</p>'
    for cat, names in CATEGORIES.items():
        mine = [g for g in guides if g["category"] == cat]
        if mine:
            body += f'<h2>{e(names[1 if lang == "ar" else 2])}</h2>' + guide_chips(mine, lang)
    body += f'<p class="mute">{e(t["guides_honest"])}</p>'
    return shell(lang, t["guides_title"], t["guides_desc"], f"{pre(lang)}/guides", f"{pre(other(lang))}/guides", body)


def drops_and_gaps(data: list[dict]) -> tuple[list[dict], list[dict]]:
    live = [v for v in data if not v["gray"]]
    drops = sorted((v for v in live if v.get("drop", 0) >= 1), key=lambda v: (-v["drop_pct"], v["label"]))
    gaps = sorted((v for v in live if v["ranked_shops"] >= 2 and v["save"] >= 5), key=lambda v: (-v["save"], v["label"]))
    return drops, gaps


def deals_page(data: list[dict], lang: str) -> str:
    t = T[lang]
    drops, gaps = drops_and_gaps(data)
    body = crumbs(lang, [(t["nav_deals"], f"{pre(lang)}/deals")]) + f'<h1>{e(t["deals_title"])}</h1><p class="mute">{e(t["deals_desc"])}</p>'
    if drops:
        body += f'<h2>{t["drops"]}</h2><ul class="list">' + "".join(card(v, lang, t["drop_note"].format(x=f'{v["drop_pct"]:g}', shop=v["best_store"])) for v in drops[:60]) + "</ul>"
    body += f'<h2>{t["gaps"]}</h2><ul class="list">' + "".join(card(v, lang, t["save"].format(x=money(v["save"]))) for v in gaps[:60]) + "</ul>"
    return shell(lang, t["deals_title"], t["deals_desc"], f"{pre(lang)}/deals", f"{pre(other(lang))}/deals", body)


def faq(lang: str, shop_names: list[str]) -> tuple[str, str]:
    t = T[lang]
    sep = "، " if lang == "ar" else ", "
    names = sep.join(shop_names[:6])
    pairs = [(t[f"q{i}"], t[f"a{i}"].format(s=len(shop_names), names=names)) for i in range(1, 6)]
    visible = f'<h2>{t["faq"]}</h2>' + "".join(f"<h3>{e(q)}</h3><p>{e(a)}</p>" for q, a in pairs)
    data = ld({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]})
    return visible, data


def home_page(data: list[dict], shop_names: list[str], lang: str, built: datetime, guides: list[dict] | None = None) -> str:
    t = T[lang]
    drops, gaps = drops_and_gaps(data)
    popular = sorted((v for v in data if not v["gray"] and v["ranked_shops"] >= 2), key=lambda v: (-v["ranked_shops"], v["best_price"]))[:12]
    cats = "".join(f'<a class="chip" href="{list_url(c, lang)}">{n[1 if lang == "ar" else 2]} ({sum(1 for v in data if v["category"] == c)})</a>'
                   for c, n in CATEGORIES.items())
    shops = "".join(f'<a class="chip" href="{shop_url(s, lang)}">{e(s)}</a>' for s in shop_names)
    see = lambda href: f'<p><a href="{href}">{t["see_all"]} ›</a></p>'
    body = f'<h1>{e(t["home_h1"])}</h1><p class="lead">{e(t["home_lead"].format(p=len(data), s=len(shop_names), t=stamp(built)))}</p>'
    body += search_form(lang) + f'<div class="chips cats">{cats}</div>'
    if drops:
        body += f'<h2>{t["drops"]}</h2><ul class="list">' + "".join(card(v, lang, t["drop_note"].format(x=f'{v["drop_pct"]:g}', shop=v["best_store"])) for v in drops[:6]) + "</ul>" + see(f"{pre(lang)}/deals")
    body += f'<h2>{t["gaps"]}</h2><ul class="list">' + "".join(card(v, lang, t["save"].format(x=money(v["save"]))) for v in gaps[:6]) + "</ul>" + see(f"{pre(lang)}/deals")
    body += f'<h2>{t["popular"]}</h2><ul class="list">' + "".join(card(v, lang) for v in popular) + "</ul>"
    if guides:
        body += f'<h2>{t["nav_guides"]}</h2>' + guide_chips(guides[:10], lang) + see(f"{pre(lang)}/guides")
    body += f'<h2>{t["shops_we"]}</h2><div class="chips">{shops}</div>'
    visible, faq_ld = faq(lang, shop_names)
    body += visible
    site_ld = ld({"@context": "https://schema.org", "@graph": [
        {"@type": "Organization", "@id": SITE + "/#org", "name": "Derbani", "alternateName": "درباني", "url": SITE + "/",
         "logo": SITE + "/logo.png", "email": "contact@derbani.com", "areaServed": "JO"},
        {"@type": "WebSite", "@id": SITE + "/#site", "name": "درباني - Derbani", "alternateName": ["Derbani", "درباني"], "url": SITE + "/",
         "inLanguage": ["ar", "en"], "publisher": {"@id": SITE + "/#org"},
         "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": SITE + "/search?q={search_term_string}"},
                             "query-input": "required name=search_term_string"}}]})
    desc = t["home_desc"].format(s=len(shop_names))
    return shell(lang, t["home_title"], desc, home_url(lang), home_url(other(lang)), body, site_ld + faq_ld, full_title=True)


def search_page(lang: str) -> str:
    t = T[lang]
    body = (f'<h1>{t["search_title"]}</h1>' + search_form(lang) + f'<p id="status" class="mute">{t["search_none"]}</p>'
            + f'<ul class="list" id="results"></ul><script src="/search.js" defer></script>')
    path = f"{pre(lang)}/search"
    page = shell(lang, t["search_title"], t["home_desc"].format(s=""), path, f"{pre(other(lang))}/search", body)
    return page.replace("<head>", '<head>\n<meta name="robots" content="noindex,follow">', 1)  # result pages are not for search engines


def search_index(data: list[dict]) -> str:
    rows = []
    for v in data:
        text, compact, _ = haystack(v["label"], v["brand"], v["brand_ar"], v["storage_gb"])
        rows.append({"n": v["label"], "u": slug(v), "p": v["best_price"], "s": v["shops"], "c": v["category"], "h": text, "k": compact,
                     "r": v["ranked_shops"]})
    letters = {chr(k): (v if isinstance(v, str) else chr(v) if v is not None else "") for k, v in _LETTERS.items()}
    return json.dumps({"words": AR_WORDS, "phrases": {fold(k): v for k, v in AR_PHRASES.items()}, "stop": sorted(fold(w) for w in STOP_WORDS),
                       "letters": letters, "items": rows}, ensure_ascii=False, separators=(",", ":"))


def llms_txt(data: list[dict], shop_names: list[str], built: datetime, guides: list[dict] | None = None) -> str:
    """A plain-text guide for AI tools (the llms.txt convention): what the site is, where the answers are."""
    lines = [
        "# Derbani (درباني)",
        "",
        "> Derbani compares the prices of new phones and tablets across shops in Jordan. Prices are read from the shops'",
        f"> public pages every hour; each product page lists the price at every shop, stock, last check time and price history.",
        f"> {len(data)} products from {len(shop_names)} shops. Last update {stamp(built)} Amman time. Prices are in Jordanian dinars (JOD).",
        "",
        "Derbani does not sell anything and ranks by price only (no paid placement). Arabic pages are at /, English at /en.",
        "",
        "## Main pages",
        f"- [Phone prices in Jordan]({SITE}/en/phones): every phone, grouped by brand",
        f"- [Tablet prices in Jordan]({SITE}/en/tablets): every tablet, grouped by brand",
        f"- [Deals]({SITE}/en/deals): price drops this week and the biggest gaps between shops",
        f"- [Shops]({SITE}/en/shops): the shops compared: {', '.join(shop_names)}",
        f"- [About]({SITE}/about): how prices are collected",
        "",
        f"- [Buying guides]({SITE}/en/guides): budgets, lowest prices ever and the biggest gaps, from today's prices",
        *[f"  - [{g['title_en']}]({SITE}{guide_url(g, 'en')})" for g in (guides or [])],
        "",
        "## Most compared products",
    ]
    top = sorted((v for v in data if not v["gray"]), key=lambda v: (-v["ranked_shops"], v["label"]))[:40]
    lines += [f"- [{v['label']}]({SITE}{url(v, 'en')}): from {money(v['best_price'])} JOD at {v['best_store']}, {v['shops']} shops" for v in top]
    return "\n".join(lines) + "\n"


def build(s: Session, out: Path, static: Path, now: datetime | None = None, shop_sites: dict[str, str] | None = None) -> dict[str, int]:
    """Writes the whole site into `out` (emptied first). Only products with a ranked price get a page."""
    now = now or datetime.now(timezone.utc)
    data = [v for v in build_variant_data(s, now) if v["best_price"] is not None and v["category"] in CATEGORIES]
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(static, out)
    by_model: dict[tuple, list[dict]] = {}
    for v in data:
        by_model.setdefault((v["model"], v["gray"]), []).append(v)
    counts: dict[str, int] = {}
    for v in data:
        for o in v["offers"]:
            counts[o["store"]] = counts.get(o["store"], 0) + 1
    shop_names = sorted(counts, key=lambda n: -counts[n])
    guides = build_guides(data, CATEGORIES)
    pages: dict[str, str] = {}
    for lang in ("ar", "en"):
        pages[home_url(lang)] = home_page(data, shop_names, lang, now, guides)
        pages[f"{pre(lang)}/guides"] = guides_index(guides, lang)
        for g in guides:
            pages[guide_url(g, lang)] = guide_page(g, lang, now)
        pages[f"{pre(lang)}/deals"] = deals_page(data, lang)
        pages[f"{pre(lang)}/search"] = search_page(lang)
        pages.update(shop_pages(data, shop_sites or {}, lang))
        for v in data:
            sibs = sorted((x for x in by_model[(v["model"], v["gray"])] if x["id"] != v["id"]), key=lambda x: (x["storage_gb"] or 0, x["label"]))
            pages[url(v, lang)] = product_page(v, lang, sibs, now)
        for category in CATEGORIES:
            items = [v for v in data if v["category"] == category]
            pages[list_url(category, lang)] = list_page(category, items, lang, guides)
            brands: dict[str, list[dict]] = {}
            for v in items:
                brands.setdefault(v["brand"], []).append(v)
            for brand, vs in brands.items():
                pages[brand_url(category, brand, lang)] = brand_page(category, brand, vs, lang)
    for address, page in pages.items():
        f = out / file_of(address)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(page, encoding="utf-8")
    (out / "search-index.json").write_text(search_index(data), encoding="utf-8")
    (out / "go-map.json").write_text(json.dumps(go_map(data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "llms.txt").write_text(llms_txt(data, shop_names, now, guides), encoding="utf-8")
    listed = [a for a in pages if not a.endswith("/search")] + ["/about", "/privacy", "/remove", "/join"]
    day = now.strftime("%Y-%m-%d")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{SITE}{a}</loc><lastmod>{day}</lastmod></url>\n" for a in listed) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /search\nDisallow: /en/search\nDisallow: /go/\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    return {"products": len(data), "pages": len(listed), "shops": len(shop_names), "guides": len(guides)}
