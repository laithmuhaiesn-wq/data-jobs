"""Read-only JSON API for the app. Data is built from the database at most every CACHE_SECONDS, so taps never hit the DB."""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import func, select

from ..db.models import Offer, Store
from ..db.session import get_engine, make_session
from ..search import KNOWN_WORDS, haystack, match, query_category, query_words
from ..views import build_variant_data

CACHE_SECONDS = 300
RATE_LIMIT = 120    # requests a minute from one visitor; normal use of the app stays far below this
DISCLAIMER = "Prices are copied from each shop's public page and may be out of date. Check the shop before buying."


def shop_list(s) -> list[dict]:
    """Shops we compare, with how many matched offers each has and when it was last checked."""
    rows = s.execute(select(Store.name, Store.site_url, func.count(Offer.id), func.max(Offer.last_checked))
                     .join(Offer, Offer.store_id == Store.id).where(Offer.match_status == "matched")
                     .group_by(Store.id).order_by(func.count(Offer.id).desc(), Store.name)).all()
    out = []
    for name, url, n, last in rows:
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        out.append({"name": name, "url": url, "offers": n, "checked": last.isoformat() if last else None})
    return out


def visitor(request: Request) -> str:
    """The caller's address. Behind the host's proxy the real one arrives in a header."""
    h = request.headers
    return (h.get("cf-connecting-ip") or h.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


def create_app(engine=None, rate_limit: int = RATE_LIMIT) -> FastAPI:
    # no interactive docs or schema page on the public server: nothing there is needed by the app
    app = FastAPI(title="Jordan phone prices", version="0.1", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=800)
    hits: dict[str, deque] = {}
    swept = [0.0]

    @app.middleware("http")
    async def limit_and_harden(request: Request, call_next):
        """Stops one visitor from flooding the server or copying everything quickly; adds basic safety headers."""
        if request.url.path != "/health":
            now = time.monotonic()
            q = hits.setdefault(visitor(request), deque())
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= rate_limit:
                return JSONResponse({"detail": "Too many requests. Try again in a minute."}, status_code=429,
                                    headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
            q.append(now)
            if len(hits) > 5000 and now - swept[0] > 10:  # forget visitors who have gone quiet, so memory stays small
                swept[0] = now                              # (at most every 10 s, so a flood cannot make this the slow part)
                for k in [k for k, v in hits.items() if not v or now - v[-1] > 60]:
                    del hits[k]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    state: dict = {"at": 0.0, "data": [], "built": None, "shops": [], "hay": {}}
    rebuild = threading.Lock()

    def data() -> list[dict]:
        if time.monotonic() - state["at"] > CACHE_SECONDS or not state["data"]:
            # one rebuild at a time: with many visitors at once, the rest keep reading the copy we already have
            if rebuild.acquire(blocking=not state["data"]):
                try:
                    if time.monotonic() - state["at"] > CACHE_SECONDS or not state["data"]:
                        try:
                            with make_session(engine or get_engine()) as s:
                                fresh, shops = build_variant_data(s), shop_list(s)
                        except Exception:
                            if not state["data"]:
                                raise
                            state["at"] = time.monotonic() - CACHE_SECONDS + 30  # database trouble: keep the old copy, retry in 30 s
                        else:
                            # what each phone is searched by, worked out once per rebuild instead of once per request
                            # (added to the old ones first, so a request reading the old list still finds its phones)
                            state["hay"] = {**state["hay"], **{v["id"]: haystack(v["label"], v["brand"], v["brand_ar"], v["storage_gb"]) for v in fresh}}
                            state["data"], state["shops"] = fresh, shops
                            state["at"], state["built"] = time.monotonic(), datetime.now(timezone.utc).isoformat()
                finally:
                    rebuild.release()
        return state["data"]

    def summary(v: dict) -> dict:
        return {k: v[k] for k in ("id", "category", "brand", "brand_ar", "model", "storage", "storage_gb", "ram_gb", "label", "market", "gray", "image", "images",
                                  "best_price", "best_store", "highest_price", "save", "ranked_shops", "shops",
                                  "was", "drop", "drop_pct", "dropped_at", "at_lowest")}

    def in_category(category: str | None, default: str | None = "phone"):
        """The products of one category ("phone", "tablet") or of all ("all"). App versions from before categories
        send nothing and were built for phones only, so nothing means phones on the home lists."""
        category = category or default
        return [v for v in data() if category in (None, "all") or v["category"] == category]

    def rank_key(v: dict):  # most compared first, then cheapest; variants without a ranked price last
        return (-v["ranked_shops"], v["best_price"] is None, v["best_price"] or 0, v["label"])

    @app.get("/health")
    def health():
        # the keep-awake ping must not touch the database: Neon's free plan counts every minute the database is awake (loads once after a restart)
        return {"ok": True, "variants": len(state["data"] or data()), "built": state["built"]}

    @app.get("/search")
    def search(q: str = Query("", max_length=80), brand: str | None = Query(None, max_length=40),
               category: str | None = Query(None, max_length=20), limit: int = Query(30, ge=1, le=300)):
        # typed text searches everything unless it names a kind ("تابلت سامسونج"); the empty list is a home list
        rows = [v for v in in_category(category or query_category(q), default=None if q.strip() else "phone")
                if not brand or brand.lower() in (v["brand"].lower(), v["brand_ar"])]
        hay = state["hay"]
        words = query_words(q)
        # a typing slip is forgiven only for a word that no phone contains as typed ("samsng"), never for a real one
        # ("pova" is a real model name: with no Pova on sale the answer is nothing, not the Huawei Nova)
        forgive = frozenset(w for w in words if w not in KNOWN_WORDS and not any(w in hay[v["id"]][0] or w in hay[v["id"]][1] for v in data()))
        found = [(slips, v) for v in rows if (slips := match(words, hay[v["id"]], forgive)) is not None]
        found.sort(key=lambda x: (x[0], rank_key(x[1])))
        hits = [v for _, v in found]
        return {"disclaimer": DISCLAIMER, "count": len(hits), "results": [summary(v) for v in hits[:limit]]}

    @app.get("/popular")
    def popular(limit: int = Query(12, ge=1, le=50), category: str | None = Query(None, max_length=20)):
        """Products with the most shops comparing them (a real-demand list replaces this later)."""
        top = sorted((v for v in in_category(category) if v["ranked_shops"] >= 2 and not v["gray"]), key=rank_key)[:limit]
        return {"disclaimer": DISCLAIMER, "results": [summary(v) for v in top]}

    @app.get("/brands")
    def brands(category: str | None = Query(None, max_length=20)):
        counts: dict[str, dict] = {}
        for v in in_category(category):
            b = counts.setdefault(v["brand"], {"brand": v["brand"], "brand_ar": v["brand_ar"], "variants": 0})
            b["variants"] += 1
        return {"results": sorted(counts.values(), key=lambda b: -b["variants"])}

    @app.get("/deals")
    def deals(limit: int = Query(30, ge=1, le=60), category: str | None = Query(None, max_length=20)):
        """Two lists: products whose best shop cut its own price in the last 7 days, and the widest gaps between shops."""
        live = [v for v in in_category(category) if not v["gray"] and v["best_price"] is not None]
        drops = sorted((v for v in live if v["drop"] >= 1), key=lambda v: (-v["drop_pct"], v["label"]))[:limit]
        gaps = sorted((v for v in live if v["ranked_shops"] >= 2 and v["save"] >= 5), key=lambda v: (-v["save"], v["label"]))[:limit]
        return {"disclaimer": DISCLAIMER, "built": state["built"], "drops": [summary(v) for v in drops], "gaps": [summary(v) for v in gaps]}

    @app.get("/variants")
    def variants(ids: str = Query("", max_length=600)):
        """Several phones at once (the saved list). Unknown ids are left out."""
        want = [int(x) for x in ids.split(",") if x.strip().isdigit()][:80]
        by_id = {v["id"]: v for v in data()}
        return {"disclaimer": DISCLAIMER, "built": state["built"], "results": [summary(by_id[i]) for i in want if i in by_id]}

    @app.get("/shops")
    def shops():
        data()
        return {"results": state["shops"]}

    @app.get("/variants/{variant_id}")
    def variant(variant_id: int):
        for v in data():
            if v["id"] == variant_id:
                return {"disclaimer": DISCLAIMER, "built": state["built"], **v}
        raise HTTPException(404, "unknown variant")

    return app
