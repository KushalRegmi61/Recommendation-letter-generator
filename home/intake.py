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


def parse_universities(names, countries, deadlines, programs):
    """Turn the form's parallel lists into cleaned university row dicts.

    Rows whose university name is blank are dropped. A blank deadline
    becomes None so it is a valid value for University.uni_deadline
    (a nullable DateField). Ragged lists are tolerated via index guards.
    """
    def at(seq, i):
        return seq[i] if i < len(seq) else ""

    rows = []
    for i, raw_name in enumerate(names):
        name = (raw_name or "").strip()
        if not name:
            continue
        deadline = (at(deadlines, i) or "").strip()
        rows.append({
            "uni_name": name,
            "country": (at(countries, i) or "").strip(),
            "uni_deadline": deadline or None,
            "program_applied": (at(programs, i) or "").strip(),
        })
    return rows
