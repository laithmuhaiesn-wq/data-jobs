"""Persist raw offers: upsert, price history only on change, run log."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .collectors.shopify import RawOffer
from .db.models import CollectionRun, Offer, PriceObservation, Source, Store


def ensure_store(s: Session, slug: str, name: str, site_url: str, method: str, terms_rating: str) -> Store:
    st = s.scalar(select(Store).where(Store.slug == slug))
    if st is None:
        st = Store(slug=slug, name=name, site_url=site_url)
        s.add(st)
        s.flush()
        s.add(Source(store_id=st.id, method=method, terms_rating=terms_rating))
        s.flush()
    return st


def fit_id(external_id: str, limit: int = 200) -> str:
    """The shop's product id, shortened to the column size when a shop uses a very long page name as the id.
    The tail is replaced by a short fingerprint of the whole id, so two long ids never collide and the same
    product always gets the same shortened id."""
    if len(external_id) <= limit:
        return external_id
    mark = hashlib.sha1(external_id.encode("utf-8")).hexdigest()[:16]
    return external_id[: limit - 17] + "-" + mark


def fit_offers(offers: list[RawOffer]) -> list[RawOffer]:
    """Makes every text fit its database column, so one odd product can never fail a whole shop."""
    out = []
    for ro in offers:
        if len(ro.url) > 500:  # a link cannot be shortened without breaking it: leave this one product out
            continue
        ro.external_id = fit_id(ro.external_id)
        ro.title = ro.title[:300]
        if ro.image_url and len(ro.image_url) > 500:
            ro.image_url = None
        out.append(ro)
    return out


def save_offers(s: Session, store: Store, offers: list[RawOffer], run: CollectionRun) -> None:
    now = datetime.now(timezone.utc)
    offers = fit_offers(offers)
    existing = {o.external_id: o for o in s.scalars(select(Offer).where(Offer.store_id == store.id))}
    for ro in offers:
        o = existing.get(ro.external_id)
        if o is None:
            o = Offer(store_id=store.id, external_id=ro.external_id, raw_title=ro.title, url=ro.url,
                      price_jod=ro.price_jod, in_stock=ro.in_stock, image_url=ro.image_url or None, last_checked=now, last_price_change=now)
            s.add(o)
            s.flush()
            s.add(PriceObservation(offer_id=o.id, price_jod=ro.price_jod, in_stock=ro.in_stock, observed_at=now))
            run.items_changed += 1
        else:
            o.last_checked = now
            o.raw_title, o.url = ro.title, ro.url
            if ro.image_url:
                o.image_url = ro.image_url
            if o.price_jod != ro.price_jod or o.in_stock != ro.in_stock:
                o.price_jod, o.in_stock, o.last_price_change = ro.price_jod, ro.in_stock, now
                s.add(PriceObservation(offer_id=o.id, price_jod=ro.price_jod, in_stock=ro.in_stock, observed_at=now))
                run.items_changed += 1
    run.items_seen = len(offers)
