"""Link offers to catalog phone variants.

Auto-match only when brand + model family + storage all agree (plan rule). Anything else goes
to the review queue. Market versions stay separate variants so they never mix in best price.
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Brand, Offer, PhoneModel, PhoneVariant
from .parse import ParsedTitle, parse_title

AUTO = 0.9


def load_catalog(s: Session, csv_path: Path) -> int:
    """Seed brands/models from data/catalog.csv (columns: brand,family). Idempotent."""
    added = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            brand = s.scalar(select(Brand).where(Brand.name_en == row["brand"]))
            if brand is None:
                brand = Brand(name_en=row["brand"])
                s.add(brand)
                s.flush()
            # a model a person removed ("blocked:<family>", see grow.block_model) is not brought back from the file
            if s.scalar(select(PhoneModel).where(PhoneModel.brand_id == brand.id,
                                                 PhoneModel.family.in_([row["family"], "blocked:" + row["family"]]))) is None:
                s.add(PhoneModel(brand_id=brand.id, family=row["family"]))
                added += 1
    s.flush()
    return added


class Catalog:
    def __init__(self, s: Session):
        self.s = s
        self.exact: dict[str, PhoneModel] = {}
        self.loose: dict[str, list[PhoneModel]] = defaultdict(list)
        brands = {b.id: b.name_en for b in s.scalars(select(Brand))}
        for m in s.scalars(select(PhoneModel)):
            key = f"{brands[m.brand_id]}:{m.family}"
            self.exact[key] = m
            self.loose[ParsedTitle(brands[m.brand_id], m.family, None, None, "", "", True).family_key_no_net].append(m)

    def find(self, p: ParsedTitle) -> tuple[PhoneModel | None, float]:
        if p.family_key in self.exact:
            return self.exact[p.family_key], 1.0
        cands = self.loose.get(p.family_key_no_net, [])
        if re.search(r"\b[45]g\b", p.family):
            # An explicit 4G/5G is a different phone from a catalog entry with the other tag (A17 4G != A17 5G);
            # it may only fall back to an entry with no tag at all (every iPhone is 5G, the catalog says "iphone 17").
            cands = [m for m in cands if not re.search(r"\b[45]g\b", m.family)]
        if len(cands) == 1:
            return cands[0], AUTO
        return None, 0.0

    def variant(self, model: PhoneModel, p: ParsedTitle, ram: int | None = None) -> PhoneVariant:
        """ram is given only for phones that really come in several RAM sizes (see ram_splits); otherwise None."""
        v = self.s.scalar(select(PhoneVariant).where(
            PhoneVariant.model_id == model.id, PhoneVariant.storage_gb == p.storage_gb,
            PhoneVariant.connectivity == p.connectivity, PhoneVariant.market_version == p.market_version,
            PhoneVariant.ram_gb.is_(None) if ram is None else PhoneVariant.ram_gb == ram))
        if v is None:
            v = PhoneVariant(model_id=model.id, storage_gb=p.storage_gb, ram_gb=ram,
                             connectivity=p.connectivity, market_version=p.market_version)
            self.s.add(v)
            self.s.flush()
        return v


def _split_key(model: PhoneModel, p: ParsedTitle) -> tuple:
    return (model.id, p.storage_gb, p.connectivity, p.market_version)


def ram_splits(s: Session, cat: Catalog) -> dict[tuple, set[int]]:
    """Phones that really come in several RAM sizes, e.g. Galaxy A57 256GB with 8GB (409 JOD) and 12GB (459 JOD).

    Shops disagree on how they write RAM (some add "extended RAM": the same phone is 4GB at one shop and 8GB at
    another, at the same price), so a different number at another shop proves nothing. The proof is ONE shop listing
    the same model and storage with two RAM sizes at different prices. Once split, a phone stays split.
    """
    seen: dict[tuple, dict[int, dict[int, set]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for o in s.scalars(select(Offer)):
        p = parse_title(o.raw_title)
        if not p.is_product or p.storage_gb is None or not p.ram_gb:
            continue
        model, _ = cat.find(p)
        if model is not None:
            seen[_split_key(model, p)][o.store_id][p.ram_gb].add(o.price_jod)
    out: dict[tuple, set[int]] = defaultdict(set)
    for key, shops in seen.items():
        for rams in shops.values():
            if len(rams) >= 2 and len({min(prices) for prices in rams.values()}) >= 2:
                out[key] |= set(rams)
    for v in s.scalars(select(PhoneVariant).where(PhoneVariant.ram_gb.is_not(None))):
        out[(v.model_id, v.storage_gb, v.connectivity, v.market_version)].add(v.ram_gb)
    return dict(out)


def match_offers(s: Session, only_unmatched: bool = True) -> dict[str, int]:
    cat = Catalog(s)
    splits = ram_splits(s, cat)
    stats = {"matched": 0, "review": 0, "no_storage": 0, "not_phone": 0}
    for o in s.scalars(select(Offer)):
        p = parse_title(o.raw_title)
        if only_unmatched and o.match_status not in ("unmatched", "review", "no_storage"):
            # an offer matched earlier is left alone, unless its phone has since been split by RAM
            model = cat.find(p)[0] if o.match_status == "matched" and p.is_product and p.storage_gb is not None else None
            if model is None or _split_key(model, p) not in splits:
                continue
        if not p.is_product:
            o.match_status, o.match_confidence, o.variant_id = "not_phone", None, None
            stats["not_phone"] += 1
            continue
        if p.storage_gb is None:  # plan rule: no storage size, no auto-match (cannot tell the variants apart)
            o.match_status, o.match_confidence, o.variant_id = "no_storage", None, None
            stats["no_storage"] += 1
            continue
        model, conf = cat.find(p)
        if model is None:
            o.match_status, o.match_confidence, o.variant_id = "review", conf or None, None
            stats["review"] += 1
            continue
        rams = splits.get(_split_key(model, p))
        if rams and p.ram_gb not in rams:  # the title does not say which RAM size it is: cannot tell the two phones apart
            o.match_status, o.match_confidence, o.variant_id = "review", conf, None
            stats["review"] += 1
            continue
        o.variant_id = cat.variant(model, p, p.ram_gb if rams else None).id
        o.match_status, o.match_confidence = "matched", conf
        stats["matched"] += 1
    return stats


def propose_catalog(s: Session) -> list[tuple[str, str, int]]:
    """Distinct (brand, family) seen in offers, with counts, for a human to approve into catalog.csv."""
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for o in s.scalars(select(Offer)):
        p = parse_title(o.raw_title)
        if p.is_product and p.brand:
            counts[(p.brand, p.family)] += 1
    return sorted(((b, f, n) for (b, f), n in counts.items()), key=lambda x: (x[0], x[1]))


def grow_catalog(s: Session, csv_path: Path, min_shops: int = 2) -> int:
    """Append families seen in the review queue WITH a storage size to catalog.csv (column 'shops' = evidence)."""
    have = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            have.add((row["brand"], row["family"]))
    # Evidence is counted per model ignoring the 4G/5G tag, so "G77" (one shop) and "G77 5G" (another) count together.
    shops_by_model: dict[tuple[str, str], set[int]] = defaultdict(set)
    spellings: dict[tuple[str, str], set[str]] = defaultdict(set)
    for o in s.scalars(select(Offer).where(Offer.match_status == "review")):
        p = parse_title(o.raw_title)
        if p.is_product and p.brand and p.storage_gb is not None:
            key = (p.brand, re.sub(r"\s+", " ", re.sub(r"\b[45]g\b", "", p.family)).strip())
            shops_by_model[key].add(o.store_id)
            spellings[key].add(p.family)
    rows = []
    for key, shops in sorted(shops_by_model.items()):
        if len(shops) < min_shops:  # one shop's spelling alone is not evidence of a real model
            continue
        tagged = sorted(f for f in spellings[key] if re.search(r"\b[45]g\b", f))
        # Several tagged spellings (A17 4G and A17 5G) are different phones; one tagged spelling is the canonical name.
        for fam in tagged or sorted(spellings[key]):
            if (key[0], fam) not in have:
                rows.append([key[0], fam, len(shops)])
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(rows)
    return len(rows)
