"""Builds the public website: one plain page per product (Arabic and English), a list page per category, a sitemap.
Pages are static files with no scripts, so they are fast and search engines can read them. The hand-written pages in
`web/` (home, privacy, shop owners, join) are copied next to them. Rebuilt from the database on every run.

Layout of the output folder:
    /p/<id>-<name>.html        Arabic product page        /en/p/<id>-<name>.html   English product page
    /phones.html /tablets.html Arabic lists               /en/phones.html ...      English lists
    /sitemap.xml /robots.txt
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .views import build_variant_data

SITE = "https://derbani.com"
AMMAN = timezone(timedelta(hours=3))
# file name, Arabic name, English name, English singular (for "Phone prices in Jordan")
CATEGORIES = {"phone": ("phones", "الموبايلات", "Phones", "Phone"), "tablet": ("tablets", "التابلت", "Tablets", "Tablet")}

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
        "owners": "لأصحاب المتاجر", "desc": "قارن سعر {name} بين {n} متاجر في الأردن. أفضل سعر الآن {p} د.أ عند {shop}.",
        "list_desc": "قارن أسعار {cat} الجديدة بين متاجر الأردن واعرف أرخص متجر لكل جهاز.",
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
        "owners": "For shop owners", "desc": "Compare the price of {name} across {n} shops in Jordan. Best price now {p} JOD at {shop}.",
        "list_desc": "Compare the prices of new {low} across shops in Jordan and find the cheapest shop for each device.",
    },
}


def money(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def slug(v: dict) -> str:
    return f"{v['id']}-" + re.sub(r"[^a-z0-9]+", "-", v["label"].lower()).strip("-")


# Addresses carry no ".html": the host serves /p/27-name from the file p/27-name.html and redirects the long form to it,
# so linking the short form avoids a redirect on every visit (and gives search engines one address per page).
def url(v: dict, lang: str) -> str:
    return f"{'/en' if lang == 'en' else ''}/p/{slug(v)}"


def list_url(category: str, lang: str) -> str:
    return f"{'/en' if lang == 'en' else ''}/{CATEGORIES[category][0]}"


def file_of(address: str) -> str:
    return address.lstrip("/") + ".html"


def picture(v: dict) -> str | None:
    """The shop picture to link. The list starts with the full-size original (often several megabytes) followed by the
    shop's own smaller copy of it; a web page should load the smaller one."""
    pics = v.get("images") or []
    if len(pics) > 1 and re.search(r"-\d{2,4}x\d{2,4}\.\w+$", pics[1]) and not re.search(r"-\d{2,4}x\d{2,4}\.\w+$", pics[0]):
        return pics[1]
    return pics[0] if pics else None


def when(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(AMMAN).strftime("%d/%m %H:%M")


def e(text) -> str:
    return html.escape(str(text), quote=True)


def shell(lang: str, title: str, desc: str, path: str, other_path: str, body: str, extra_head: str = "") -> str:
    t = T[lang]
    ar_path, en_path = (path, other_path) if lang == "ar" else (other_path, path)
    home = "/en/phones" if lang == "en" else "/"
    return f"""<!doctype html>
<html lang="{lang}" dir="{t['dir']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} | {t['brand']}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{path}">
<link rel="alternate" hreflang="ar" href="{SITE}{ar_path}">
<link rel="alternate" hreflang="en" href="{SITE}{en_path}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE}{path}">
<link rel="stylesheet" href="/style.css">
<link rel="icon" href="/logo.png">
{extra_head}</head>
<body>
<div class="stripe"></div>
<main>
<header><a href="{home}"><img src="/logo.png" alt="{t['brand']}" width="56" height="56"></a><div><div class="brand">{t['brand']}</div><div class="mute">{t['tag']}</div></div></header>
<nav><a href="{home}">{t['home']}</a>{''.join(f'<a href="{list_url(c, lang)}">{names[1 if lang == "ar" else 2]}</a>' for c, names in CATEGORIES.items())}<a href="{other_path}" lang="{'en' if lang == 'ar' else 'ar'}">{t['other']}</a></nav>
{body}
<footer><p>{t['disclaimer']}</p><p><a href="/privacy{'#en' if lang == 'en' else ''}">{t['privacy']}</a> · <a href="/remove{'#en' if lang == 'en' else ''}">{t['owners']}</a> · © 2026 Derbani</p></footer>
</main>
</body>
</html>
"""


def product_page(v: dict, lang: str, siblings: list[dict], built: datetime) -> str:
    t = T[lang]
    name = v["label"]
    best = v["best_price"]
    title = t["price_of"].format(name=name)
    desc = (t["desc"].format(name=name, n=v["shops"], p=money(best), shop=v["best_store"]) if best is not None
            else title)
    rows = []
    for o in v["offers"]:
        is_best = o["rank"] and best is not None and o["price"] == best
        state = t["out"] if not o["stock"] else (t["old"] if o["stale"] else t["in"])
        was = f' <s class="mute">{t["was"].format(p=money(o["was"]))}</s>' if o.get("was") and o["was"] > o["price"] else ""
        rows.append(
            f'<tr class="{"best" if is_best else ("dim" if not o["rank"] else "")}"><td>{e(o["store"])}'
            f'{f" <span class=\"flag\">{t["best"]}</span>" if is_best else ""}</td>'
            f'<td class="num"><b>{money(o["price"])}</b> {t["jod"]}{was}</td><td>{state}</td><td class="num">{when(o["checked"])}</td>'
            f'<td><a class="go" href="{e(o["url"])}" rel="nofollow noopener" target="_blank">{t["go"]}</a></td></tr>')
    history = ""
    if len(v.get("history") or []) > 1:
        hist = "".join(f'<tr><td class="num">{e(h["d"])}</td><td class="num"><b>{money(h["p"])}</b> {t["jod"]}</td></tr>' for h in reversed(v["history"]))
        history = (f'<h2>{t["history"]}</h2><p class="mute">{t["history_hint"]}</p>'
                   f'<table class="hist"><thead><tr><th>{t["date"]}</th><th>{t["price"]}</th></tr></thead><tbody>{hist}</tbody></table>')
    more = ""
    if siblings:
        links = "".join(f'<a class="chip" href="{url(s, lang)}">{e(s["storage"])}'
                        f'{f" · {money(s["best_price"])}" if s["best_price"] is not None else ""}</a>' for s in siblings)
        more = f'<h2>{t["more"].format(model=e(v["model"]))}</h2><div class="chips">{links}</div>'
    pic = picture(v)
    shot = (f'<img class="shot" src="{e(pic)}" alt="{e(name)}" width="150" height="150" referrerpolicy="no-referrer">' if pic else "")
    ticket = ""
    if best is not None:
        gap = f'<div class="gap">{t["save"].format(x=money(v["save"]))}</div>' if v["save"] > 0 else ""
        ticket = (f'<div class="ticket"><div>{t["best"]} · {t["at"].format(shop=e(v["best_store"]))}</div>'
                  f'<div class="big">{money(best)} <small>{t["jod"]}</small></div>{gap}</div>')
    gray = f'<p class="warn">{t["gray"]}</p>' if v["gray"] else ""
    ld = ""
    ranked = [o for o in v["offers"] if o["rank"]]
    if ranked:
        ld = '<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@type": "Product", "name": name, "brand": {"@type": "Brand", "name": v["brand"]},
            **({"image": picture(v)} if picture(v) else {}),
            "offers": {"@type": "AggregateOffer", "priceCurrency": "JOD", "lowPrice": min(o["price"] for o in ranked),
                       "highPrice": max(o["price"] for o in ranked), "offerCount": len(ranked),
                       "availability": "https://schema.org/InStock"},
        }, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"
    body = f"""<article>
<h1>{e(title)}</h1>{gray}
<div class="top">{shot}{ticket}</div>
<h2>{t['all_shops']}</h2>
<div class="scroll"><table class="offers"><thead><tr><th>{t['shop']}</th><th>{t['price']}</th><th>{t['state']}</th><th>{t['checked']}</th><th></th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{history}{more}
<p class="mute">{t['updated'].format(t=built.astimezone(AMMAN).strftime('%d/%m/%Y %H:%M'))}</p>
</article>"""
    return shell(lang, title, desc, url(v, lang), url(v, "en" if lang == "ar" else "ar"), body, ld)


def list_page(category: str, items: list[dict], lang: str) -> str:
    t = T[lang]
    cat = CATEGORIES[category][1 if lang == "ar" else 2]
    one = CATEGORIES[category][3]
    title = t["list_title"].format(cat=cat, one=one)
    lead = t["list_desc"].format(cat=cat, low=cat.lower())
    by_brand: dict[str, list[dict]] = {}
    for v in items:
        by_brand.setdefault(v["brand_ar"] if lang == "ar" else v["brand"], []).append(v)
    parts = []
    for brand, vs in sorted(by_brand.items(), key=lambda kv: -len(kv[1])):
        cards = "".join(
            f'<li><a href="{url(v, lang)}"><span class="name">{e(v["label"])}</span>'
            f'<span class="tag">{t["from"].format(p=money(v["best_price"]))}</span>'
            f'<span class="mute">{t["one_shop"] if v["shops"] == 1 else t["n_shops"].format(n=v["shops"])}</span></a></li>'
            for v in sorted(vs, key=lambda v: (-v["ranked_shops"], v["label"])))
        parts.append(f"<h2>{e(brand)}</h2><ul class=\"list\">{cards}</ul>")
    body = f"<h1>{e(title)}</h1><p class=\"mute\">{lead}</p>{''.join(parts)}"
    return shell(lang, title, lead, list_url(category, lang), list_url(category, "en" if lang == "ar" else "ar"), body)


def build(s: Session, out: Path, static: Path, now: datetime | None = None) -> dict[str, int]:
    """Writes the whole site into `out` (emptied first). Only products with a ranked price get a page."""
    now = now or datetime.now(timezone.utc)
    data = [v for v in build_variant_data(s, now) if v["best_price"] is not None and v["category"] in CATEGORIES]
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(static, out)
    by_model: dict[tuple, list[dict]] = {}
    for v in data:
        by_model.setdefault((v["model"], v["gray"]), []).append(v)
    pages: list[str] = []
    for lang in ("ar", "en"):
        base = out / "en" if lang == "en" else out
        (base / "p").mkdir(parents=True, exist_ok=True)
        for v in data:
            sibs = sorted((x for x in by_model[(v["model"], v["gray"])] if x["id"] != v["id"]), key=lambda x: (x["storage_gb"] or 0, x["label"]))
            (out / file_of(url(v, lang))).write_text(product_page(v, lang, sibs, now), encoding="utf-8")
            pages.append(url(v, lang))
        for category in CATEGORIES:
            items = [v for v in data if v["category"] == category]
            (out / file_of(list_url(category, lang))).write_text(list_page(category, items, lang), encoding="utf-8")
            pages.append(list_url(category, lang))
    fixed = ["/", "/privacy", "/remove", "/join"]
    stamp = now.strftime("%Y-%m-%d")
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{SITE}{p}</loc><lastmod>{stamp}</lastmod></url>\n" for p in fixed + pages) + "</urlset>\n", encoding="utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n", encoding="utf-8")
    return {"products": len(data), "pages": len(pages) + len(fixed)}
