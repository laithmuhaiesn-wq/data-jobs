"""Product specifications (plan step 2b.5).

Rule: specifications come only from the manufacturer's own page, are checked by hand, and are never invented. Every
entry in `specs.json` (next to this file) names the page it was read from (`source`, on the manufacturer's own site) and the day it
was checked (`checked`). A field the page does not state is simply left out; the site and app show nothing for it.
Values are short and in our own wording (facts only, nothing copied beyond the numbers and names).

Storage and RAM are not in the file: they come from the product itself (the version the shops sell).
"""
from __future__ import annotations

import json
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

SPECS_FILE = Path(__file__).with_name("specs.json")  # inside the package, so the server's pip install ships it

# (key, English label, Arabic label), in the order they are shown
FIELDS = {
    "phone": [("display", "Screen", "الشاشة"), ("chip", "Processor", "المعالج"), ("rear_camera", "Rear camera", "الكاميرا الخلفية"),
              ("front_camera", "Front camera", "الكاميرا الأمامية"), ("battery", "Battery", "البطارية"),
              ("charging", "Charging", "الشحن"), ("weight", "Weight", "الوزن"), ("os", "System", "النظام")],
    "laptop": [("processor", "Processor", "المعالج"), ("graphics", "Graphics", "كرت الشاشة"), ("display", "Screen", "الشاشة"),
               ("battery", "Battery", "البطارية"), ("weight", "Weight", "الوزن"), ("os", "System", "النظام")],
}
FIELDS["tablet"] = FIELDS["phone"]
FIELDS["tv"] = [("display", "Screen", "الشاشة"), ("resolution", "Resolution", "الدقة"), ("refresh", "Refresh rate", "معدل التحديث"),
                ("os", "System", "النظام"), ("weight", "Weight", "الوزن")]
OWN_FIELDS = [("storage", "Storage", "التخزين"), ("ram", "RAM", "الذاكرة (RAM)")]  # from the product itself

# manufacturers' own sites only (a spec page anywhere else is not accepted)
MAKER_SITES = ("apple.com", "samsung.com", "mi.com", "xiaomi.com", "honor.com", "huawei.com", "infinixmobility.com",
               "motorola.com", "oppo.com", "realme.com", "tecno-mobile.com", "asus.com", "lenovo.com", "hp.com",
               "dell.com", "acer.com", "msi.com", "nothing.tech", "vivo.com", "oneplus.com", "google.com", "nokia.com",
               "zte.com.cn", "ztedevices.com", "itel-life.com", "microsoft.com", "gigabyte.com", "razer.com")


def key(brand: str, family: str) -> str:
    return f"{brand}|{family}"


def problems(entries: dict) -> list[str]:
    """Everything wrong with the specs file; the tests require an empty list."""
    out = []
    known = {k for fields in FIELDS.values() for k, _, _ in fields}
    for k, e in entries.items():
        if k.startswith("_"):
            continue
        if not re.fullmatch(r"[A-Z][\w-]*\|[a-z0-9 .\-+]+", k):
            out.append(f"{k}: key must be 'Brand|family'")
        host = urlparse(e.get("source", "")).netloc.lower()
        if not e.get("source", "").startswith("https://") or not any(host == d or host.endswith("." + d) for d in MAKER_SITES):
            out.append(f"{k}: source must be the manufacturer's own https page")
        try:
            if date.fromisoformat(e.get("checked", "")) > date.today():
                out.append(f"{k}: checked date is in the future")
        except ValueError:
            out.append(f"{k}: checked must be YYYY-MM-DD")
        fields = {f for f in e if f not in ("source", "checked")}
        if fields - known:
            out.append(f"{k}: unknown fields {sorted(fields - known)}")
        if not fields:
            out.append(f"{k}: no specifications")
        for f in fields & known:
            if not isinstance(e[f], str) or not e[f].strip() or len(e[f]) > 80:
                out.append(f"{k}: {f} must be a short text")
    return out


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict:
    p = Path(path) if path else SPECS_FILE
    if not p.exists():
        return {}
    entries = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in entries.items() if not k.startswith("_")}


def storage_text(gb: int | None) -> str | None:
    if not gb:
        return None
    return f"{gb // 1024} TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb} GB"


def specs_for(brand: str, family: str, category: str, storage_gb: int | None, ram_gb: int | None,
              entries: dict | None = None) -> dict:
    """{"rows": [[key, en, ar, value], ...], "source": url|None, "checked": date|None}. Only stated facts; never guessed."""
    e = (entries if entries is not None else load()).get(key(brand, family), {})
    rows = []
    if category == "tv":  # a TV's size field holds its screen size (TVs have no storage)
        rows.append(["screen_size", "Screen size", "حجم الشاشة", f'{storage_gb} inch'] if storage_gb else [])
        rows = [r for r in rows if r]
    else:
        own = {"storage": storage_text(storage_gb), "ram": f"{ram_gb} GB" if ram_gb else None}
        for k, en, ar in OWN_FIELDS:
            if own[k]:
                rows.append([k, en, ar, own[k]])
    for k, en, ar in FIELDS.get(category, []):
        if e.get(k):
            rows.append([k, en, ar, e[k]])
    return {"rows": rows, "source": e.get("source"), "checked": e.get("checked")}
