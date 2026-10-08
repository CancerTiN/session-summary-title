#!/usr/bin/env python3
"""Validate a session title as exactly twelve Han characters."""

from __future__ import annotations

import sys
import unicodedata


def is_han(character: str) -> bool:
    if len(character) != 1:
        return False
    # Unicode names exclude unassigned gaps and cover newer CJK extensions.
    return unicodedata.name(character, "").startswith((
        "CJK UNIFIED IDEOGRAPH-", "CJK COMPATIBILITY IDEOGRAPH-",
    ))


def validate_title(title: str) -> None:
    if len(title) == 12 and all(is_han(character) for character in title):
        return
    han_count = sum(is_han(character) for character in title)
    raise ValueError(
        "expected exactly 12 Han characters with no other characters; "
        f"got {len(title)} characters ({han_count} Han characters)"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 scripts/validate_title.py '<title>'")
        return 2

    try:
        validate_title(sys.argv[1])
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
