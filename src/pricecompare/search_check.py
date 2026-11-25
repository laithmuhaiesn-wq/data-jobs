"""The nightly search test (2026-11-25: "ps5" found nothing and nobody knew). Runs searches people in Jordan really type, and
searches made from every product's own name, on the website's rules (web/search.js, with node), the app's rules
(app/lib/local_search.dart, with dart when it is installed) and the API's rules (search.py), over the last built files.
What fails goes to ~/.derbani/search_problems.json; the daily doctor fixes the words or the rules.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .search import AR_WORDS, find, fold

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "web_build"
REPORT = Path.home() / ".derbani" / "search_problems.json"
KEEP = 300   # problems written to the report; the count is always the full one

# (what is typed, what most of the first results must be: a pattern over "category|product name").
# When nothing on sale matches the pattern the search is not tested. Add every failed search worth finding here.
CASES: list[tuple[str, str]] = [
    # phones
    ("iphone 17", r"^phone\|iPhone 17"), ("ايفون 17", r"^phone\|iPhone 17"), ("ايفون ١٧ برو ماكس", r"iPhone 17 Pro Max"), ("iphone17promax", r"iPhone 17 Pro Max"),
    ("ايفون 16", r"^phone\|iPhone 16"), ("اي فون 15", r"^phone\|iPhone 15"), ("i phone 17 pro", r"iPhone 17 Pro"), ("ipone 17", r"iPhone 17"), ("ifone 17", r"iPhone 17"),
    ("iphone 17 pro max 256", r"iPhone 17 Pro Max 256"), ("iphone 17 pro max 256 gb", r"iPhone 17 Pro Max 256"), ("سعر ايفون 17 برو في الاردن", r"iPhone 17 Pro"),
    ("ايفون اير", r"iPhone (17 )?Air"), ("جوال ايفون", r"^phone\|iPhone"), ("موبايل", r"^phone\|"), ("phone", r"^phone\|"), ("هاتف سامسونج", r"^phone\|Samsung"),
    ("سامسونج", r"\|Samsung"), ("سامسونغ", r"\|Samsung"), ("samsng", r"\|Samsung"), ("sumsung", r"\|Samsung"), ("جالكسي", r"Galaxy"), ("غالاكسي", r"Galaxy"), ("galxy", r"Galaxy"),
    ("s26 ultra", r"S26 Ultra"), ("اس 26 الترا", r"S26 Ultra"), ("اس 25 الترا", r"S25 Ultra"), ("s25ultra", r"S25 Ultra"), ("a57", r"A57"), ("اي 57", r"A57"), ("a 56", r"A56"),
    ("a17", r"A17"), ("a07", r"A07"), ("samsung a56", r"A56"), ("زد فولد 7", r"Z Fold ?7"), ("z flip 7", r"Galaxy Z Flip ?7"), ("جالكسي فليب 7", r"Galaxy Z Flip ?7"),
    ("شاومي", r"\|Xiaomi"), ("xiomi", r"\|Xiaomi"), ("ريدمي نوت 15", r"Redmi Note 15"), ("redmi note 15 pro", r"Redmi Note 15 Pro"), ("نوت 15 برو", r"Note 15 Pro"),
    ("بوكو", r"Poco"), ("poco x7", r"Poco X7"), ("هونر", r"\|Honor"), ("اونر", r"\|Honor"), ("honor 400", r"Honor 400"), ("honer x9d", r"X9d"), ("هواوي", r"\|Huawei"), ("hauwei", r"\|Huawei"),
    ("انفينكس", r"\|Infinix"), ("infinix hot 60", r"Hot 60"), ("انفنكس نوت", r"Infinix Note"), ("تكنو", r"\|Tecno"), ("tecno spark", r"Tecno Spark"), ("techno camon", r"Tecno Camon"), ("تكنو سبارك", r"Spark"),
    ("اوبو", r"\|Oppo"), ("oppo a6", r"Oppo A6"), ("اوبو رينو", r"Oppo Reno"), ("ريلمي", r"\|Realme"), ("realme", r"\|Realme"), ("موتورولا", r"\|Motorola"), ("motorola edge", r"Motorola Edge"),
    # tablets
    ("ايباد", r"^tablet\|iPad"), ("اي باد", r"^tablet\|iPad"), ("ipad air", r"iPad Air"), ("ايباد اير 11", r"iPad Air 11"), ("ipad pro 13", r"iPad Pro 13"), ("ايباد ميني", r"iPad Mini"),
    ("تابلت", r"^tablet\|"), ("تابلت سامسونج", r"^tablet\|Samsung"), ("tablet", r"^tablet\|"), ("تابلت هونر", r"^tablet\|Honor"), ("galaxy tab a11", r"Tab A11"), ("تاب اس 11", r"Tab S11"), ("ميت باد", r"MatePad"),
    ("قلم ابل", r"Apple Pencil"), ("apple pencil", r"Apple Pencil"),
    # laptops and computers
    ("لابتوب", r"^laptop\|"), ("لاب توب", r"^laptop\|"), ("laptop", r"^laptop\|"), ("labtop", r"^laptop\|"), ("lap top", r"^laptop\|"), ("لابتوب hp", r"^laptop\|HP"), ("لابتوب اتش بي", r"^laptop\|HP"),
    ("لابتوب لينوفو", r"^laptop\|Lenovo"), ("لابتوب ديل", r"^laptop\|Dell"), ("لابتوب اسوس", r"^laptop\|Asus"), ("لابتوب جيمنج", r"^laptop\|"), ("gaming laptop", r"^laptop\|"), ("laptop i7", r"^laptop\|.*i7"),
    ("laptop rtx 5050", r"^laptop\|.*RTX 5050"), ("macbook", r"MacBook"), ("ماك بوك", r"MacBook"), ("ماك بوك اير", r"MacBook Air"), ("macbook air m5", r"MacBook Air.*M5"), ("macbook pro", r"MacBook Pro"), ("ماكبوك برو", r"MacBook Pro"),
    ("thinkpad", r"Thinkpad"), ("vivobook", r"Vivobook"), ("victus", r"Victus"), ("كمبيوتر", r"^(desktop|laptop)\|"), ("imac", r"iMac"), ("ايماك", r"iMac"), ("mac mini", r"Mac Mini"), ("ماك ميني", r"Mac Mini"),
    ("pc", r"^desktop\|"), ("desktop", r"^desktop\|"),
    # televisions and monitors
    ("تلفزيون", r"^tv\|"), ("تلفاز", r"^tv\|"), ("tv", r"^tv\|"), ("tv 65", r"^tv\|.*65"), ("تلفزيون سامسونج", r"^tv\|Samsung"), ("شاشة سامسونج 55", r"Samsung 55"), ("شاشة", r"^(tv|monitor)\|"), ("شاشات", r"^(tv|monitor)\|"),
    ("شاشة ال جي 65", r"LG 65"), ("lg oled", r"LG.*OLED"), ("شاشة 55 بوصة", r"^(tv|monitor)\|.*55"), ("تي سي ال", r"\|TCL"), ("شاشة كمبيوتر 27", r"^monitor\|.*27"), ("monitor 27", r"^monitor\|.*27"),
    ("gaming monitor", r"^monitor\|"), ("شاشة جيمنج", r"^monitor\|"), ("samsung odyssey", r"Odyssey"), ("هايسنس", r"\|Hisense"), ("سمارت تي في", r"^tv\|"),
    # watches
    ("ساعة", r"^watch\|"), ("ساعة ذكية", r"^watch\|"), ("smart watch", r"^watch\|"), ("smartwatch", r"^watch\|"), ("ساعة ابل", r"^watch\|Apple"), ("ساعة آبل", r"^watch\|Apple"), ("apple watch", r"Apple Watch"), ("apple watch series 11", r"Watch Series 11"),
    ("ابل ووتش", r"Apple Watch"), ("ساعة هواوي", r"^watch\|Huawei"), ("huawei watch fit", r"Huawei Watch Fit"), ("galaxy watch", r"Galaxy Watch"), ("ساعة سامسونج", r"^watch\|Samsung"), ("ساعات شاومي", r"^watch\|Xiaomi"), ("mi band", r"Xiaomi.*Band"),
    # sound
    ("سماعة", r"^(audio|speaker|smarthome)\|"), ("سماعات", r"^(audio|speaker|smarthome)\|"), ("سماعات بلوتوث", r"^(audio|speaker)\|"), ("سماعات لاسلكية", r"^(audio|speaker)\|"), ("headphones", r"^audio\|"), ("headphone", r"^audio\|"),
    ("headset", r"^audio\|"), ("earbuds", r"^audio\|"), ("airpods", r"AirPods"), ("ايربودز", r"AirPods"), ("اير بودز", r"AirPods"), ("airpods pro", r"AirPods Pro"), ("ايربودز برو 3", r"AirPods Pro 3"), ("air pods", r"AirPods"), ("ايربود", r"AirPods"),
    ("galaxy buds", r"Galaxy Buds"), ("سماعات جيمنج", r"^audio\|"), ("سماعة راس", r"^audio\|"), ("jbl", r"\|JBL"), ("جي بي ال", r"\|JBL"), ("سماعة jbl", r"\|JBL"), ("jbl flip", r"JBL Flip"), ("سبيكر", r"^(speaker|smarthome)\|"), ("speaker", r"^(speaker|smarthome)\|"),
    ("سبيكر جي بي ال", r"^speaker\|JBL"), ("partybox", r"PartyBox"), ("soundbar", r"^speaker\|"), ("ساوند بار", r"^speaker\|"), ("سماعة انكر", r"\|Anker"), ("hyperx cloud", r"HyperX Cloud"),
    # games
    ("ps5", r"PlayStation 5"), ("ps 5", r"PlayStation 5"), ("playstation", r"PlayStation"), ("playstaion 5", r"PlayStation 5"), ("play station 5", r"PlayStation 5"), ("بلايستيشن", r"PlayStation"), ("بلاي ستيشن 5", r"PlayStation 5"), ("بلستيشن 5", r"PlayStation 5"),
    ("بلايستيشن ٥", r"PlayStation 5"), ("سوني 5", r"\|Sony"), ("ps5 pro", r"PlayStation 5 Pro"), ("ps5 slim", r"PlayStation 5 Slim"), ("xbox", r"Xbox"), ("اكس بوكس", r"Xbox"), ("xbox series x", r"Xbox Series"), ("نينتندو سويتش", r"Nintendo Switch"), ("nintendo switch 2", r"Nintendo Switch 2"),
    # computer things
    ("طابعة", r"^printer\|"), ("printer", r"^printer\|"), ("طابعة hp", r"^printer\|HP"), ("طابعة كانون", r"^printer\|Canon"), ("epson", r"\|Epson"), ("ابسون", r"\|Epson"), ("برنتر", r"^printer\|"),
    ("راوتر", r"^router\|"), ("router", r"^router\|"), ("راوتر تي بي لينك", r"^router\|TP-Link"), ("tp link", r"\|TP-Link"), ("tplink", r"\|TP-Link"), ("مودم", r"^router\|"), ("مقوي واي فاي", r"^router\|"), ("wifi extender", r"^router\|"),
    ("باور بانك", r"^powerbank\|"), ("باوربانك", r"^powerbank\|"), ("power bank", r"^powerbank\|"), ("powerbank 20000", r"^powerbank\|.*20,000"), ("باور بانك انكر", r"^powerbank\|Anker"),
    ("هارد", r"^storage\|"), ("هارد ديسك", r"^storage\|"), ("هارد خارجي", r"^storage\|"), ("ssd", r"^storage\|"), ("ssd 1tb", r"^storage\|.*1TB"), ("فلاشة", r"^storage\|"), ("flash 64", r"^storage\|.*64GB"), ("usb flash", r"^storage\|"),
    ("كيبورد", r"^(peripheral|tabletacc)\|"), ("keyboard", r"^(peripheral|tabletacc)\|"), ("كيبورد جيمنج", r"^peripheral\|"), ("ماوس", r"^peripheral\|"), ("mouse", r"^peripheral\|"), ("ماوس لوجيتك", r"^peripheral\|Logitech"), ("gaming mouse", r"^peripheral\|"),
    ("ماوس لاسلكي", r"^peripheral\|"), ("mx master", r"MX Master"), ("لوجيتك", r"\|Logitech"), ("logitec", r"\|Logitech"), ("ريزر", r"\|Razer"), ("كرت شاشة", r"^pcpart\|"), ("rtx 5060", r"RTX 5060"), ("graphics card", r"^pcpart\|"), ("معالج", r"^pcpart\|"), ("processor", r"^pcpart\|"), ("معالج انتل", r"^pcpart\|Intel"), ("ryzen 7", r"Ryzen 7"),
    # cameras and home
    ("كاميرا", r"^camera\|"), ("camera", r"^camera\|"), ("كاميرا مراقبة", r"^camera\|"), ("كاميرات مراقبة", r"^camera\|"), ("كاميرا كانون", r"^camera\|Canon"), ("gopro", r"GoPro"), ("جو برو", r"GoPro"), ("webcam", r"^camera\|"), ("ويب كام", r"^camera\|"), ("security camera", r"^camera\|"),
    ("بروجكتر", r"^projector\|"), ("بروجكتور", r"^projector\|"), ("projector", r"^projector\|"), ("داتا شو", r"^projector\|"), ("مكنسة روبوت", r"Robot Vacuum"), ("robot vacuum", r"Robot Vacuum"), ("جرس", r"Doorbell"), ("اليكسا", r"Echo"), ("alexa", r"Echo"),
]


def _slip(name: str) -> str | None:
    """The name with one typing slip: two neighbouring letters swapped inside its longest plain word."""
    words = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 6]
    if not words:
        return None
    w = max(words, key=len)
    i = len(w) // 2
    bad = w[:i] + w[i + 1] + w[i] + w[i + 2:] if w[i] != w[i + 1] else w[:i] + w[i + 1:]
    return re.sub(rf"\b{w}\b", bad, name.lower(), count=1)


def own_searches(p: dict) -> dict[str, str]:
    """Searches made from a product's own name, every one of which must find it."""
    name, brand = p["label"], p["brand"]
    out = {"name": name, "model": p.get("model") or name}
    bare = re.sub(rf"^{re.escape(brand)}\s+", "", out["model"], flags=re.I)
    if re.search(r"[a-z]{3}", bare, re.I) and re.search(r"\d", bare):
        out["short"] = bare
    if p["brand_ar"] != brand:
        out["arabic brand"] = f"{p['brand_ar']} {bare}"
    ar = {v: k for k, v in reversed(AR_WORDS.items()) if v.isalpha() and len(v) > 2}
    words = [ar.get(w, w) for w in fold(bare).split()]
    if any(re.match(r"[؀-ۿ]", w) for w in words):
        out["arabic"] = " ".join(words)
    slip = _slip(out["model"])
    if slip:
        out["slip"] = slip
    return out


def _run(cmd: list[str], queries: list[str], cwd: Path, tmp: Path, name: str) -> list[list]:
    (tmp / "q.json").write_text(json.dumps(queries, ensure_ascii=False), encoding="utf-8")
    out = tmp / f"{name}.json"
    subprocess.run([*cmd, str(tmp / "q.json"), str(out)], cwd=cwd, check=True, capture_output=True, timeout=1500,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.loads(out.read_text(encoding="utf-8"))


def api_answers(queries: list[str], rows: list, products: dict[int, dict]) -> list[list[int]]:
    items = [(i, products[i]["category"], (h, k, frozenset(re.findall(r"[a-z0-9؀-ۿ]+", h)))) for i, h, k in rows if i in products]

    def rank(x):
        p = products[x[1]]
        return (x[0], -p["ranked_shops"], p["best_price"] is None, p["best_price"] or 0, p["label"], p["id"])
    return [[i for _, i in sorted(find(q, items), key=rank)] for q in queries]


def judge(queries: list[tuple[str, str, object]], answers: list[list], names: dict) -> list[dict]:
    """Problems of one set of rules. A query is (kind, text, wanted): wanted is a pattern for the first results, or the one
    product that must be among the results; names = product key -> "category|name" of what that client can show."""
    bad = []
    for (kind, text, want), got in zip(queries, answers):
        if kind == "typed":
            rx = re.compile(str(want), re.I)
            if not any(rx.search(n) for n in names.values()):
                continue
            top = [names.get(k, "") for k in got[:5]]
            if not top or sum(bool(rx.search(n)) for n in top) * 2 < len(top):
                bad.append({"kind": kind, "query": text, "wanted": want, "got": top[:3]})
        elif want in names and want not in got:
            bad.append({"kind": kind, "query": text, "wanted": names[want], "got": [names.get(k, "") for k in got[:3]]})
    return bad


def check(build: Path = BUILD, every: int = 1, clients: tuple[str, ...] = ("api", "site", "app")) -> dict:
    """Runs every search on each client's rules. `every`=n tests only each n-th product's own searches (for quick runs)."""
    summaries = json.loads((build / "api" / "summaries.json").read_text(encoding="utf-8"))["results"]
    rows = json.loads((build / "api" / "search.json").read_text(encoding="utf-8"))["items"]
    site = json.loads((build / "search-index.json").read_text(encoding="utf-8"))["items"]
    products = {p["id"]: p for p in summaries}
    by_slug = {p["slug"]: p["id"] for p in summaries}
    names = {i: f"{p['category']}|{p['label']}" for i, p in products.items()}
    real = {t for _, h, _ in rows for t in re.findall(r"[a-z]+", h)}
    queries: list[tuple[str, str, object]] = [("typed", q, rx) for q, rx in CASES]
    for p in summaries[::every]:
        for kind, text in own_searches(p).items():
            # a slip that gives another real word is another search, not a slip; a server search is at most 80 letters
            if len(text) <= 80 and not (kind == "slip" and any(w in real or any(w in r for r in real) for w in re.findall(r"[a-z]{5,}", text) if w not in fold(p["label"]))):
                queries.append((kind, text, p["id"]))
    texts = [q for _, q, _ in queries]
    out: dict = {"at": datetime.now(timezone.utc).isoformat(), "searches": len(texts), "clients": {}, "problems": []}
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        got: dict[str, list] = {}
        for c in clients:
            try:
                if c == "api":
                    got[c] = api_answers(texts, rows, products)
                elif c == "site":
                    got[c] = _run([shutil.which("node") or "node", str(ROOT / "scripts" / "search_check.js"), str(ROOT / "web" / "search.js"),
                                   str(build / "search-index.json")], texts, ROOT, tmp, c)
                else:
                    dart = shutil.which("dart")
                    dart = dart and Path(dart).parent / "cache" / "dart-sdk" / "bin" / "dart.exe"
                    if not dart or not dart.exists():
                        out["clients"][c] = "not run: dart is not installed here"
                        continue
                    got[c] = _run([str(dart), str(ROOT / "app" / "tool" / "search_check.dart"), str(build / "api" / "search.json"),
                                   str(build / "api" / "summaries.json")], texts, ROOT / "app", tmp, c)
            except Exception as e:  # noqa: BLE001  the other clients' results still count
                out["clients"][c] = f"not run: {type(e).__name__} {str(e)[:200]}"
    seen: dict[tuple, dict] = {}
    for c, answers in got.items():
        if c == "site":
            on_site = {by_slug[x["u"]]: names[by_slug[x["u"]]] for x in site if x["u"] in by_slug}
            answers = [[by_slug.get(u) for u in a] for a in answers]
        bad = judge(queries, answers, on_site if c == "site" else names)
        out["clients"][c] = len(bad)
        for b in bad:
            seen.setdefault((b["kind"], b["query"], b["wanted"]), {**b, "in": []})["in"].append(c)
    if "api" in got and "app" in got:   # the two must give the same products in the same order
        diff = [q for q, a, b in zip(texts, got["api"], got["app"]) if a != b]
        out["api_app_differ"] = len(diff)
        for q in diff[:50]:
            seen.setdefault(("differ", q, ""), {"kind": "differ", "query": q, "wanted": "the same answer in the app and the API", "got": [], "in": ["app"]})
    order = {"typed": 0, "differ": 1, "name": 2, "model": 3, "short": 4, "arabic brand": 5, "arabic": 6, "slip": 7}
    problems = sorted(seen.values(), key=lambda p: (order[p["kind"]], p["query"]))
    out["count"] = len(problems)
    out["kinds"] = {k: sum(p["kind"] == k for p in problems) for k in order}
    out["problems"] = problems[:KEEP]
    return out


def write(report: Path = REPORT, **kw) -> dict:
    r = check(**kw)
    report.parent.mkdir(parents=True, exist_ok=True)
    tmp = report.with_suffix(".tmp")
    tmp.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(report)
    return {k: r[k] for k in ("searches", "count", "clients", "kinds")}


def summary(report: Path = REPORT) -> dict | None:
    """For the admin page: when, how many searches, how many failed, and the first failing ones."""
    if not report.exists():
        return None
    r = json.loads(report.read_text(encoding="utf-8"))
    return {"at": r["at"], "searches": r["searches"], "count": r["count"], "clients": r["clients"],
            "first": [{"q": p["query"], "wanted": str(p["wanted"])[:80], "in": ", ".join(p["in"])} for p in r["problems"][:15]]}
