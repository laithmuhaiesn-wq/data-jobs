"""More for the admin page (owner 2026-11-23: "more information that is important"), sent with the hourly health numbers:
system status, shop problems and the daily doctor's report, which shop is cheapest most often, and today's price moves.
Each part is filled on its own: one that fails is left out and the rest still goes to the page."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db.models import Offer, PhoneModel, PhoneVariant, PriceObservation, Store

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
JOBS = ("hourly", "nightly", "electronics", "slow", "fast", "watch")
DONE = re.compile(r"^(\d\d:\d\d:\d\d) done in (\d+) s; failed: (.*)$")

STEP = re.compile(r"^(\d\d:\d\d:\d\d) == (.+)$")


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _sending(lines: list[str]) -> tuple[str, int, str] | None:
    """The run that is sending these numbers right now (push-health is one of its last steps, before its "done" line):
    without this the page always showed the run before it, "7 h ago" after the PC had been off (2026-11-25)."""
    start = max((i for i, x in enumerate(lines) if DONE.match(x)), default=-1) + 1
    steps = [(m.group(1), m.group(2)) for x in lines[start:] if (m := STEP.match(x))]
    if not steps or not steps[-1][1].startswith("push-health"):
        return None
    failed, label = [], ""
    for x in lines[start:]:
        if m := STEP.match(x):
            label = m.group(2)
        elif re.match(r"^\d\d:\d\d:\d\d FAILED", x):
            failed.append(label)
    secs = [sum(int(p) * k for p, k in zip(t.split(":"), (3600, 60, 1))) for t in (steps[0][0], steps[-1][0])]
    return steps[-1][0], (secs[1] - secs[0]) % 86400, ", ".join(failed)


HOME = Path.home() / ".derbani"
RUNS = HOME / "runs.json"            # the cloud runs, newest last (written at the end of each run, saved with the jobs' files)
NL = chr(10)
DOCTOR = HOME / "doctor_report.md"   # the doctor's last report, put in R2 by scripts/doctor_db.py finish


def _check(url: str) -> bool:
    import httpx
    try:
        return httpx.get(url, timeout=15).status_code == 200
    except Exception:
        return False


def move_signs(runs: list[dict], now: datetime) -> list[str]:
    """When GitHub is no longer enough and the jobs should move to a server (owner 2026-11-28: "how will we know?").
    Each sign is measured over the last 24 hours of runs (runs.json); none = GitHub is fine."""
    day = [r for r in runs if datetime.fromisoformat(r["at"]) >= now - timedelta(hours=24)]
    signs = []
    if len(runs) >= 24 and len(day) < 18:
        signs.append(f"only {len(day)} runs in 24 hours (24 expected): GitHub starts them late or skips them")
    if len(day) >= 6:
        mins = sorted(r["secs"] for r in day)[len(day) // 2] / 60
        if mins > 40:
            signs.append(f"a run takes {mins:.0f} min (half of them longer): close to the hour, runs start to queue")
        bad = sum(bool(r.get("failed")) for r in day)
        if bad > len(day) // 3:
            signs.append(f"{bad} of {len(day)} runs had a failed step")
    return signs


def cloud_status(logs: Path = LOGS, runs: Path = RUNS, now: datetime | None = None, check=_check) -> dict:
    """Since the move off the PC (2026-11-28): the run sending this, the last runs before it (each with the jobs it did,
    how long, what failed) and whether api.derbani.com (the Cloudflare worker) answers. Times carry their zone."""
    import json
    now = now or datetime.now(timezone.utc)
    try:
        past = json.loads(runs.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        past = []
    out = {"cloud": True, "checked": now.isoformat(timespec="seconds"), "runs": past[-24:][::-1],
           "api_public": check("https://api.derbani.com/health")}
    out["move"] = move_signs(past, now)
    try:   # what this run found from the day's price drops (sale.py); the calendar seasons are in worker/api.js
        out["sale"] = json.loads((ROOT / "web_build" / "api" / "sale.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    files = sorted(logs.glob("jobs-cloud-*.log"))
    if files:
        lines = files[-1].read_text(encoding="utf-8", errors="replace").splitlines()
        sending = _sending(lines)
        parts = [x[14:].strip() for x in lines if x[9:].startswith("==== ")]
        if sending:
            day = files[-1].stem.rsplit("-", 3)[-3:]
            at = datetime.fromisoformat(f"{'-'.join(day)}T{sending[0]}").replace(tzinfo=timezone.utc)
            out["now"] = {"at": at.isoformat(), "secs": sending[1], "failed": sending[2], "parts": parts}
    return out


def system_status(logs: Path = LOGS, now: datetime | None = None, check=None) -> dict:
    """The last finished run of each job (from its log: when, how long, which steps failed) and whether the API answers
    on this PC and from the internet."""
    now = now or datetime.now()
    jobs = {}
    for name in JOBS:
        files = sorted(logs.glob(f"jobs-{name}-*.log"))[-2:]           # today's, or yesterday's after midnight
        for f in reversed(files):
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            m = next((DONE.match(x) for x in reversed(lines) if DONE.match(x)), None)
            now_run = _sending(lines)
            if now_run:
                jobs[name] = {"at": f"{'-'.join(f.stem.rsplit('-', 3)[-3:])}T{now_run[0]}", "secs": now_run[1], "failed": now_run[2]}
                break
            if m:
                day = f.stem.rsplit("-", 3)[-3:]
                jobs[name] = {"at": f"{'-'.join(day)}T{m.group(1)}", "secs": int(m.group(2)),
                              "failed": "" if m.group(3).strip() == "nothing" else m.group(3).strip()}
                break
    out = {"jobs": jobs, "checked": now.isoformat(timespec="seconds")}
    if check is None:
        import httpx

        def check(url):
            try:
                return httpx.get(url, timeout=15).status_code == 200
            except Exception:
                return False
    out["api_local"] = check("http://127.0.0.1:8787/health")
    out["api_public"] = check("https://api.derbani.com/health")
    return out


def doctor_report(logs: Path = LOGS, sent: Path = DOCTOR) -> dict | None:
    """The daily repair session's latest report (logs/doctor-YYYY-MM-DD.md on the PC; in the cloud the copy the doctor
    put in R2, its first line "day: YYYY-MM-DD"), shortened."""
    files = sorted(logs.glob("doctor-*.md"))
    if files:
        text = files[-1].read_text(encoding="utf-8", errors="replace")
        return {"day": files[-1].stem.replace("doctor-", ""), "text": text[:3000]}
    if sent.exists():
        first, _, text = sent.read_text(encoding="utf-8", errors="replace").partition(NL)
        return {"day": first.removeprefix("day:").strip(), "text": text[:3000]}
    return None


def _live(s: Session, now: datetime) -> list[tuple[Offer, str]]:
    """Listings a visitor compares: matched, in stock, cash, read in the last 48 h; with their product's family."""
    family = dict(s.execute(select(PhoneVariant.id, PhoneModel.family).join(PhoneModel, PhoneVariant.model_id == PhoneModel.id)).all())
    rows = s.scalars(select(Offer).where(Offer.match_status == "matched", Offer.in_stock.is_(True), Offer.price_type == "cash"))
    return [(o, family.get(o.variant_id, "")) for o in rows if _aware(o.last_checked) >= now - timedelta(hours=48) and float(o.price_jod) > 0]


def cheapest_shops(s: Session, now: datetime | None = None) -> list[dict]:
    """Per shop: on how many products it has the lowest price (ties count for each), out of how many it sells, by kind."""
    from .matching.parse import category_of
    now = now or datetime.now(timezone.utc)
    names = {st.id: st.name for st in s.scalars(select(Store))}
    by_variant: dict[int, list[Offer]] = {}
    kind: dict[int, str] = {}
    for o, fam in _live(s, now):
        by_variant.setdefault(o.variant_id, []).append(o)
        kind[o.variant_id] = category_of(fam) if fam else "phone"
    stats: dict[int, dict] = {}
    for vid, offers in by_variant.items():
        shops = {o.store_id for o in offers}
        if len(shops) < 2:
            continue                                   # one shop only: nothing to win
        low = min(float(o.price_jod) for o in offers)
        for sid in shops:
            st = stats.setdefault(sid, {"shop": names.get(sid, "?"), "sells": 0, "cheapest": 0, "kinds": {}})
            st["sells"] += 1
            if any(o.store_id == sid and float(o.price_jod) == low for o in offers):
                st["cheapest"] += 1
                st["kinds"][kind[vid]] = st["kinds"].get(kind[vid], 0) + 1
    out = sorted(stats.values(), key=lambda x: (-x["cheapest"], x["shop"]))
    for x in out:
        x["pct"] = round(100 * x["cheapest"] / x["sells"]) if x["sells"] else 0
    return out


def price_moves(s: Session, now: datetime | None = None, top: int = 15) -> dict:
    """Price changes in the last 24 hours on compared listings: how many went down or up, and the biggest drops."""
    from .health import _shown_name
    from .db.models import Brand
    now = now or datetime.now(timezone.utc)
    live = {o.id: (o, fam) for o, fam in _live(s, now)}
    since = now - timedelta(hours=24)
    changed = [oid for oid, (o, _) in live.items() if _aware(o.last_price_change) >= since]
    down = up = 0
    drops = []
    if changed:
        hist: dict[int, list[tuple[datetime, float]]] = {}
        for oid, p, at in s.execute(select(PriceObservation.offer_id, PriceObservation.price_jod, PriceObservation.observed_at)
                                    .where(PriceObservation.offer_id.in_(changed))):
            hist.setdefault(oid, []).append((_aware(at), float(p)))
        brand = dict(s.execute(select(PhoneVariant.id, Brand.name_en).join(PhoneModel, PhoneVariant.model_id == PhoneModel.id)
                               .join(Brand, PhoneModel.brand_id == Brand.id)).all())
        names = {st.id: st.name for st in s.scalars(select(Store))}
        for oid in changed:
            seen = sorted(hist.get(oid, []))
            before = [p for at, p in seen if at < since]
            if not before:
                continue                               # new listing, not a change
            o, fam = live[oid]
            was, now_p = before[-1], float(o.price_jod)
            if now_p < was:
                down += 1
                drops.append({"name": _shown_name(brand.get(o.variant_id, ""), fam), "shop": names.get(o.store_id, "?"),
                              "was": was, "now": now_p, "pct": round(100 * (was - now_p) / was, 1), "url": o.url})
            elif now_p > was:
                up += 1
    drops.sort(key=lambda d: -d["pct"])
    held = s.query(Offer).filter(Offer.match_status == "held").count()
    return {"down": down, "up": up, "drops": drops[:top], "held": held}


def _named(s: Session, problems: list[dict]) -> list[dict]:
    names = {st.slug: st.name for st in s.scalars(select(Store))}
    return [p | {"name": names.get(p["shop"], p["shop"]), "detail": p["detail"].splitlines()[0][:160] if p["detail"] else ""}
            for p in problems]


def extra(s: Session) -> dict:
    """Everything above; a part that fails is left out (its error is kept for the page)."""
    from .health import shop_problems
    from .search_check import summary as search_summary
    out: dict = {}
    for key, fn in (("search", search_summary), ("system", cloud_status if os.environ.get("KAMKAM_CLOUD") == "1" else system_status), ("doctor", doctor_report), ("problems", lambda: _named(s, shop_problems(s))),
                    ("cheapest", lambda: cheapest_shops(s)), ("moves", lambda: price_moves(s))):
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001
            out[f"{key}_error"] = str(e)[:200]
    return out
