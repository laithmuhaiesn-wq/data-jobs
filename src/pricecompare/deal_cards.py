"""Daily deal cards for Instagram, Facebook and WhatsApp (competitor study idea, 2026-11-17).

Every night the PC picks the day's biggest real price drops (and, when there are too few, the biggest gaps between
shops), draws one square 1080x1080 picture per product in Arabic and in English, and writes a ready caption with the
product's kamkam.derbani.com link. The pictures are drawn as small HTML pages and photographed by Microsoft Edge (already on
every Windows PC; it shapes Arabic text properly), so no extra software is needed. Nothing is posted anywhere: the owner
picks what to post. Only our own recorded prices are used.

    python -m pricecompare.cli deal-cards            ->  ~/Derbani deal cards/<date>/
"""
from __future__ import annotations

import html
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

EDGE = [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe"]
OUT = Path.home() / "Derbani deal cards"
COUNT = 6
MIN_SHOPS = 3  # a "deal" at the only shop that sells it says little; three shops make the comparison real
KEEP_DAYS = 14

TEXT = {
    "ar": {"dir": "rtl", "drop": "نزل السعر ‎{x}%‎", "gap": "وفّر {x} د.أ بين المتاجر", "was": "كان {p} د.أ", "now": "{p} د.أ",
           "at": "عند {shop}", "shops": "قارنّا {n} متاجر", "foot": "قارن الأسعار في الأردن قبل أن تشتري",
           "cap_drop": "نزل سعر {name} إلى {p} دينار عند {shop} (كان {was}).",
           "cap_gap": "{name}: أرخص سعر {p} دينار عند {shop}، والفرق بين المتاجر {save} دينار.",
           "cap_end": "قارن كل المتاجر: {link}"},
    "en": {"dir": "ltr", "drop": "{x}% cheaper", "gap": "Save {x} JOD between shops", "was": "was {p} JOD", "now": "{p} JOD",
           "at": "at {shop}", "shops": "{n} shops compared", "foot": "Compare prices in Jordan before you buy",
           "cap_drop": "{name} is down to {p} JOD at {shop} (was {was}).",
           "cap_gap": "{name}: lowest price {p} JOD at {shop}; shops differ by {save} JOD.",
           "cap_end": "Compare every shop: {link}"},
}


def money(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def pick(data: list[dict], count: int = COUNT) -> list[tuple[str, dict]]:
    """The day's best stories: real drops first (one per model), then the biggest gaps. [(kind, product)]"""
    from .website import drops_and_gaps
    drops, gaps = drops_and_gaps(data)
    out, models = [], set()
    for kind, items in (("drop", drops), ("gap", gaps)):
        for v in items:
            if len(out) >= count:
                return out
            if v["model"] in models or not v.get("best_store") or v["ranked_shops"] < MIN_SHOPS:
                continue
            models.add(v["model"])
            out.append((kind, v))
    return out


def card_html(kind: str, v: dict, lang: str, picture: str | None) -> str:
    t, e = TEXT[lang], html.escape
    badge = (t["drop"].format(x=round(v["drop_pct"])) if kind == "drop" else t["gap"].format(x=money(v["save"])))
    was = f'<div class="was">{e(t["was"].format(p=money(v["was"])))}</div>' if kind == "drop" and v.get("was") else ""
    shot = f'<img src="{e(picture)}" alt="">' if picture else ""
    return f"""<!doctype html><html lang="{lang}" dir="{t['dir']}"><head><meta charset="utf-8"><style>
html,body{{margin:0;width:1080px;height:1080px;overflow:hidden;background:#f7f7f5;font-family:"Segoe UI",Tahoma,Arial,sans-serif;color:#111}}
.stripe{{height:22px;background:#c8102e}}
.wrap{{padding:56px 72px;display:flex;flex-direction:column;height:calc(1080px - 22px - 112px)}}
.brand{{font-size:46px;font-weight:800;letter-spacing:.5px}} .brand span{{color:#c8102e}}
.badge{{align-self:flex-start;margin-top:28px;background:#c8102e;color:#fff;font-size:44px;font-weight:800;padding:10px 26px}}
.pic{{flex:1;display:flex;align-items:center;justify-content:center;min-height:0;margin:24px 0;background:#fff;border:3px solid #111}}
.pic img{{max-width:86%;max-height:86%;object-fit:contain}}
.name{{font-size:52px;font-weight:800;line-height:1.15}}
.row{{display:flex;align-items:baseline;gap:28px;margin-top:14px}}
.now{{font-size:84px;font-weight:900;color:#007a3d}} .was{{font-size:40px;color:#5a5a55;text-decoration:line-through}}
.at{{font-size:36px;color:#333;margin-top:6px}}
.foot{{font-size:30px;color:#5a5a55;margin-top:18px}}
</style></head><body><div class="stripe"></div><div class="wrap">
<div class="brand">Kamkam<span> · kamkam.derbani.com</span></div>
<div class="badge"><bdi>{e(badge)}</bdi></div>
<div class="pic">{shot}</div>
<div class="name"><bdi>{e(v['label'])}</bdi></div>
<div class="row"><div class="now">{e(t['now'].format(p=money(v['best_price'])))}</div>{was}</div>
<div class="at">{e(t['at'].format(shop=v['best_store']))} · {e(t['shops'].format(n=v['ranked_shops']))}</div>
<div class="foot">{e(t['foot'])}</div>
</div></body></html>"""


def caption(kind: str, v: dict, lang: str, link: str) -> str:
    t = TEXT[lang]
    if kind == "drop":
        line = t["cap_drop"].format(name=" ".join(v["label"].split()), p=money(v["best_price"]), shop=v["best_store"], was=money(v["was"]))
    else:
        line = t["cap_gap"].format(name=" ".join(v["label"].split()), p=money(v["best_price"]), shop=v["best_store"], save=money(v["save"]))
    return line + " " + t["cap_end"].format(link=link)


def edge() -> Path | None:
    return next((p for p in EDGE if p.exists()), None)


def render(page: Path, png: Path, browser: Path) -> bool:
    """Photograph one card page with Edge in the background (no window)."""
    subprocess.run([str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                        "--force-device-scale-factor=1", "--window-size=1080,1080", "--virtual-time-budget=8000",
                        f"--screenshot={png}", page.resolve().as_uri()],
                       capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    # Edge's first process can hand the work to a running one and return early: wait for the picture itself
    for _ in range(40):
        if png.exists() and png.stat().st_size > 10_000:
            time.sleep(0.5)  # let the file finish writing
            return True
        time.sleep(0.5)
    return False


def make(data: list[dict], now: datetime, out_root: Path = OUT) -> dict:
    from .website import SITE, picture, url
    stories = pick(data)
    day = out_root / now.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    browser, made, lines = edge(), 0, []
    for n, (kind, v) in enumerate(stories, 1):
        for lang in ("ar", "en"):
            page = day / f"{n}-{lang}.html"
            page.write_text(card_html(kind, v, lang, picture(v)), encoding="utf-8")
            link = f"{SITE}{url(v, lang)}?utm_source=social"
            lines.append(f"[{n}-{lang}.png]\n{caption(kind, v, lang, link)}\n")
            if browser and render(page, day / f"{n}-{lang}.png", browser):
                made += 1
                page.unlink()
    (day / "captions.txt").write_text("\n".join(lines), encoding="utf-8")
    for old in out_root.iterdir():  # older days go after two weeks
        try:
            if old.is_dir() and (now - datetime.strptime(old.name, "%Y-%m-%d").replace(tzinfo=now.tzinfo)).days > KEEP_DAYS:
                for f in old.iterdir():
                    f.unlink()
                old.rmdir()
        except ValueError:
            continue
    return {"stories": len(stories), "pictures": made, "folder": str(day), "edge": bool(browser)}
