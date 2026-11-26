"""Pieces of the 2026-11 Kamkam design shared by the website pages: category icons, the price chart and the
"similar price" alternatives. The app has the same alternatives rule (app/lib/alternatives.dart); keep them alike."""
from __future__ import annotations

from datetime import date

# 24-grid line icons, drawn with the text colour (CSS: svg.i). The app draws its own set (app/lib/icons.dart).
ICONS = {
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
    "tablet": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M11 18h2"/>',
    "laptop": '<rect x="5" y="5" width="14" height="10" rx="1.5"/><path d="M2.5 19h19l-2-4h-15z"/>',
    "tv": '<rect x="2.5" y="4" width="19" height="13" rx="1.5"/><path d="M8 21h8M12 17v4"/>',
    "watch": '<rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 6l1-3.5h4L15 6M9 18l1 3.5h4l1-3.5M12 9.5V12l1.5 1.5"/>',
    "audio": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4.5" height="6" rx="1.5"/>'
             '<rect x="16.5" y="14" width="4.5" height="6" rx="1.5"/>',
    "speaker": '<rect x="6" y="2.5" width="12" height="19" rx="2"/><circle cx="12" cy="14.5" r="3.5"/><path d="M12 7h.01"/>',
    "console": '<path d="M7 7h10a5 5 0 0 1 4.8 6.4l-1 3.4a2.5 2.5 0 0 1-4.3.9L14.5 15h-5l-2 2.7a2.5 2.5 0 0 1-4.3-.9l-1-3.4A5 5 0 0 1 7 7z"/>'
               '<path d="M7.5 10v3M6 11.5h3M15.5 11h.01M17.5 12.5h.01"/>',
    "monitor": '<rect x="2.5" y="3.5" width="19" height="13" rx="1.5"/><path d="M12 16.5V20M8 20.5h8"/>',
    "printer": '<path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="1.5"/><path d="M7 14h10v7H7z"/>',
    "desktop": '<rect x="7" y="2.5" width="10" height="19" rx="1.5"/><path d="M10 6.5h4M10 9.5h4M12 17h.01"/>',
    "router": '<rect x="3" y="13" width="18" height="7" rx="1.5"/><path d="M7 16.5h.01M10 16.5h.01M17 13V9"/>'
              '<path d="M14.2 7.2a4 4 0 0 1 5.6 0M12.4 5a6.8 6.8 0 0 1 9.2 0"/>',
    "powerbank": '<rect x="6" y="3" width="12" height="18" rx="2"/><path d="M12.5 7.5L10 12h4l-2.5 4.5"/>',
    "storage": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 14h.01M10 14h7"/>',
    "camera": '<path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h3L9 4.5h6L16.5 7h3A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>'
              '<circle cx="12" cy="13" r="3.5"/>',
    "projector": '<rect x="2.5" y="8" width="19" height="9" rx="2"/><circle cx="15.5" cy="12.5" r="2.5"/><path d="M6 12.5h3M5 17v2M19 17v2"/>',
    "smarthome": '<path d="M3.5 11L12 4l8.5 7M5.5 9.5V20h13V9.5"/><path d="M10 16a3 3 0 0 1 4 0M8.5 13.5a5 5 0 0 1 7 0"/>',
    "peripheral": '<rect x="2.5" y="10" width="13" height="8" rx="1.5"/><path d="M5.5 13h.01M8.5 13h.01M11.5 13h.01M6 15.5h6"/>'
                  '<rect x="17.5" y="9" width="4" height="7" rx="2"/><path d="M19.5 9V6.5a2 2 0 0 0-2-2H12"/>',
    "tabletacc": '<path d="M16.5 3.5l4 4L9 19l-5 1 1-5z"/><path d="M14 6l4 4"/>',
    "pcpart": '<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5"/>'
              '<path d="M9 2.5V6M15 2.5V6M9 18v3.5M15 18v3.5M2.5 9H6M2.5 15H6M18 9h3.5M18 15h3.5"/>',
    "ram": '<rect x="2.5" y="7" width="19" height="9" rx="1"/><path d="M6 10v3M9.5 10v3M14.5 10v3M18 10v3M2.5 19h19M5 16v3M19 16v3"/>',
    "tag": '<path d="M3 12V4.5A1.5 1.5 0 0 1 4.5 3H12l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "share": '<circle cx="18" cy="5.5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="18.5" r="2.5"/>'
             '<path d="M8.2 10.8l7.6-4.1M8.2 13.2l7.6 4.1"/>',
    "theme": '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17A8.5 8.5 0 0 0 12 3.5z" class="fill"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "heart": '<path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.3 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10z"/>',
    "grid": '<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/>'
            '<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>',
    "down": '<path d="M12 5v14M6 13l6 6 6-6"/>',
}


def icon(name: str, size: int = 24) -> str:
    return (f'<svg class="i" viewBox="0 0 24 24" width="{size}" height="{size}" aria-hidden="true" focusable="false">'
            f'{ICONS.get(name, ICONS["tag"])}</svg>')


# ---- similar price ----
SIMILAR_RANGE = 0.12   # within 12 % of this product's lowest price
SIMILAR_MAX = 6


def alternatives(v: dict, data: list[dict], n: int = SIMILAR_MAX) -> list[dict]:
    """Other products of the same kind whose lowest price is close to this one's: one size per model, the ones sold
    at most shops first, then the closest in price. Nothing for a product with no price now, and no grey-market ones."""
    p = v.get("best_price")
    if p is None:
        return []
    pool = [x for x in data if x["category"] == v["category"] and x["id"] != v["id"] and x.get("best_price") is not None
            and not x.get("gray") and x["model"] != v["model"] and abs(x["best_price"] - p) <= p * SIMILAR_RANGE]
    one_each: dict[str, dict] = {}
    for x in sorted(pool, key=lambda x: (-x.get("ranked_shops", 0), abs(x["best_price"] - p), x["id"])):
        one_each.setdefault(x["model"], x)
    return list(one_each.values())[:n]


# ---- price chart ----
def _money(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".")


def price_chart(history: list[dict], today: date, title: str, jod: str) -> str:
    """The lowest price over time as a step line (it holds until the day it moves), drawn as plain SVG on the page:
    no script, works with the page's strict rules. `history` is oldest first, [{"d": "2026-11-07", "p": 1299.0}]."""
    try:
        pts = [(date.fromisoformat(str(h["d"])[:10]), float(h["p"])) for h in history]
    except (KeyError, TypeError, ValueError):
        return ""
    if len(pts) < 2:
        return ""
    start, end = pts[0][0], max(today, pts[-1][0])
    span = max((end - start).days, 1)
    lo, hi = min(p for _, p in pts), max(p for _, p in pts)
    pad = (hi - lo) * 0.18 or max(hi * 0.03, 1.0)
    w, h, left, right, top, bottom = 640, 200, 10, 10, 26, 30

    def x(d: date) -> float:
        return left + (w - left - right) * (d - start).days / span

    def y(p: float) -> float:
        return top + (h - top - bottom) * (1 - (p - (lo - pad)) / ((hi + pad) - (lo - pad)))

    line = f"M{x(pts[0][0]):.1f},{y(pts[0][1]):.1f}" + "".join(f"H{x(d):.1f}V{y(p):.1f}" for d, p in pts[1:]) + f"H{x(end):.1f}"
    area = line + f"V{h - bottom}H{left}Z"
    low_d = next(d for d, p in pts if p == lo)
    hi_d = next(d for d, p in pts if p == hi)
    lx, hx = x(low_d), x(hi_d)
    anchor = lambda px: "start" if px < w * 0.2 else ("end" if px > w * 0.8 else "middle")
    return (f'<figure class="chart" dir="ltr"><svg viewBox="0 0 {w} {h}" role="img" aria-label="{title}">'
            f'<line class="base" x1="{left}" x2="{w - right}" y1="{h - bottom}" y2="{h - bottom}"/>'
            f'<path class="area" d="{area}"/><path class="line" d="{line}"/>'
            f'<circle class="lo" cx="{lx:.1f}" cy="{y(lo):.1f}" r="5"/>'
            f'<text class="lbl good" x="{lx:.1f}" y="{min(y(lo) + 20, h - bottom - 4):.1f}" text-anchor="{anchor(lx)}">{_money(lo)}</text>'
            + (f'<text class="lbl" x="{hx:.1f}" y="{max(y(hi) - 9, 14):.1f}" text-anchor="{anchor(hx)}">{_money(hi)}</text>' if hi != lo else "")
            + f'<text class="day" x="{left}" y="{h - 8}" text-anchor="start">{start.strftime("%d/%m")}</text>'
            f'<text class="day" x="{w - right}" y="{h - 8}" text-anchor="end">{end.strftime("%d/%m")}</text>'
            '</svg></figure>')
