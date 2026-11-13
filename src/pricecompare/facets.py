"""Filter values for one product, the same for the website and the app.

Each product gets a small dict of filter group -> value, built only from what we already know for sure (the matched
storage and RAM, and the processor, screen and graphics written in the product's own name). A product without a value
for a group simply does not show under that group's choices. The clients count the values to build the choices, so
the filters only ever offer what is really on the list.
"""
from __future__ import annotations

import re

# shown in this order; the clients know the group titles in both languages
GROUPS = {
    "phone": ["brand", "storage"],      # RAM is known for too few phones to filter by it fairly
    "tablet": ["brand", "storage"],
    "laptop": ["brand", "chip", "ram", "storage", "screen", "gpu"],
    "tv": ["brand", "size"],
}

_CHIPS = [   # first match wins; the label is the same in Arabic and English (people search these words in English)
    (re.compile(r"\b(celeron|pentium|athlon)\b|\bintel\s*n\d{2,4}\b|\bi3-n\d{3}\b", re.I), "Celeron / N"),
    (re.compile(r"\bcore\s*ultra\s*([579])\b|\bultra\s*([579])\s*\d{3}", re.I), "Core Ultra {}"),
    (re.compile(r"\bcore\s*i([3579])\b|\bi([3579])-\d{4,5}", re.I), "Core i{}"),
    (re.compile(r"\bcore\s*([3579])\b", re.I), "Core {}"),
    (re.compile(r"\bryzen(?:\s*ai)?(?:\s*max\+?)?\s*([3579])\b|\bryzen([3579])-", re.I), "Ryzen {}"),
    (re.compile(r"\b(m[1-5])\b|\b(a18)\s*pro\b", re.I), "Apple"),
    (re.compile(r"\bsnapdragon\b", re.I), "Snapdragon"),
]
_SCREEN = re.compile(r"(?<![\d.])(1[1-8])(?:\.\d)?\s*(?:\"|″|''|”|-?\s*inch)", re.I)
_GPU = re.compile(r"\b(rtx|gtx)\s*\d{4}|\bradeon\s*rx\s*\d{4}|\barc\s*a\d{3}m?\b", re.I)


def size_text(gb: int) -> str:
    return f"{gb // 1024}TB" if gb >= 1024 and gb % 1024 == 0 else f"{gb}GB"


def chip(name: str) -> str | None:
    for rx, label in _CHIPS:
        m = rx.search(name)
        if m:
            n = next((g for g in m.groups() if g), "")
            return label.format(n) if "{}" in label else label
    return None


def screen(name: str) -> str | None:
    m = _SCREEN.search(name)
    if not m:
        return None
    n = int(m.group(1))
    return '13-14"' if n <= 14 else ('15-16"' if n <= 16 else '17-18"')


def of(v: dict) -> dict:
    """The filter values of one product summary (needs category, brand, model, storage_gb, ram_gb)."""
    cat, name = v.get("category"), v.get("model") or ""
    f: dict[str, str] = {"brand": v["brand"]}
    if cat == "tv":
        if v.get("storage_gb"):
            f["size"] = f'{v["storage_gb"]}"'
        return f
    if v.get("storage_gb"):
        f["storage"] = size_text(v["storage_gb"])
    if cat == "laptop":
        if v.get("ram_gb"):
            f["ram"] = f"{v['ram_gb']}GB"
        for key, value in (("chip", chip(name)), ("screen", screen(name))):
            if value:
                f[key] = value
        f["gpu"] = "card" if _GPU.search(name) else "built-in"
    return f
