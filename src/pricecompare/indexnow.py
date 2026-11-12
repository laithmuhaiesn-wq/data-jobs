"""IndexNow: tells Bing (which also feeds ChatGPT and Copilot search) and other engines which pages are new, so they are
crawled within hours instead of weeks. Google does not use IndexNow; it reads the sitemap (submitted in Search Console).

    prepare: before publishing, compare the new sitemap with the live one and save the new addresses to a file
    send:    after publishing, submit that list (plus the home and deals pages) once
The key is public by design: the engines check that the file /<key>.txt on the site contains it.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

KEY = "8f3c1d7a5b2e4f6098a1c3e5d7b9f2a4"
HOST = "derbani.com"
ALWAYS = ["https://derbani.com/", "https://derbani.com/en", "https://derbani.com/deals", "https://derbani.com/en/deals"]


def _locs(xml: str) -> set[str]:
    return set(re.findall(r"<loc>([^<]+)</loc>", xml))


def prepare(new_sitemap: Path, out: Path, live_url: str = "https://derbani.com/sitemap.xml") -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(live_url, headers={"User-Agent": "Derbani site build"}), timeout=30) as r:
            live = _locs(r.read().decode("utf-8"))
    except Exception:
        live = set()
    fresh = sorted(_locs(new_sitemap.read_text(encoding="utf-8")) - live)
    urls = ALWAYS + [u for u in fresh if u not in ALWAYS]
    out.write_text("\n".join(urls[:10000]) + "\n", encoding="utf-8")
    return len(fresh)


def send(listing: Path) -> int:
    urls = [u for u in listing.read_text(encoding="utf-8").split() if u.startswith("https://derbani.com")]
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"https://{HOST}/{KEY}.txt", "urlList": urls}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status
