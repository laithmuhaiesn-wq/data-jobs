"""Monthly "visitors we sent you" report for each shop (owner's pay-per-click plan, 2026-11-17).

On the 1st of every month the nightly job writes one report per shop for the month before, from the same "Go to shop"
click counts as the private click report (Cloudflare D1; nothing personal is stored). Each report holds ONLY that
shop's own numbers: visitors sent, app or website, day by day, its most clicked products and the change from the month
before. It is saved as HTML and as a PDF (printed by Microsoft Edge) in ~/Derbani shop reports/<month>/, for the owner
to send when talking to a shop. Nothing is sent anywhere by this code.

    python -m pricecompare.cli shop-reports               # last month
    python -m pricecompare.cli shop-reports --month 2026-11   # any month (a month still running is marked so)
"""
from __future__ import annotations

import html
import re
import subprocess
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

OUT = Path.home() / "Derbani shop reports"


def month_days(month: str) -> list[date]:
    y, m = map(int, month.split("-"))
    d, out = date(y, m, 1), []
    while d.month == m:
        out.append(d)
        d += timedelta(days=1)
    return out


def previous(month: str) -> str:
    return (month_days(month)[0] - timedelta(days=1)).strftime("%Y-%m")


def file_name(shop: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", shop.lower()).strip("-") or "shop"


def shop_numbers(rows: list[dict], shop: str, month: str) -> dict:
    mine = [r for r in rows if r["shop"] == shop]
    this = [r for r in mine if r["day"].startswith(month)]
    before = sum(r["n"] for r in mine if r["day"].startswith(previous(month)))
    by_day: dict[str, int] = defaultdict(int)
    by_product: dict[int, int] = defaultdict(int)
    src = {"app": 0, "site": 0}
    for r in this:
        by_day[r["day"]] += r["n"]
        by_product[r["product"]] += r["n"]
        src[r["source"] if r["source"] in src else "site"] += r["n"]
    return {"total": sum(src.values()), "before": before, "app": src["app"], "site": src["site"], "by_day": dict(by_day),
            "top": sorted(by_product.items(), key=lambda x: (-x[1], x[0]))[:10]}


def page(shop: str, month: str, n: dict, names: dict[int, str], today: date) -> str:
    e = html.escape
    days = month_days(month)
    running = days[-1] >= today
    peak = max(n["by_day"].values(), default=0) or 1
    bars = "".join(
        f'<div class="bar" title="{d.isoformat()}: {n["by_day"].get(d.isoformat(), 0)}">'
        f'<i style="height:{round(100 * n["by_day"].get(d.isoformat(), 0) / peak)}%"></i><span>{d.day}</span></div>' for d in days)
    change = ""
    if n["before"]:
        pct = round(100 * (n["total"] - n["before"]) / n["before"])
        change = f'<p class="mute">Month before: {n["before"]} ({"+" if pct >= 0 else ""}{pct}%) · الشهر السابق: {n["before"]}</p>'
    top = "".join(f'<tr><td>{e(names.get(p, f"#{p}"))}</td><td class="num">{c}</td></tr>' for p, c in n["top"]) \
        or '<tr><td colspan="2" class="mute">—</td></tr>'
    label = days[0].strftime("%B %Y")
    note = ('<p class="warn">This month is not over yet; the numbers are up to today.</p>'
            '<p class="warn ar">الشهر لم ينتهِ بعد؛ الأرقام حتى اليوم.</p>') if running else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Kamkam · {e(shop)} · {label}</title><style>
@page{{size:A4;margin:16mm}}
body{{font-family:"Segoe UI",Tahoma,Arial,sans-serif;color:#111;margin:0 auto;max-width:760px;padding:24px}}
.stripe{{height:10px;background:#c8102e;margin:-24px -24px 20px}}
h1{{font-size:26px;margin:0}} h2{{font-size:17px;margin:26px 0 8px;border-bottom:2px solid #111;padding-bottom:4px}}
.mute{{color:#5a5a55}} .warn{{color:#9a5b00;font-weight:600}}
.big{{display:flex;gap:16px;margin-top:18px}} .big div{{flex:1;border:2px solid #111;padding:12px}}
.big b{{display:block;font-size:34px}} .big span{{color:#5a5a55;font-size:13px}}
.chart{{display:flex;align-items:flex-end;gap:2px;height:150px;border-bottom:1px solid #111}}
.bar{{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center}}
.bar i{{display:block;width:100%;background:#c8102e;min-height:1px}} .bar span{{font-size:9px;color:#5a5a55}}
table{{width:100%;border-collapse:collapse}} td{{padding:6px 4px;border-bottom:1px solid #ddd}} .num{{text-align:right;font-weight:700}}
.ar{{direction:rtl;text-align:right}}
</style></head><body><div class="stripe"></div>
<h1>Visitors Kamkam sent to {e(shop)}</h1>
<p class="ar" style="font-size:20px;margin:4px 0 0"><b>الزوار الذين أرسلهم Kamkam إلى {e(shop)}</b></p>
<p class="mute">{label} · kamkam.derbani.com · a Derbani product</p>{note}
<div class="big"><div><b>{n["total"]}</b><span>visitors sent · زائر</span></div>
<div><b>{n["site"]}</b><span>from the website · من الموقع</span></div>
<div><b>{n["app"]}</b><span>from the app · من التطبيق</span></div></div>{change}
<h2>Day by day · يوماً بيوم</h2><div class="chart">{bars}</div>
<h2>Most clicked products · أكثر المنتجات</h2><table>{top}</table>
<h2>How we count · كيف نعدّ</h2>
<p>A visitor is counted when they press “Go to shop” for one of your products on kamkam.derbani.com or in the Kamkam app and
are sent to your page (links carry <code>utm_source=kamkam</code>, so you can see them in your own analytics too).
Known bots are not counted. We store no personal data: only the day, the shop, the product and app or website.</p>
<p class="ar">يُحسب الزائر عندما يضغط «اذهب للمتجر» على أحد منتجاتكم في kamkam.derbani.com أو تطبيق Kamkam ويُنقل إلى صفحتكم. الروابط تحمل
<code>utm_source=kamkam</code> لتروها في إحصاءاتكم أيضاً. لا نعدّ الروبوتات المعروفة، ولا نخزن أي بيانات شخصية.</p>
<p class="mute">Made {today.isoformat()} · Kamkam, price comparison in Jordan · Derbani</p>
</body></html>"""


def print_pdf(src: Path, pdf: Path) -> bool:
    from .deal_cards import edge
    browser = edge()
    if not browser:
        return False
    subprocess.run([str(browser), "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", src.resolve().as_uri()],
                   capture_output=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(40):  # Edge can return before the file is written
        if pdf.exists() and pdf.stat().st_size > 2_000:
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False


def make(rows: list[dict], names: dict[int, str], month: str, today: date, out_root: Path = OUT, pdf: bool = True) -> dict:
    folder = out_root / month
    folder.mkdir(parents=True, exist_ok=True)
    shops = sorted({r["shop"] for r in rows if r["day"].startswith(month)})
    pdfs = 0
    for shop in shops:
        f = folder / f"{file_name(shop)}.html"
        f.write_text(page(shop, month, shop_numbers(rows, shop, month), names, today), encoding="utf-8")
        if pdf and print_pdf(f, f.with_suffix(".pdf")):
            pdfs += 1
    return {"month": month, "shops": len(shops), "pdfs": pdfs, "folder": str(folder)}


def main(month: str | None = None) -> None:
    import os

    from .clicks import fetch_rows, product_names
    token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not token or not account:
        raise SystemExit("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are needed")
    today = date.today()
    month = month or previous(today.strftime("%Y-%m"))
    rows = fetch_rows(token, account)
    wanted = [r for r in rows if r["day"].startswith(month)]
    names = old_names()
    names.update(product_names(sorted({r["product"] for r in wanted})))
    print("shop reports:", make(rows, names, month, today))


def old_names() -> dict[int, str]:
    """Names of products from the old site (clicks on old links still count; the live API may not know them now)."""
    import json
    f = Path.home() / ".derbani" / "old_products.json"
    try:
        return {v["id"]: " ".join(v["label"].split()) for v in json.loads(f.read_text(encoding="utf-8"))["results"] if v.get("label")}
    except (OSError, ValueError, KeyError):
        return {}
