"""Products whose listings are known to be one product (owner 2026-11-25: "I don't care if the prices are so different if we
are sure that they are the same product"). Such a product is never hidden for its prices, never held, and not listed on the
admin page's accuracy check, however far apart the shops are.

Sure means that EVERY title it has now was read and judged:
- data/sure.json "titles": product -> titles judged to be that product (`python -m pricecompare.cli apart-same <product id> ...`
  adds the titles a product has now; the daily doctor runs it after reading them);
- the finished kinds' saved answers (tests/truth), where every title was read by hand.
A new title counts as judged when it only differs in its colour or in the shop's own code at the end. "doubt" in data/sure.json:
products that stay doubtful whatever else says they are sure, with the reason."""
from __future__ import annotations

import csv
import json
import re
from functools import lru_cache
from pathlib import Path

from . import settled

FILE = settled.DATA / "sure.json"
TRUTH = settled.DATA.parent / "tests" / "truth"
FINISHED = ("phone", "audio", "tv", "monitor")      # kinds whose every title was read by hand (docs/product-data-plan.md)
COLOURS = re.compile(r"\b(?:black|white|blue|red|pink|purple|green|gr[ae]y|silver|gold|beige|teal|squad|camo|orange|yellow|graphite|"
                     r"(?:light|dark|midnight|space|sky|navy)\b)\b")


def plain(title: str) -> str:
    """The title without its colour, the shop's code after the last dash, and signs."""
    t = re.sub(r"\s[-–—|]\s+(?=\S*\d)[a-z0-9-]{6,}\s*$", "", settled.norm(title))
    return " ".join(re.findall(r"[a-z0-9+؀-ۿ]+", COLOURS.sub(" ", t)))


def key(brand: str, family: str, storage: int | None, ram: int | None) -> str:
    return f"{brand}:{family}|{storage or 0}|{ram or 0}"


def _read() -> dict:
    return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {"titles": {}, "doubt": {}}


@lru_cache(maxsize=1)
def judged() -> dict[str, set[str]]:
    out = {k: {plain(t) for t in v} for k, v in _read()["titles"].items()}
    for kind in FINISHED:
        f = TRUTH / f"{kind}_titles.csv"
        if not f.exists():
            continue
        with f.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if " | " in r["answer"]:
                    product, storage, ram, _ = r["answer"].split(" | ")
                    # a title may leave the memory out: the product's key then says it, so the title counts for any memory
                    out.setdefault(f"{product}|{storage}", set()).add(plain(r["title"]))
    return out


def sure(product: str, titles: list[str]) -> bool:
    if product.rpartition("|")[0].rpartition("|")[0] in _read_doubt() or not titles:
        return False
    known = judged().get(product, set()) | judged().get(product.rpartition("|")[0], set())
    return bool(known) and all(plain(t) in known for t in titles)


@lru_cache(maxsize=1)
def _read_doubt() -> dict[str, str]:
    return _read()["doubt"]


def add(titles: dict[str, list[str]]) -> int:
    """Saves the titles as judged; returns how many are new."""
    data, n = _read(), 0
    for k, ts in titles.items():
        have = set(data["titles"].get(k, []))
        n += len(set(ts) - have)
        data["titles"][k] = sorted(have | set(ts))
    data["titles"] = dict(sorted(data["titles"].items()))
    FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    judged.cache_clear()
    _read_doubt.cache_clear()
    return n


def products(s, variant_ids) -> dict[int, str]:
    """variant id -> its key."""
    from sqlalchemy import select

    from ..db.models import Brand, PhoneModel, PhoneVariant
    return {vid: key(b, f, g, r) for vid, b, f, g, r in s.execute(
        select(PhoneVariant.id, Brand.name_en, PhoneModel.family, PhoneVariant.storage_gb, PhoneVariant.ram_gb)
        .join(PhoneModel, PhoneVariant.model_id == PhoneModel.id).join(Brand, PhoneModel.brand_id == Brand.id)
        .where(PhoneVariant.id.in_(list(variant_ids))))}


def mark(s, variant_ids: list[int]) -> int:
    from sqlalchemy import select

    from ..db.models import Offer
    keys = products(s, variant_ids)
    titles: dict[str, list[str]] = {}
    for vid, t in s.execute(select(Offer.variant_id, Offer.raw_title).where(
            Offer.variant_id.in_(list(keys)), Offer.match_status.in_(("matched", "held")))):
        titles.setdefault(keys[vid], []).append(settled.norm(t))
    return add(titles)
