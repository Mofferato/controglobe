"""Historical years: negative is BCE, and there is no year 0."""

from __future__ import annotations


def iter_years(start: int, end: int):
    for y in range(start, end + 1):
        if y != 0:
            yield y


def label(year: int) -> str:
    return f"{-year} BCE" if year < 0 else f"{year}"


def long_label(year: int) -> str:
    return f"{-year} BCE" if year < 0 else f"{year} CE"


def parse(value: str) -> int:
    """Accept '-500', '500 BCE', '500BC', '1776', '1776 CE'."""
    s = str(value).strip().upper().replace(".", "")
    for suffix in ("BCE", "BC"):
        if s.endswith(suffix):
            return -int(s[: -len(suffix)].strip())
    for suffix in ("CE", "AD"):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    y = int(s)
    if y == 0:
        raise ValueError("there is no year 0: use -1 (1 BCE) or 1 (1 CE)")
    return y
