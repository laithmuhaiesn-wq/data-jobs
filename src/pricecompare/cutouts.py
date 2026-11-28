"""The nightly job that makes the product page's pictures without background (`cut-images`, owner 2026-11-27: all shops).

For every product with a page, the picture the site shows (website.picture) is cut once (cutout.cut) and stored in
Cloudflare R2 (bucket kamkam-cut) as <product id>.png; the site's worker serves it at kamkam.derbani.com/cut/<id>.png
and the app loads it from there. A product is cut again only when its picture changes; when the new picture cannot be
cut, the old file is deleted, so the site and the app show the shop's photo instead of a picture of something else.

What was done lives in ~/.derbani/cuts.json ({id: {"src": picture address, "ok": true/false, "day": "YYYY-MM-DD"}}),
kept between cloud runs with the jobs' other files. The site build reads it (website.CUTS) and uses /cut/<id>.png only
for products whose picture is still the one that was cut.

Pictures are read the polite way: the shop's robots.txt is obeyed, 3 s between two reads from one host, at most
MAX_READS a night, and nothing from a shop whose terms forbid copying its pictures (NO_COPY).
Needs CLOUDFLARE_API_TOKEN (R2 edit) and CLOUDFLARE_ACCOUNT_ID, like the other cloud jobs.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx

FILE = Path.home() / ".derbani" / "cuts.json"
BUCKET = "kamkam-cut"
MAX_READS = 400            # pictures read per night at most (the first nights work through the backlog)
MAX_SECONDS = 25 * 60      # and never longer than this
RETRY_DAYS = 30            # a picture that could not be read is tried again after this
NO_COPY = ("rokonbaghdad",)  # shops whose terms say their pictures may not be copied (docs/data-source-permissions.md)


def load(path: Path | None = None) -> dict[str, dict]:
    try:
        return {str(k): v for k, v in json.loads((path or FILE).read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def save(d: dict, path: Path | None = None) -> None:
    p = path or FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(p)


def ready(cuts: dict, pictures: dict[int, str | None]) -> set[int]:
    """Products whose current picture has a cut-out stored."""
    return {pid for pid, src in pictures.items() if src and (c := cuts.get(str(pid))) and c.get("ok") and c.get("src") == src}


def todo(cuts: dict, pictures: dict[int, str | None], today: date) -> list[tuple[int, str]]:
    """Products to cut tonight: never tried, picture changed, or a failed read old enough to try again."""
    out = []
    for pid, src in pictures.items():
        if not src or any(n in (urlparse(src).netloc or "").lower() for n in NO_COPY):
            continue
        c = cuts.get(str(pid))
        if c and c.get("src") == src:
            if c.get("ok") or c.get("plain") is False:   # done, or the background is not plain (that never changes)
                continue
            if (today - date.fromisoformat(c.get("day") or "2000-01-01")).days < RETRY_DAYS:
                continue
        out.append((pid, src))
    return out


class R2:
    """Objects in one R2 bucket through Cloudflare's API (no extra keys needed)."""

    def __init__(self, bucket: str = BUCKET, http: httpx.Client | None = None):
        token, account = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        if not token or not account:
            raise SystemExit("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are needed")
        self.base = f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket}/objects"
        self.http = http or httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=60)

    def put(self, key: str, data: bytes) -> None:
        self.http.put(f"{self.base}/{key}", content=data, headers={"Content-Type": "image/png"}).raise_for_status()

    def delete(self, key: str) -> None:
        r = self.http.delete(f"{self.base}/{key}")
        if r.status_code != 404:
            r.raise_for_status()


def run(pictures: dict[int, str | None], store: R2, read, cuts: dict | None = None, today: date | None = None,
        max_reads: int = MAX_READS, max_seconds: float = MAX_SECONDS) -> dict[str, int]:
    """Cuts what is to do. `read(url) -> bytes` reads one picture (raises when it may not or cannot)."""
    from .cutout import cut
    today = today or date.today()
    cuts = load() if cuts is None else cuts
    started, n = time.monotonic(), {"cut": 0, "not plain": 0, "not read": 0, "left": 0}
    jobs = todo(cuts, pictures, today)
    for i, (pid, src) in enumerate(jobs):
        if i >= max_reads or time.monotonic() - started > max_seconds:
            n["left"] = len(jobs) - i
            break
        had = (cuts.get(str(pid)) or {}).get("ok")
        try:
            data = read(src)
        except Exception:
            cuts[str(pid)] = {"src": src, "ok": False, "day": today.isoformat()}
            n["not read"] += 1
            if had:
                store.delete(f"{pid}.png")
            continue
        try:
            png = cut(data)
        except Exception:   # not a picture Pillow can open
            png = None
        if png:
            store.put(f"{pid}.png", png)
            cuts[str(pid)] = {"src": src, "ok": True, "day": today.isoformat()}
            n["cut"] += 1
        else:
            if had:
                store.delete(f"{pid}.png")
            cuts[str(pid)] = {"src": src, "ok": False, "plain": False, "day": today.isoformat()}
            n["not plain"] += 1
    gone = [k for k in cuts if int(k) not in pictures]   # products with no page any more: their entry goes (file kept, harmless)
    for k in gone:
        del cuts[k]
    save(cuts)
    return n


def reader():
    """Reads one shop picture politely: robots.txt obeyed, 3 s between reads from one host, our usual name."""
    from .collectors.base import USER_AGENT, PoliteClient
    rules = PoliteClient(min_interval=3.0)
    http = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
    last: dict[str, float] = {}

    def read(url: str) -> bytes:
        if not rules._robots_for(url).can_fetch(url):
            raise PermissionError(f"robots.txt disallows {url}")
        host = urlparse(url).netloc
        wait = last.get(host, 0) + 3.0 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        last[host] = time.monotonic()
        r = http.get(url)
        r.raise_for_status()
        if len(r.content) > 15_000_000:
            raise ValueError("picture too big")
        return r.content
    return read


def main() -> None:
    from datetime import datetime, timezone
    from .db.session import get_engine, make_session
    from .views import build_variant_data
    from .website import LIVE_CATEGORIES, picture
    with make_session(get_engine()) as s:
        every = build_variant_data(s, datetime.now(timezone.utc))
    pictures = {v["id"]: picture(v) for v in every if v["offers"] and v["category"] in LIVE_CATEGORIES}
    n = run(pictures, R2(), reader())
    print(f"pictures without background: {n['cut']} new, {n['not plain']} background not plain, "
          f"{n['not read']} not read, {n['left']} left for the next nights; {len(ready(load(), pictures))} ready")
