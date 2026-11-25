"""The answer for one shop's title, without a database: what the saved answers (tests/truth/<kind>_titles.csv) are made of.

`python -m pricecompare.matching.answers phone` writes the file again after a change that was looked at line by line."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from . import settled
from .parse import parse_title

TRUTH = Path(__file__).resolve().parents[3] / "tests" / "truth"


def answer(shop: str, title: str) -> str:
    """"Brand:family | storage | RAM | market", or "little", "not ours", "-" (not one of our kinds), "? kind" (kind known, not which)."""
    d = settled.decide(shop, title)
    if d is not None:
        if d.answer in (settled.LITTLE, settled.NOT_OURS):
            return d.answer
        return " | ".join((settled.same_as(d.answer), str(d.storage), str(d.ram or ""), d.market))
    p = parse_title(title)
    if not p.is_product:
        return "-"
    if p.storage_gb is None:
        return f"? {p.category} {settled.same_as(p.family_key)}"
    return " | ".join((settled.same_as(p.family_key), str(p.storage_gb), str(p.ram_gb or ""), p.market_version))


def load(kind: str) -> list[dict]:
    with (TRUTH / f"{kind}_titles.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write(kind: str, rows: list[tuple[str, str]]) -> None:
    with (TRUTH / f"{kind}_titles.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["shop", "title", "answer"])
        for shop, title in sorted(set(rows)):
            w.writerow([shop, title, answer(shop, title)])


if __name__ == "__main__":
    write(sys.argv[1], [(r["shop"], r["title"]) for r in load(sys.argv[1])])
