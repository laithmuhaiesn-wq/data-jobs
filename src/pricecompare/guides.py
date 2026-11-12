"""Buying guides (plan 2b.4), built from our own price data every hour, for EVERY category automatically.

Honest by design: a guide never claims one product is "better" than another (we do not judge quality and never invent
specifications). Each guide answers a price question with today's facts: what fits a budget, what is at its lowest
price ever, where comparing saves the most, what most shops sell. Order inside a guide is by how many shops sell it
(more shops = easier to compare and usually more popular), then by price. Non-official versions are left out.

A new category gets guides with no extra work: budgets come from BUDGETS when set, otherwise from its own prices.
"""
from __future__ import annotations

# Budget lines per category (JOD). A category without an entry gets lines from its own prices (see _auto_budgets).
BUDGETS: dict[str, list[int]] = {
    "phone": [100, 150, 200, 300, 500, 800],
    "tablet": [150, 250, 400, 700],
}
MAX_ITEMS = 15
MIN_ITEMS = 3

TEXT = {
    "under": ("{cat} أقل من {b} دينار في الأردن", "{cat} under {b} JOD in Jordan"),
    "under_intro": ("كل {low} سعره الآن {b} د.أ أو أقل في متجر واحد على الأقل، مرتبة حسب عدد المتاجر التي تبيعه ثم السعر. "
                    "الترتيب لا يقيّم الجودة: قارن المواصفات بنفسك قبل الشراء.",
                    "Every {low} that costs {b} JOD or less today in at least one shop, ordered by how many shops sell it, then by "
                    "price. The order does not judge quality: compare the specifications yourself before you buy."),
    "lowest": ("{cat} بأقل سعر سجلناه الآن", "{cat} at the lowest price we have recorded"),
    "lowest_intro": ("هذه {low} سعرها اليوم هو الأقل منذ بدأنا متابعتها، وتغيّر سعرها مرة على الأقل. الأكبر نزولاً أولاً.",
                     "These {low} cost the least today since we started tracking them, and their price has moved at least once. "
                     "Biggest fall from the highest price first."),
    "gaps": ("{cat}: أين توفر المقارنة أكثر", "{cat}: where comparing saves the most"),
    "gaps_intro": ("الفرق بين أرخص وأغلى متجر لنفس {one} اليوم. الفرق الأكبر أولاً.",
                   "The gap between the cheapest and the dearest shop for the same {one_low} today. Biggest gap first."),
    "popular": ("أكثر {cat} توفراً في متاجر الأردن", "{cat} sold in the most shops in Jordan"),
    "popular_intro": ("{cat} التي تبيعها 3 متاجر أو أكثر، فتسهل مقارنتها. الأكثر متاجر أولاً ثم الأرخص.",
                      "{cat} sold by 3 or more shops, so they are easy to compare. Most shops first, then the cheapest."),
    "note_lowest": ("أقل سعر سجلناه (كان {h} د.أ)", "lowest we recorded (was {h} JOD)"),
    "note_save": ("وفّر {x} د.أ بين المتاجر", "save {x} JOD between shops"),
    "note_shops": ("{n} متاجر", "{n} shops"),
}


def _money(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def _auto_budgets(prices: list[float]) -> list[int]:
    """Round budget lines at the quarter points of a category's own prices (a new category needs no setup)."""
    if len(prices) < 8:
        return []
    p = sorted(prices)
    step = 50 if p[len(p) // 2] < 1000 else 100
    lines = {int(-(-p[int(len(p) * q)] // step) * step) for q in (0.25, 0.5, 0.75)}
    return sorted(lines)


def _rank(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda v: (-v["ranked_shops"], v["best_price"], v["label"]))


def build_guides(data: list[dict], categories: dict[str, tuple]) -> list[dict]:
    """categories: {key: (path, name_ar, name_en, one_en, bare_ar)} as on the website. Returns guides, each with
    id, category, kind, title/intro in both languages and items [(product, note_ar, note_en)]."""
    out = []
    for cat, names in categories.items():
        items = [v for v in data if v["category"] == cat and not v["gray"] and v.get("best_price") is not None]
        if not items:
            continue
        path, name_ar, name_en, one_en = names[0], names[1], names[2], names[3]
        words = {"ar": dict(cat=name_ar, low=name_ar, one=names[4] if len(names) > 4 else name_ar),
                 "en": dict(cat=name_en, low=name_en.lower(), one_low=one_en.lower())}

        def guide(kind: str, gid: str, chosen: list[tuple[dict, tuple[str, str]]], **extra) -> None:
            if len(chosen) < MIN_ITEMS:
                return
            out.append({
                "id": gid, "category": cat, "kind": kind,
                "title_ar": TEXT[kind][0].format(**words["ar"], **extra), "title_en": TEXT[kind][1].format(**words["en"], **extra),
                "intro_ar": TEXT[kind + "_intro"][0].format(**words["ar"], **extra),
                "intro_en": TEXT[kind + "_intro"][1].format(**words["en"], **extra),
                "items": [(v, note[0], note[1]) for v, note in chosen[:MAX_ITEMS]],
            })

        shops_note = lambda v: (TEXT["note_shops"][0].format(n=v["ranked_shops"]), TEXT["note_shops"][1].format(n=v["ranked_shops"]))
        # 1. budgets: one guide per budget line that changes the list
        last: set[int] = set()
        for b in BUDGETS.get(cat) or _auto_budgets([v["best_price"] for v in items]):
            fit = [v for v in items if v["best_price"] <= b]
            ids = {v["id"] for v in fit}
            if len(fit) >= MIN_ITEMS and ids != last:
                guide("under", f"{path}-under-{b}", [(v, shops_note(v)) for v in _rank(fit)], b=_money(b))
                last = ids
        # 2. at the lowest price ever (and the price has moved, so the record means something)
        low = [v for v in items if v.get("verdict") == "lowest" and v.get("record_high") and v["record_high"] > v["best_price"]]
        low.sort(key=lambda v: (-(v["record_high"] - v["best_price"]), v["label"]))
        guide("lowest", f"{path}-lowest-price", [(v, (TEXT["note_lowest"][0].format(h=_money(v["record_high"])),
                                                      TEXT["note_lowest"][1].format(h=_money(v["record_high"])))) for v in low])
        # 3. biggest gaps between shops
        gaps = sorted((v for v in items if v["ranked_shops"] >= 2 and v["save"] >= 5), key=lambda v: (-v["save"], v["label"]))
        guide("gaps", f"{path}-compare-saves", [(v, (TEXT["note_save"][0].format(x=_money(v["save"])),
                                                     TEXT["note_save"][1].format(x=_money(v["save"])))) for v in gaps])
        # 4. sold in the most shops
        guide("popular", f"{path}-most-shops", [(v, shops_note(v)) for v in _rank([v for v in items if v["ranked_shops"] >= 3])])
    return out
