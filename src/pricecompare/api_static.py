"""The app's data as plain files on derbani.com (the free fix for the sleeping Render server, 2026-11-13).

Every hour, right after the website is built, the API itself answers each question the app asks and the answers are
saved under web_build/api/. Cloudflare serves them instantly and never sleeps. The app reads these files first and asks
the Render server only for typed searches, or if a file is missing. Same code, so the same answers.

    api/categories.json, guides.json, shops.json, deals.json
    api/popular-<category>.json, brands-<category>.json
    api/list-<category>.json, list-<category>-<brand>.json   (the empty search, per category and per brand)
    api/summaries.json                                       (every product's summary: the saved list)
    api/v/<id>.json                                          (one product: shops, history, specs), answered by the worker from
    api/vs/<id % 200>.json                                   200 bundles: Cloudflare allows 20,000 files a site, and one file
                                                             per product made 19,136 of them (2026-11-25)
"""
from __future__ import annotations

import json
import re
from pathlib import Path


BUNDLES = 200        # the same number is in worker/index.js


def brand_file(brand: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", brand.lower()).strip("-")


def build(out: Path, engine=None, data: list[dict] | None = None) -> int:
    from fastapi.testclient import TestClient

    from .api.app import create_app
    from .matching import settled

    c = TestClient(create_app(engine, rate_limit=10**9, preloaded=data))
    root = out / "api"
    (root / "vs").mkdir(parents=True, exist_ok=True)
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
    save("filters.json", "/filters")
    summaries = []
    for cat in cats:
        save(f"popular-{cat}.json", "/popular", {"limit": 12, "category": cat})
        brands = save(f"brands-{cat}.json", "/brands", {"category": cat})["results"]
        mine = save(f"list-{cat}.json", "/search", {"q": "", "limit": 1000, "category": cat})["results"]
        seen = {v["id"] for v in mine}
        for b in brands:
            more = save(f"list-{cat}-{brand_file(b['brand'])}.json", "/search", {"q": "", "brand": b["brand"], "limit": 1000, "category": cat})["results"]
            # a kind with over 1000 products (keyboards and mice: 1102 on 2026-11-27): the rest come from the brand lists,
            # so every product is in summaries.json and search.json (the app's and api.derbani.com's search)
            mine += [v for v in more if v["id"] not in seen]
            seen |= {v["id"] for v in more}
        summaries += mine
    # saved before two products were joined: the old id gets today's summary (search.json has no row for it)
    old = list(settled.aliases({v["id"]: v for v in summaries}).values())
    (root / "summaries.json").write_text(json.dumps({"results": summaries + old}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    bundles: dict[int, dict[int, dict]] = {n: {} for n in range(BUNDLES)}
    for v in summaries + old:
        r = c.get(f"/variants/{v['id']}")
        r.raise_for_status()
        bundles[v["id"] % BUNDLES][v["id"]] = r.json()
        written += 1
    for n, products in bundles.items():
        (root / "vs" / f"{n}.json").write_text(json.dumps(products, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (root / "search.json").write_text(search_file(summaries), encoding="utf-8")
    return written + 2


def search_file(summaries: list[dict]) -> str:
    """Everything the app needs to search on the phone itself, with the server's own rules (search.py): every product's
    search text, in the order of summaries.json, plus the spelling rules. Typed searches then never reach the PC, so
    any number of people can search at once, and search works while the PC is off (2026-11-18)."""
    from .search import (_ARTICLES, _LETTERS, ALONE, AR_PHRASES, AR_WORDS, CATEGORY_WORDS, EN_WORDS, KNOWN_WORDS, MAX_WORDS,
                         STOP_WORDS, fold, hay_of)
    letters = {chr(k): (v if isinstance(v, str) else chr(v) if v is not None else "") for k, v in _LETTERS.items()}
    rows = []
    for v in summaries:
        text, compact, _ = hay_of(v)
        rows.append([v["id"], text, compact])
    return json.dumps({"v": 1, "letters": letters, "words": AR_WORDS, "phrases": {fold(k): x for k, x in AR_PHRASES.items()},
                       "stop": sorted(STOP_WORDS), "categories": CATEGORY_WORDS, "alone": ALONE, "en": EN_WORDS, "known": sorted(KNOWN_WORDS),
                       "articles": list(_ARTICLES), "max": MAX_WORDS, "items": rows}, ensure_ascii=False, separators=(",", ":"))
