"""The app's data as plain files on derbani.com (the free fix for the sleeping Render server, 2026-11-13).

Every hour, right after the website is built, the API itself answers each question the app asks and the answers are
saved under web_build/api/. Cloudflare serves them instantly and never sleeps. The app reads these files first and asks
the Render server only for typed searches, or if a file is missing. Same code, so the same answers.

    api/categories.json, guides.json, shops.json, deals.json
    api/popular-<category>.json, brands-<category>.json
    api/list-<category>.json, list-<category>-<brand>.json   (the empty search, per category and per brand)
    api/summaries.json                                       (every product's summary: the saved list)
    api/v/<id>.json                                          (one product: shops, history, specs)
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def brand_file(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


def build(out: Path, engine=None) -> int:
    from fastapi.testclient import TestClient

    from .api.app import create_app

    c = TestClient(create_app(engine, rate_limit=10**9))
    root = out / "api"
    (root / "v").mkdir(parents=True, exist_ok=True)
    written = 0

    def save(name: str, path: str, params: dict | None = None) -> dict:
        nonlocal written
        r = c.get(path, params=params or {})
        r.raise_for_status()
        body = r.json()
        (root / name).write_text(json.dumps(body, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written += 1
        return body

    cats = [x["key"] for x in save("categories.json", "/categories")["results"]]
    save("guides.json", "/guides")
    save("shops.json", "/shops")
    save("deals.json", "/deals", {"category": "all"})
    summaries = []
    for cat in cats:
        save(f"popular-{cat}.json", "/popular", {"limit": 12, "category": cat})
        brands = save(f"brands-{cat}.json", "/brands", {"category": cat})["results"]
        summaries += save(f"list-{cat}.json", "/search", {"q": "", "limit": 1000, "category": cat})["results"]
        for b in brands:
            save(f"list-{cat}-{brand_file(b['brand'])}.json", "/search", {"q": "", "brand": b["brand"], "limit": 1000, "category": cat})
    (root / "summaries.json").write_text(json.dumps({"results": summaries}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for v in summaries:
        save(f"v/{v['id']}.json", f"/variants/{v['id']}")
    return written + 1
