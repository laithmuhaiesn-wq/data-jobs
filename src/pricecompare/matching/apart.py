"""Products whose shops' prices are far apart (report.accuracy_check), each one looked at once (owner 2026-11-25).

The admin page lists them every hour; most are real differences between shops, so the same ones came back every day.
`python -m pricecompare.cli apart` writes the ones not looked at yet to ~/.derbani/apart_products.json; the daily doctor
reads each one (titles and the shops' own pages), splits two joined products in the reader, and runs `apart-seen`.
A product comes back as soon as its listings change: another shop or title, or a price that moved more than 10%.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

REPORT = Path.home() / ".derbani" / "apart_products.json"
SEEN = Path.home() / ".derbani" / "apart_seen.json"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _state(offers: list[tuple]) -> list[list]:
    """[shop, title, price] of every listing: what "the same as last time" is judged by."""
    return sorted([shop, title, price] for shop, price, title, _ in offers)


def _same(a: list[list] | None, b: list[list]) -> bool:
    return bool(a) and len(a) == len(b) and all(
        x[:2] == y[:2] and math.isclose(x[2], y[2], rel_tol=0.10) for x, y in zip(a, b))


def find(s: Session, seen: dict | None = None, now: datetime | None = None) -> list[dict]:
    """Far-apart products not looked at yet, hidden ones first, then the widest gap."""
    from ..report import accuracy_check
    seen = _load(SEEN) if seen is None else seen
    rows = []
    for vid, a in accuracy_check(s, now).items():
        state = _state(a["offers"])
        if not _same((seen.get(str(vid)) or {}).get("state"), state):
            rows.append({"product": vid, "ratio": a["ratio"], "hidden": a["hidden"], "state": state,
                         "offers": [{"shop": sh, "price": p, "title": t, "url": u} for sh, p, t, u in a["offers"]]})
    return sorted(rows, key=lambda r: (not r["hidden"], -r["ratio"]))


def write(s: Session, path: Path = REPORT, seen: dict | None = None) -> int:
    rows = find(s, seen)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "products": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows)


def mark_seen(report: Path = REPORT, seen_path: Path = SEEN) -> int:
    """Everything in the last report has been looked at."""
    seen, rows = _load(seen_path), _load(report).get("products", [])
    day = datetime.now(timezone.utc).date().isoformat()
    seen.update({str(r["product"]): {"day": day, "state": r["state"]} for r in rows})
    tmp = seen_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    tmp.replace(seen_path)
    return len(rows)
