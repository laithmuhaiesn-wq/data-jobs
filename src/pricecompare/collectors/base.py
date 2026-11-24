"""Polite HTTP client shared by all collectors.

Rules (see plan): obey robots.txt, at most one request per `min_interval`
seconds per host, honest User-Agent, backoff on 429/5xx, no image fetches.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import bot_auth
from .robots import RobotsRules

# Honest name and a contact page for shop owners (plan rule). Generic: no personal name or email.
USER_AGENT = "DerbaniBot/1.0 (+https://derbani.com/remove; Jordan price comparison, reads prices only)"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif")


class RobotsBlocked(Exception):
    pass


class ChallengeBlocked(Exception):
    """The shop answered with a bot check (Cloudflare challenge). Never worked around: the run stops for that shop."""


class PoliteClient:
    def __init__(self, min_interval: float = 3.0, max_retries: int = 3, client: httpx.Client | None = None,
                 shared_pace: Path | None = None, sign: bool = False):
        self.min_interval = min_interval
        self.shared_pace = shared_pace
        self.max_retries = max_retries
        self.client = client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)
        if sign and (s := bot_auth.signer()):   # proves to the shop that it is really DerbaniBot
            self.client.event_hooks = {"request": [s], "response": []}
        self._robots: dict[str, RobotsRules] = {}
        self._last: dict[str, float] = {}
        self._delay: dict[str, float] = {}
        self.request_count = 0

    def _wait(self, host: str) -> None:
        interval = max(self.min_interval, self._delay.get(host, 0.0))  # a shop's Crawl-delay can only slow us down
        wait = self._last.get(host, 0) + interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        if self.shared_pace:
            self._shared_wait()
        self._last[host] = time.monotonic()

    def _shared_wait(self) -> None:
        """One pace for a group of shops behind one gate, across every job on this computer (Shopify counts a visitor's
        requests over all its shops together): the time of the group's last request sits in a file, guarded by a lock
        file, so two jobs never ask at once and the gap is kept even between different shops."""
        p = self.shared_pace
        p.parent.mkdir(parents=True, exist_ok=True)
        lock = p.with_suffix(".lock")
        while True:
            try:
                os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                break
            except FileExistsError:
                try:
                    if time.time() - lock.stat().st_mtime > 900:  # left by a job that crashed
                        lock.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                time.sleep(1)
        try:
            try:
                last = float(p.read_text())
            except (OSError, ValueError):
                last = 0.0
            wait = last + self.min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            p.write_text(str(time.time()))
        finally:
            lock.unlink(missing_ok=True)

    def _robots_for(self, url: str) -> RobotsRules:
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        # shops behind a shared gate (Shopify: a few requests an hour) keep their robots.txt for 24 hours, as search
        # engines do, so each run's one allowed request reads prices; the rules are still obeyed (2026-11-23)
        saved = self.shared_pace.parent / "robots" / f"{p.netloc}.txt" if self.shared_pace else None
        if origin not in self._robots and saved and saved.exists() and time.time() - saved.stat().st_mtime < 86400:
            rp = RobotsRules.parse(saved.read_text(encoding="utf-8"), USER_AGENT)
            self._robots[origin] = rp
            self._delay[p.netloc] = rp.crawl_delay
        if origin not in self._robots:
            rp = RobotsRules()
            self._wait(p.netloc)
            self.request_count += 1
            try:
                r = self.client.get(f"{origin}/robots.txt")
                if r.status_code == 200:
                    rp = RobotsRules.parse(r.text, USER_AGENT)
                    if saved:
                        saved.parent.mkdir(parents=True, exist_ok=True)
                        saved.write_text(r.text, encoding="utf-8")
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
            try:
                r = self.client.get(url)
            except httpx.TransportError:  # slow shop or network blip: wait longer, try again (still polite)
                if attempt == self.max_retries:
                    raise
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == self.max_retries:
                    r.raise_for_status()
                retry_after = r.headers.get("retry-after", "")
                time.sleep(float(retry_after) if retry_after.isdigit() else delay)
                delay *= 2
                continue
            if r.headers.get("cf-mitigated", "").lower() == "challenge":
                raise ChallengeBlocked(f"bot check at {url}")
            r.raise_for_status()
            final = str(r.url)
            if final != url and not self._robots_for(final).can_fetch(final):
                # the shop redirected us somewhere robots.txt does not allow: we do not use that page
                raise RobotsBlocked(f"robots.txt disallows {final} (redirected from {url})")
            return r
        raise RuntimeError("unreachable")
