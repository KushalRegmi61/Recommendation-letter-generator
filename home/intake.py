"""Testable helpers for the student intake flow (FR-2).

The large studentform views call these instead of duplicating logic.
"""


def compose_full_name(first, middle, last):
    """Join first/middle/last into a single display name, skipping blanks."""
    parts = [p.strip() for p in (first, middle, last) if p and p.strip()]
    return " ".join(parts)


def has_pending_application(student, professor):
    """True if a not-yet-generated application already links this pair.

    Implements the diagram's 'Check Duplicate Submission'. A generated
    letter (is_generated=True) does not block a fresh request.
    """
    from home.models import Application
    return Application.objects.filter(
        std=student, professor=professor, is_generated=False,
    ).exists()
