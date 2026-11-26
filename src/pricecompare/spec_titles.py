"""Specifications read from the shops' own product names (owner 2026-11-26: fill specs for every product).

A fact is used only when at least two different shops state the same value in their product names and no other value
is stated as often. One shop alone is never enough (a shop's name can be wrong). Facts from the maker's page
(specs.json) always win; these only fill fields the maker data leaves empty, and the site and app mark them.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

MIN_SHOPS = 2


def _num(x: str) -> str:
    return x.rstrip("0").rstrip(".") if "." in x else x


def _processor(t: str) -> str | None:
    m = re.search(r"\bcore\s+ultra\s+([579])\s+(\d{3}[a-z]{0,2})\b", t)
    if m:
        return f"Intel Core Ultra {m[1]} {m[2].upper()}"
    m = re.search(r"\b(?:intel\s+)?(?:core\s+)?i([3579])[\s-]+(\d{4,5}[a-z]{0,2})\b", t)
    if m:
        return f"Intel Core i{m[1]}-{m[2].upper()}"
    m = re.search(r"\bcore\s+([357])\s+(\d{3}[a-z]{0,2})\b", t)
    if m:
        return f"Intel Core {m[1]} {m[2].upper()}"
    m = re.search(r"\bryzen\s+(?:ai\s+)?([3579])\s+(?:pro\s+)?(\d{3,4}[a-z]{0,2})\b", t)
    if m:
        return f"AMD Ryzen {m[1]} {m[2].upper()}"
    m = re.search(r"\bsnapdragon\s+x\s*(elite|plus)?\b", t)
    if m:
        return "Snapdragon X" + (f" {m[1].capitalize()}" if m[1] else "")
    m = re.search(r"\b(?:apple\s+)?m([1-5])\s*(pro|max)?\s+chip\b|\bapple\s+m([1-5])\b\s*(pro|max)?", t)
    if m:
        n, extra = m[1] or m[3], m[2] or m[4]
        return f"Apple M{n}" + (f" {extra.capitalize()}" if extra else "")
    return None


def _graphics(t: str) -> str | None:
    m = re.search(r"\b(rtx|gtx)\s*(\d{4})\s*(ti)?\b", t)
    if m:
        return f"NVIDIA GeForce {m[1].upper()} {m[2]}" + (" Ti" if m[3] else "")
    m = re.search(r"\bradeon\s+rx\s*(\d{4}[a-z]{0,2})\b|\brx\s*(\d{4}(?:xt|xtx|m|s)?)\b", t)
    if m:
        return f"AMD Radeon RX {(m[1] or m[2]).upper()}"
    return None


def _chip(t: str) -> str | None:
    m = re.search(r"\bsnapdragon\s+(8\s*(?:\+\s*)?(?:gen\s*\d|elite)|\d{3})\b", t)
    if m:
        return "Snapdragon " + re.sub(r"\s+", " ", m[1].replace("gen", "Gen ").replace("elite", "Elite")).replace("Gen  ", "Gen ").strip()
    m = re.search(r"\b(helio\s+[gpx]\d{2,3}|dimensity\s+\d{3,4}|exynos\s+\d{4}|unisoc\s+t\d{3,4}|kirin\s+\d{3,4}[a-z]?)\b", t)
    if m:
        w = m[1].split()
        return f"{w[0].capitalize()} {w[1].upper()}"
    m = re.search(r"\ba(1[4-9])\s+(pro|bionic)\b", t)
    if m:
        return f"Apple A{m[1]}" + (" Pro" if m[2] == "pro" else "")
    return None


def _screen(t: str) -> str | None:
    m = re.search(r"\b(\d{1,2}(?:\.\d)?)\s*(?:\"|”|''|-?\s*inch(?:es)?\b|in\b)", t)
    if m and 5 <= float(m[1]) <= 34:
        return f'{_num(m[1])} inch'
    return None


def _battery(t: str) -> str | None:
    m = re.search(r"\b(\d{1,2},?\d{3})\s*mah\b", t)
    if m:
        return f"{m[1].replace(',', '')} mAh"
    m = re.search(r"\b(\d{2,3}(?:\.\d)?)\s*wh\b", t)
    return f"{_num(m[1])} Wh" if m else None


def _refresh(t: str) -> str | None:
    m = re.search(r"\b(\d{2,3})\s*hz\b", t)
    return f"{m[1]} Hz" if m and 50 <= int(m[1]) <= 540 else None


def _resolution(t: str) -> str | None:
    if re.search(r"\b8k\b", t):
        return "8K"
    if re.search(r"\b(4k|uhd|3840\s*x\s*2160)\b", t):
        return "4K (3840 × 2160)"
    if re.search(r"\b(qhd|wqhd|2k|2560\s*x\s*1440)\b", t):
        return "QHD (2560 × 1440)"
    if re.search(r"\b(fhd|full\s*hd|1080p|1920\s*x\s*1080)\b", t):
        return "Full HD (1920 × 1080)"
    return None


def _panel(t: str) -> str | None:
    m = re.search(r"\b(qd-?oled|oled|ips|va|tn)\b", t)
    return {"qdoled": "QD-OLED", "qd-oled": "QD-OLED"}.get(m[1], m[1].upper()) if m else None


def _response(t: str) -> str | None:
    m = re.search(r"\b(\d(?:\.\d{1,2})?)\s*ms\b", t)
    return f"{_num(m[1])} ms" if m else None


def _water(t: str) -> str | None:
    m = re.search(r"\b(ip[x]?\d{1,2})\b", t)
    if m:
        return m[1].upper().replace("IPX", "IPX")
    m = re.search(r"\b(\d{1,2})\s*atm\b", t)
    return f"{m[1]} ATM" if m else None


def _bluetooth(t: str) -> str | None:
    m = re.search(r"\b(?:bluetooth|bt)\s*v?(\d\.\d)\b", t)
    return f"Bluetooth {m[1]}" if m else None


def _watts(t: str) -> str | None:
    m = re.search(r"\b(\d{2,4})\s*w\b", t)
    return f"{m[1]} W" if m and int(m[1]) >= 5 else None


def _wifi(t: str) -> str | None:
    m = re.search(r"\bwi-?fi\s*(7|6e|6|5)\b", t)
    if m:
        return f"Wi-Fi {m[1].upper()}"
    m = re.search(r"\b(be|ax|ac)\s*(\d{4,5})\b", t)
    return f"{m[1].upper()}{m[2]}" if m else None


def _mbps(t: str) -> str | None:
    m = re.search(r"\b(\d{3,5})\s*mbps\b", t)
    return f"{m[1]} Mbps" if m else None


def _storage_type(t: str) -> str | None:
    for word, name in (("nvme", "NVMe SSD"), ("ssd", "SSD"), ("hdd", "Hard disk"), ("hard drive", "Hard disk"),
                       ("flash", "USB flash drive"), ("microsd", "microSD card"), ("micro sd", "microSD card")):
        if re.search(rf"\b{word}\b", t):
            return name
    return None


def _readspeed(t: str) -> str | None:
    m = re.search(r"\b(\d{3,5})\s*mb/?s\b", t)
    return f"{m[1]} MB/s" if m else None


def _lumens(t: str) -> str | None:
    m = re.search(r"\b(\d{1,2},?\d{3}|\d{3})\s*(?:ansi\s*)?lumens?\b", t)
    return f"{m[1].replace(',', '')} lumens" if m else None


def _dpi(t: str) -> str | None:
    m = re.search(r"\b(\d{1,2},?\d{3}|\d{1,2}k)\s*dpi\b", t)
    if not m:
        return None
    v = m[1].replace(",", "")
    return f"{int(v[:-1]) * 1000 if v.endswith('k') else int(v)} DPI"


def _ppm(t: str) -> str | None:
    m = re.search(r"\b(\d{1,3})\s*ppm\b", t)
    return f"{m[1]} pages/min" if m else None


def _os(t: str) -> str | None:
    m = re.search(r"\bwin(?:dows)?\s*1([01])\s*(home|pro)?\b", t)
    if m:
        return f"Windows 1{m[1]}" + (f" {m[2].capitalize()}" if m[2] else "")
    return "FreeDOS" if re.search(r"\b(free\s*dos|dos)\b", t) else None


# field -> reader, per category; only fields the category shows (specs.FIELDS) are filled
READERS = {
    "laptop": {"processor": _processor, "graphics": _graphics, "display": _screen, "battery": _battery, "os": _os},
    "desktop": {"processor": _processor, "graphics": _graphics, "os": _os},
    "phone": {"chip": _chip, "battery": _battery},
    "tablet": {"chip": _chip, "display": _screen, "battery": _battery},
    "tv": {"resolution": _resolution, "refresh": _refresh},
    "monitor": {"resolution": _resolution, "refresh": _refresh, "panel": _panel, "response": _response},
    "watch": {"water": _water},
    "audio": {"battery": _battery, "connection": _bluetooth},
    "speaker": {"power": _watts, "battery": _battery, "water": _water, "connection": _bluetooth},
    "powerbank": {"output": _watts},
    "router": {"wifi": _wifi, "speed": _mbps},
    "storage": {"type": _storage_type, "speed": _readspeed},
    "printer": {"speed": _ppm},
    "camera": {"video": lambda t: "4K" if re.search(r"\b4k\b", t) else None},
    "projector": {"resolution": _resolution, "brightness": _lumens},
    "peripheral": {"dpi": _dpi, "connection": _bluetooth},
}


def facts(category: str | None, titles: list[tuple[object, str]]) -> dict[str, str]:
    """{field: value} that at least MIN_SHOPS shops agree on. titles: (shop id, product name) pairs."""
    readers = READERS.get(category or "", {})
    if not readers:
        return {}
    seen: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for shop, title in titles:
        t = " " + re.sub(r"\s+", " ", (title or "").lower().replace("×", "x")) + " "
        for field, read in readers.items():
            v = read(t)
            if v:
                seen[field][v].add(shop)
    out = {}
    for field, values in seen.items():
        ranked = Counter({v: len(shops) for v, shops in values.items()}).most_common(2)
        if ranked[0][1] >= MIN_SHOPS and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
            out[field] = ranked[0][0]
    return out
