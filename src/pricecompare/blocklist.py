"""Pictures we never show (third-party watermarks, wrong product, shop asked us to stop).

Each entry is a piece of the picture address; any candidate containing it is dropped. Add a line, push, done.
Use a shop's domain (e.g. "iservicejo.com/") to drop all of that shop's pictures at once.
"""
BLOCKED_PICTURES = (
    "iphone-16-finish-select-202409-6-1inch",  # iService iPhone 16 (all colours): GSMArena watermark (2026-11-09)
)


def is_blocked(url: str) -> bool:
    low = url.lower()
    return any(b.lower() in low for b in BLOCKED_PICTURES)
