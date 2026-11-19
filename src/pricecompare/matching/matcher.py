"""Link offers to catalog phone variants.

Auto-match only when brand + model family + storage all agree (plan rule). Anything else goes
to the review queue. Market versions stay separate variants so they never mix in best price.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import Brand, Offer, PhoneModel, PhoneVariant
from .parse import category_of, ParsedTitle, parse_title

AUTO = 0.9
SAME_PRICE = 0.12  # two spellings are one phone only if their prices agree this closely (see Catalog)
# merges decided by price are remembered: afterwards one spelling has no listings of its own left to compare
ALIASES_FILE = Path.home() / '.derbani' / 'catalog_aliases.json'


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
        # One phone written two ways: "galaxy s26 ultra" and "galaxy s26 ultra 5g" (the S26 Ultra only comes as 5G) were
        # two catalog entries, so the same phone showed twice (2026-11-18). When a model has ONE tagged spelling, the
        # tagged and the untagged entries are the same phone: both names lead to the older entry (its address and price
        # history were published first). A17 4G and A17 5G (two tags) stay different phones, as before.
        # A name alone is not proof ("Spark 40" is a 4G phone, "Spark 40 5G" another one): the two entries are merged only
        # when their prices agree too (within SAME_PRICE for every storage size both have, at least one shared size).
        prices: dict[tuple[int, int], list[float]] = defaultdict(list)
        for model_id, storage, price in s.execute(
                select(PhoneVariant.model_id, PhoneVariant.storage_gb, Offer.price_jod)
                .join(Offer, Offer.variant_id == PhoneVariant.id).where(Offer.in_stock.is_(True), Offer.match_status == "matched")):
            if storage:
                prices[(model_id, storage)].append(float(price))

        def same_phone(a: PhoneModel, b: PhoneModel) -> bool:
            shared = {st for (mid, st) in prices if mid == a.id} & {st for (mid, st) in prices if mid == b.id}
            if not shared:
                return False
            for st in shared:
                pa, pb = statistics.median(prices[(a.id, st)]), statistics.median(prices[(b.id, st)])
                if abs(pa - pb) > SAME_PRICE * min(pa, pb):
                    return False
            return True

        try:
            aliases: dict[str, str] = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            aliases = {}
        name = lambda m: f"{brands[m.brand_id]}:{m.family}"  # noqa: E731
        learned = False
        for group in list(self.loose.values()):
            tags = {t.group(0) for m in group if (t := re.search(r"\b[45]g\b", m.family))}
            if len(group) < 2 or len(tags) > 1:
                continue
            keep = min(group, key=lambda m: m.id)
            known = all(aliases.get(name(m)) == name(keep) for m in group)
            if not known:
                if not all(same_phone(a, b) for a in group for b in group if a.id < b.id):
                    continue
                aliases.update({name(m): name(keep) for m in group})
                learned = True
            for m in group:
                self.exact[name(m)] = keep
            self.loose[ParsedTitle(brands[keep.brand_id], keep.family, None, None, "", "", True).family_key_no_net] = [keep]
        if learned:
            try:
                ALIASES_FILE.parent.mkdir(parents=True, exist_ok=True)
                ALIASES_FILE.write_text(json.dumps(aliases, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
            except OSError:
                pass

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
        if not p.is_product or p.storage_gb is None or not p.ram_gb or p.category not in ("phone", "tablet"):
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


# A title without a size ("HONOR X7d 4G Silver") is matched only when every other shop sells that model in one
# size and this shop's price is within 20% of theirs: then it can only be that phone. Marked by this confidence so
# the rule never feeds itself; it is checked again on every run.
SINGLE_CONF = 0.74
SINGLE_SPREAD = 0.20


def single_sizes(s: Session) -> dict[int, tuple[PhoneVariant, list[tuple[int, float]]]]:
    """model id -> (its only sold variant, (shop, price) of each shop selling it), for models sold in one size."""
    prices: dict[int, list[tuple[int, float]]] = defaultdict(list)
    from datetime import datetime, timedelta, timezone
    recent = datetime.now(timezone.utc) - timedelta(days=2)
    for vid, store, price, conf, seen in s.execute(select(Offer.variant_id, Offer.store_id, Offer.price_jod, Offer.match_confidence,
                                                          Offer.last_checked).where(
            Offer.match_status == "matched", Offer.in_stock.is_(True), Offer.variant_id.is_not(None))):
        if conf != SINGLE_CONF and (seen if seen.tzinfo else seen.replace(tzinfo=timezone.utc)) >= recent:
            prices[vid].append((store, float(price)))
    per_model: dict[int, list[PhoneVariant]] = defaultdict(list)
    for v in s.scalars(select(PhoneVariant).where(PhoneVariant.id.in_(list(prices)))):
        per_model[v.model_id].append(v)
    out = {}
    for mid, vs in per_model.items():
        if len(vs) == 1:
            out[mid] = (vs[0], prices[vs[0].id])
    return out


def variant_splits(s: Session) -> dict[tuple, set[int]]:
    """The RAM splits already made (they are sticky): read from the catalogue alone, without any listing titles."""
    out: dict[tuple, set[int]] = defaultdict(set)
    for v in s.scalars(select(PhoneVariant).where(PhoneVariant.ram_gb.is_not(None))):
        out[(v.model_id, v.storage_gb, v.connectivity, v.market_version)].add(v.ram_gb)
    return dict(out)


def match_offers(s: Session, only_unmatched: bool = True, new_only: bool = False) -> dict[str, int]:
    """new_only (after each shop collection): only listings that are new or whose title changed are read. Reading
    every listing again (new reader rules, new RAM splits, the review queue) is the nightly run's job: done after
    every collection it sent most of Neon's free monthly data allowance (2026-11-17)."""
    cat = Catalog(s)
    splits = variant_splits(s) if new_only else ram_splits(s, cat)
    single = single_sizes(s)
    stats = {"matched": 0, "review": 0, "no_storage": 0, "not_phone": 0}
    family_of = dict(s.execute(select(PhoneModel.id, PhoneModel.family)).all())
    model_of = {vid: (mid, gb) for vid, mid, gb in s.execute(select(PhoneVariant.id, PhoneVariant.model_id, PhoneVariant.storage_gb))}
    for o in s.scalars(select(Offer).where(Offer.match_status == "unmatched") if new_only else select(Offer)):
        p = parse_title(o.raw_title)
        released = o.match_status == "matched" and (not p.is_product or p.storage_gb is None)
        if o.match_status == "matched" and not released and o.variant_id is not None:
            now_model = cat.find(p)[0]
            # the reader now reads it as another product, or a product we do not have: matched again from scratch
            was = model_of.get(o.variant_id)
            if now_model is not None and was is not None:
                released = (now_model.id, p.storage_gb) != was                # another product, or another size of it
            elif was is not None:
                # now read as another kind ("PS5 Compatible" SSD), or as a product our own readers name differently
                # ("Odyssey G6" became "FG600"); a phone or tablet is never let go on a name it cannot find
                released = p.category != category_of(family_of[was[0]]) or p.category not in ("phone", "tablet")
        # "not_phone" is read again too: a reader that learns a new spelling or brand must pick up old listings
        if only_unmatched and o.match_status not in ("unmatched", "review", "no_storage", "not_phone") and not released:
            # an offer matched earlier is left alone, unless its phone has since been split by RAM, or the reader no
            # longer trusts its title (no product or no storage size any more): then it is taken back below
            model = cat.find(p)[0] if o.match_status == "matched" and p.is_product and p.storage_gb is not None else None
            if model is None or _split_key(model, p) not in splits:
                continue
        if not p.is_product:
            o.match_status, o.match_confidence, o.variant_id = "not_phone", None, None
            stats["not_phone"] += 1
            continue
        if p.storage_gb is None:  # plan rule: no storage size, no auto-match (cannot tell the variants apart)
            model = cat.find(p)[0] if p.category in ("phone", "tablet", "watch") else None
            only = single.get(model.id) if model is not None else None
            others = sorted(price for store, price in (only[1] if only else []) if store != o.store_id)   # never its own price
            mid = others[len(others) // 2] if others else None
            if mid and p.connectivity in ("unknown", only[0].connectivity) and abs(float(o.price_jod) - mid) <= SINGLE_SPREAD * mid:
                o.variant_id, o.match_status, o.match_confidence = only[0].id, "matched", SINGLE_CONF
                stats["matched"] += 1
                continue
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
        # a laptop's RAM is always part of the product (8GB and 16GB are different machines at different prices)
        ram = p.ram_gb if (rams or p.category in ("laptop", "desktop")) else None
        o.variant_id = cat.variant(model, p, ram).id
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
