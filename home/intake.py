"""Testable helpers for the student intake flow (FR-2).

The large studentform views call these instead of duplicating logic.
"""


def compose_full_name(first, middle, last):
    """Join first/middle/last into a single display name, skipping blanks."""
    parts = [p.strip() for p in (first, middle, last) if p and p.strip()]
    return " ".join(parts)
