"""Polite HTTP client shared by all collectors.

Rules (see plan): obey robots.txt, at most one request per `min_interval`
seconds per host, honest User-Agent, backoff on 429/5xx, no image fetches.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx

from .robots import RobotsRules

USER_AGENT = "PriceCompareJO-pilot/0.1 (private research pilot; prices only)"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif")


class RobotsBlocked(Exception):
    pass


class PoliteClient:
    def __init__(self, min_interval: float = 3.0, max_retries: int = 3, client: httpx.Client | None = None):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        self._robots: dict[str, RobotsRules] = {}
        self._last: dict[str, float] = {}
        self._delay: dict[str, float] = {}
        self.request_count = 0

    def _wait(self, host: str) -> None:
        interval = max(self.min_interval, self._delay.get(host, 0.0))  # a shop's Crawl-delay can only slow us down
        wait = self._last.get(host, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.monotonic()

    def _robots_for(self, url: str) -> RobotsRules:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin not in self._robots:
            rp = RobotsRules()
            self._wait(p.netloc)
            self.request_count += 1
            try:
                r = self.client.get(f"{origin}/robots.txt")
                if r.status_code == 200:
                    rp = RobotsRules.parse(r.text, USER_AGENT)
                elif r.status_code in (401, 403):
                    rp.disallow_all = True
                else:
                    rp.allow_all = True
            except httpx.HTTPError:
                rp.disallow_all = True  # unknown rules: stay out
            self._robots[origin] = rp
            self._delay[p.netloc] = rp.crawl_delay
        return self._robots[origin]

    def get(self, url: str) -> httpx.Response:
        if urlparse(url).path.lower().endswith(IMAGE_SUFFIXES):
            raise RobotsBlocked(f"image fetch refused: {url}")
        if not self._robots_for(url).can_fetch(url):
            raise RobotsBlocked(f"robots.txt disallows {url}")
        host = urlparse(url).netloc
        delay = self.min_interval
        for attempt in range(self.max_retries + 1):
            self._wait(host)
            self.request_count += 1
            r = self.client.get(url)
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get("retry-after", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else delay)
                delay *= 2
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("unreachable")
