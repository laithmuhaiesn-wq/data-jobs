"""What has been settled by hand (docs/product-data-plan.md, section 3): it wins over every rule.

data/products/<kind>.json   the product register: how a product's name is really written, and which catalogue spellings
                            are the same product. {"products": {"Brand:family": {"en": "...", "same": "Brand:family"}}}
data/decisions/<kind>.csv   one shop's exact title = this product / not ours / not enough information, with the reason
                            (shop,title,answer,storage,ram,market,reason). shop "*" = any shop.
A title the shop changes is a new title: it is read by the rules again until it is settled."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[3] / "data"
LITTLE, NOT_OURS = "little", "not ours"


@dataclass(frozen=True)
class Decision:
    answer: str                 # "Brand:family", or LITTLE, or NOT_OURS
    storage: int | None = None
    ram: int | None = None
    market: str = "unknown"

    @property
    def brand(self) -> str:
        return self.answer.partition(":")[0]

    @property
    def family(self) -> str:
        return self.answer.partition(":")[2]


def norm(title: str) -> str:
    """Titles are compared without regard to capitals and spacing: shops change those without changing the product."""
    return re.sub(r"\s+", " ", title).strip().lower()


@lru_cache(maxsize=1)
def register() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted((DATA / "products").glob("*.json")):
        out.update(json.loads(f.read_text(encoding="utf-8"))["products"])
    return out


@lru_cache(maxsize=1)
def decisions() -> dict[tuple[str, str], Decision]:
    out: dict[tuple[str, str], Decision] = {}
    for f in sorted((DATA / "decisions").glob("*.csv")):
        with f.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                key = (row["shop"].strip(), norm(row["title"]))
                if key in out:
                    raise ValueError(f"{f.name}: settled twice: {key}")
                out[key] = Decision(row["answer"].strip(), int(row["storage"]) if row["storage"].strip() else None,
                                    int(row["ram"]) if row["ram"].strip() else None, row["market"].strip() or "unknown")
    return out


@lru_cache(maxsize=1)
def moved() -> dict[int, int]:
    """Product pages that are now another product's page (two products that were one): old id -> id. Chains are followed."""
    f = DATA / "moved.json"
    raw = {int(k): int(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()} if f.exists() else {}
    out = {}
    for old, new in raw.items():
        seen = {old}
        while new in raw and new not in seen:
            seen.add(new)
            new = raw[new]
        if new not in seen:
            out[old] = new
    return out


def aliases(live: dict[int, dict]) -> dict[int, dict]:
    """Old ids people may have saved, answered with today's product (under the old id, so saved items and alerts go on)."""
    return {old: {**live[new], "id": old} for old, new in moved().items() if old not in live and new in live}


def decide(shop: str, title: str) -> Decision | None:
    d = decisions()
    t = norm(title)
    return d.get((shop, t)) or d.get(("*", t))


def same_as(key: str) -> str:
    """The register's own spelling of a product ("Tecno:go 3" is "Tecno:spark go 3"); itself when nothing is said."""
    reg = register()
    seen = {key}
    while (nxt := reg.get(key, {}).get("same")) and nxt not in seen:
        key = nxt
        seen.add(key)
    return key


def shown_name(brand: str, family: str) -> str | None:
    """The name as the maker writes it, when it is in the register."""
    return register().get(f"{brand}:{family}", {}).get("en")


def arabic_name(brand: str, family: str) -> str | None:
    return register().get(f"{brand}:{family}", {}).get("ar")
