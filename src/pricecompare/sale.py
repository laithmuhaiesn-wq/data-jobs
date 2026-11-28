"""Sale mode found by itself (owner 2026-11-28: "handled now for all major sales" and for the ones nobody announced).

The worker's calendar (worker/api.js saleMode) knows the yearly sale seasons. This catches the rest: every cloud run
counts the compared listings whose price went down in the last 24 hours. When that is far above the usual day (3x the
middle day of the last 14, and at least MIN_DROPS), the shops are running a sale: sale mode goes on and stays on for
KEEP days after the last such day. The answer is published as api/sale.json; the worker reads it at half past.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY = Path.home() / ".derbani" / "drops_by_day.json"   # {day: the most drops seen in 24 h that day}
MIN_DROPS = 60       # a normal day has about 30-70 drops (2026-11); a sale moves hundreds
TIMES = 3
KEEP = timedelta(days=3)


def decide(history: dict[str, int], today: str) -> dict:
    """{"auto": bool, "why": str, "until": day or None} from the daily drops (pure, for tests)."""
    days = sorted(history)
    past = [history[d] for d in days if d < today][-14:]
    usual = sorted(past)[len(past) // 2] if len(past) >= 7 else None
    limit = max(MIN_DROPS, TIMES * usual) if usual is not None else None
    sale_days = [d for d in days if limit is not None and d <= today and history[d] >= limit]
    if not sale_days:
        return {"auto": False, "why": f"usual day {usual} drops" if usual is not None else "learning the usual day (7 days)",
                "until": None}
    until = (datetime.fromisoformat(sale_days[-1]) + KEEP).date().isoformat()
    on = today <= until
    return {"auto": on, "why": f"{history[sale_days[-1]]} price drops on {sale_days[-1]} (usual day {usual})", "until": until}


def write(s, build: Path, now: datetime | None = None, history_path: Path = HISTORY) -> dict:
    from .admin_extra import price_moves
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    history[today] = max(history.get(today, 0), price_moves(s, now)["down"])
    history = {d: n for d, n in history.items() if d >= (now - timedelta(days=60)).date().isoformat()}
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history), encoding="utf-8")
    out = {**decide(history, today), "drops_24h": history[today], "checked": now.isoformat(timespec="seconds")}
    (build / "api").mkdir(parents=True, exist_ok=True)
    (build / "api" / "sale.json").write_text(json.dumps(out), encoding="utf-8")
    return out
