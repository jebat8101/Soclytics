"""Helpers for Light/Medium/Deep caps.

Deep may be unlimited (`None` / `<= 0`), which means collect until the
scraper idle-stops, then optionally filter by date range.
"""
from __future__ import annotations


def normalize_cap(value) -> int | None:
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return None if n <= 0 else n


def has_room(count: int, cap: int | None) -> bool:
    return cap is None or int(count) < int(cap)


def take_cap(items: list, cap: int | None) -> list:
    if cap is None:
        return list(items)
    return list(items)[: int(cap)]


def cap_label(cap: int | None) -> str:
    return 'unlimited' if cap is None else str(cap)
