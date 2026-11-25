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


PLUGS = (("type-c", r"\btype ?-?c\b|\busb ?-?c\b"), ("lightning", r"\blightning\b"), ("3.5mm", r"\b3\.5 ?mm\b|\baux\b|\bone jack\b"), ("usb", r"\busb\b"))
PLUG_NAMES = {"type-c": "Type-C", "lightning": "Lightning", "3.5mm": "3.5 mm", "usb": "USB"}


def split(brand: str | None, family: str, title: str) -> str:
    """A model whose versions are different products ("by": the plug; "re": a part of the title): the family with its
    version. The plug that is not said stays out of the name: that listing is then the plain model."""
    entry = register().get(same_as(f"{brand}:{family}"), {}) if brand else {}
    low = title.lower()
    if entry.get("by") == "plug":
        kind = next((k for k, pat in PLUGS if re.search(pat, low)), None)
        return f"{family} {kind}" if kind else family
    if entry.get("re") and (m := re.search(entry["re"], low)):
        return f"{family} " + re.sub(r"\s+", " ", m.group(1)).strip()
    return family


def base_of(key: str) -> str | None:
    """The registered product a key is a version of ("Lenovo:audio e06 usb" -> "Lenovo:audio e06"); None when it is none."""
    reg = register()
    brand, _, family = key.partition(":")
    words = family.split()
    for n in range(len(words) - 1, 0, -1):
        base, last = f"{brand}:{' '.join(words[:n])}", " ".join(words[n:])
        e = reg.get(base, {})
        if e.get("by") == "plug" and last in PLUG_NAMES or e.get("re"):
            return base
    return None


def shown_name(brand: str, family: str) -> str | None:
    """The name as the maker writes it, when it is in the register (with the version, for a model that is split)."""
    reg = register()
    entry = reg.get(f"{brand}:{family}", {})
    if entry.get("en"):
        return entry["en"]
    base, _, last = family.rpartition(" ")
    while base:
        e = reg.get(f"{brand}:{base}", {})
        if e.get("by") == "plug" and last in PLUG_NAMES:
            return f'{e["en"]} {PLUG_NAMES[last]}'
        if e.get("re"):
            return f'{e["en"]} {last.upper()}'
        base, _, word = base.rpartition(" ")
        last = f"{word} {last}"
    return None


def arabic_name(brand: str, family: str) -> str | None:
    return register().get(f"{brand}:{family}", {}).get("ar")
