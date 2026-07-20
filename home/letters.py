"""Pure letter-generation helpers: context, template selection, rendering, export.

Nothing here touches ``request``. Views in ``home/views.py`` supply an
``Application`` and a template choice; everything below is testable in isolation.
"""

import datetime

PRONOUNS = {
    "male": ("He", "him", "His"),
    "female": ("She", "her", "Her"),
}
DEFAULT_PRONOUNS = ("They", "them", "Their")

# ``recommendation_strength`` is a choices field; each value becomes an
# adverbial phrase that completes "I recommend them ___."
STRENGTH_PHRASES = {
    "top5": "as one of the very best students I have taught",
    "top10": "as one of the strongest students I have taught",
    "outstanding": "in the strongest possible terms",
    "strong": "with great enthusiasm",
}
DEFAULT_STRENGTH_PHRASE = "with great enthusiasm"


def join_subjects(parts):
    """Render a subject list as prose: "A", "A and B", "A, B and C"."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def build_letter_context(application):
    """Assemble the dict every letter template renders against."""
    from home.models import (
        Academics, Files, Paper, Project, Qualities, University,
    )

    def first(model):
        # Every Jinja template guards its fields with ``{% if %}``, so a
        # missing satellite row is rendered as an omitted paragraph rather
        # than an error. Hence ``.first()`` and not ``.get()``.
        return model.objects.filter(application=application).first()

    university = first(University)
    quality = first(Qualities)
    gender = (application.std.gender or "").lower()
    pronoun, pronoun_obj, pronoun_pos = PRONOUNS.get(gender, DEFAULT_PRONOUNS)

    # One normalisation for all three keys: the legacy views derived them
    # separately and disagreed on whether empty segments counted.
    parts = [s.strip() for s in (application.subjects or "").split(",") if s.strip()]

    name = application.name or ""
    return {
        # Two aliases for the application: legacy templates use both.
        "student": application,
        "app": application,
        "subjects": parts[:-1],
        "subject": parts[-1] if parts else "",
        "value": len(parts) == 1,
        # "A, B and C" - the seeded templates want a sentence, not a CSV dump.
        "subjects_sentence": join_subjects(parts),
        "firstname": (name.split() or [""])[0],
        "paper": first(Paper),
        "project": first(Project),
        "university": university,
        "quality": quality,
        "academics": first(Academics),
        "files": first(Files),
        "teacher": application.professor,
        "pronoun": pronoun,
        "pronoun_obj": pronoun_obj,
        "pronoun_pos": pronoun_pos,
        # Students describe the relationship themselves ("instructor",
        # "project supervisor"); fall back to the generic term when unset.
        "rel_desc": (application.relationship_type or "").strip() or "teacher",
        "strength_phrase": STRENGTH_PHRASES.get(
            (quality.recommendation_strength or "") if quality else "",
            DEFAULT_STRENGTH_PHRASE,
        ),
        "deadline": (
            university.uni_deadline.strftime("%B %d, %Y")
            if university and university.uni_deadline else ""
        ),
        "today": datetime.date.today().strftime("%B %d, %Y"),
    }
