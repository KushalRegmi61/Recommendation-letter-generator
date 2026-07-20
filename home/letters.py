"""Pure letter-generation helpers: context, template selection, rendering, export.

Nothing here touches ``request``. Views in ``home/views.py`` supply an
``Application`` and a template choice; everything below is testable in isolation.
"""

import datetime

from django.db.models import Q
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment

# Professors author these templates themselves, so the renderer is sandboxed:
# plain ``jinja2.Template`` allows ``__class__``/``__subclasses__`` walking,
# which is the standard springboard to running code as the web user.
_JINJA = SandboxedEnvironment()


def visible_to(teacher):
    """Q matching the templates ``teacher`` may use: their own, plus shared ones.

    A system template is by definition *unowned* - that is what migration 0013
    seeds. Matching on ``is_system`` alone would let a row that is both owned
    and flagged system leak from its owner to every other professor.
    """
    return Q(professor=teacher) | Q(professor__isnull=True, is_system=True)


def system_templates():
    """The shared, unowned starter library."""
    from home.models import CustomTemplates

    return CustomTemplates.objects.filter(professor__isnull=True, is_system=True)

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


def select_template(teacher, template_id=None):
    """Resolve which template to render for ``teacher``.

    ``template_id`` arrives straight from POST data, so it may be ``None``, an
    empty string, or junk. Anything unusable falls through to the professor's
    default rather than raising.
    """
    from home.models import CustomTemplates

    try:
        pk = int(template_id)
    except (TypeError, ValueError):
        pk = None

    if pk is not None:
        # A professor may pick their own template or any shared system one,
        # never another professor's.
        chosen = CustomTemplates.objects.filter(pk=pk).filter(
            visible_to(teacher)
        ).first()
        if chosen:
            return chosen

    # ``professor=teacher`` is load-bearing: without it a colleague's default
    # at a lower pk would be returned instead of this professor's.
    default = CustomTemplates.objects.filter(
        professor=teacher, is_default=True
    ).first()
    if default:
        return default

    return system_templates().order_by("template_name").first()


def render_letter(application, template_obj):
    """Render ``template_obj`` against ``application``. No template -> empty text.

    Professors author these templates by hand, so a saved template may be
    malformed or reference a field that does not exist. A broken template
    renders as empty text rather than raising, matching the convention that a
    missing row is an omitted paragraph and never a 500.
    """
    if not template_obj or not template_obj.template:
        return ""
    try:
        return _JINJA.from_string(template_obj.template).render(
            build_letter_context(application)
        )
    except TemplateError:
        # Covers syntax errors, undefined attributes and sandbox violations,
        # which all subclass ``TemplateError``.
        return ""


def available_templates(teacher):
    """Every template ``teacher`` may generate from: theirs plus system ones."""
    from home.models import CustomTemplates

    # No ``.distinct()`` needed, unlike ``filters.py``: both arms of the OR test
    # columns on this table only, so Django emits a bare WHERE with no join and
    # cannot return a row twice.
    return CustomTemplates.objects.filter(visible_to(teacher)).order_by(
        "-is_default", "is_system", "template_name"
    )
