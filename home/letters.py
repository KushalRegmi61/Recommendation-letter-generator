"""Pure letter-generation helpers: context, template selection, rendering, export.

Nothing here touches ``request``. Views in ``home/views.py`` supply an
``Application`` and a template choice; everything below is testable in isolation.
"""

import datetime
import io
import os
import re
from types import SimpleNamespace

import fpdf as _fpdf_module
from docx import Document
from fpdf import FPDF

from django.conf import settings
from django.db.models import Q
from jinja2 import TemplateError, TemplateSyntaxError, meta
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

# python-docx rejects NULL and C0 control characters outright; strip them
# rather than 500 on text a professor pasted from another document.
# Tab (\x09), newline (\x0a) and carriage return (\x0d) are legal XML and kept.
_DOCX_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def join_subjects(parts):
    """Render a subject list as prose: "A", "A and B", "A, B and C"."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# --- Phase C: guided template editor -------------------------------------

# The single source of truth mapping a professor-friendly label to the Jinja
# expression inserted inside {{ }}. Every row's top-level name (the part before
# the first '.', '|', '[' or space) MUST be a key returned by
# build_letter_context / sample_context; a test enforces this so the palette can
# never offer a variable that does not exist.
FIELDS = [
    ("Student name",            "app.name",                     "Student"),
    ("First name",              "firstname",                    "Student"),
    ("Program",                 "app.std.program.program_name", "Student"),
    ("Department",              "app.std.department.dept_name", "Student"),
    ("Ranking percentile",      "app.ranking_percentile",       "Student"),
    ("Relationship",            "rel_desc",                     "Student"),
    ("GPA",                     "academics.gpa",                "Academics & Quality"),
    ("Standout quality",        "quality.quality",              "Academics & Quality"),
    ("Recommendation strength", "strength_phrase",              "Academics & Quality"),
    ("Subjects (sentence)",     "subjects_sentence",            "Academics & Quality"),
    ("Subject",                 "subject",                      "Academics & Quality"),
    ("Teacher name",            "teacher.name",                 "Teacher"),
    ("Teacher email",           "teacher.email",                "Teacher"),
    ("Teacher title",           "teacher.title",                "Teacher"),
    ("Teacher phone",           "teacher.phone",                "Teacher"),
    ("Pronoun (he/she)",        "pronoun",                      "Pronouns & Dates"),
    ("Pronoun (him/her)",       "pronoun_obj",                  "Pronouns & Dates"),
    ("Pronoun (his/her)",       "pronoun_pos",                  "Pronouns & Dates"),
    ("Today's date",            "today",                        "Pronouns & Dates"),
    ("Deadline",                "deadline",                     "Pronouns & Dates"),
]


def _field_top_name(expr):
    """The top-level context name an expression depends on (``app.std.x`` -> ``app``)."""
    return re.split(r"[.\|\[ ]", expr.strip(), maxsplit=1)[0]


def grouped_fields():
    """``FIELDS`` grouped by group label, preserving first-seen order."""
    groups = {}
    for label, expr, group in FIELDS:
        groups.setdefault(group, []).append({"label": label, "expr": expr})
    return [{"group": g, "fields": items} for g, items in groups.items()]


def sample_context():
    """A dummy render context mirroring build_letter_context's keys, for previews.

    Uses ``SimpleNamespace`` stand-ins so the attribute access the templates use
    (``app.name``, ``app.std.program.program_name``, ``academics.gpa`` ...) resolves.
    Touches no database and exposes no real student.
    """
    program = SimpleNamespace(program_name="Computer Engineering")
    department = SimpleNamespace(dept_name="Electronics & Computer Engineering")
    std = SimpleNamespace(program=program, department=department, gender="female")
    app = SimpleNamespace(
        name="Asmita Sharma", std=std,
        relationship_type="project supervisor", ranking_percentile="top 3%",
    )
    academics = SimpleNamespace(gpa="3.82", final_percentage="", tentative_ranking="Top 5%")
    teacher = SimpleNamespace(
        name="Dr. Rajesh Koirala", email="rajesh@pcampus.edu.np",
        title="Professor", phone="+977-1-5555555",
    )
    quality = SimpleNamespace(
        quality="a meticulous and endlessly curious engineer",
        recommendation_strength="top5",
        leadership=True, hardworking=True, social=False, teamwork=True, friendly=True,
        presentation="excellent", recommend="strongly",
    )
    paper = SimpleNamespace(paper_title="On-Device ML", paper_link="https://example.org/p")
    project = SimpleNamespace(supervised_project="Autonomous rover",
                              final_project="", deployed=True)
    university = SimpleNamespace(uni_name="ETH Zurich", country="Switzerland",
                                 program_applied="MSc CS", uni_deadline=None)
    files = SimpleNamespace()
    parts = ["Data Structures", "Operating Systems", "Machine Learning"]
    return {
        "student": app, "app": app,
        "subjects": parts[:-1], "subject": parts[-1] if parts else "",
        "value": len(parts) == 1,
        "subjects_sentence": join_subjects(parts),
        "firstname": "Asmita",
        "paper": paper, "project": project, "university": university,
        "quality": quality, "academics": academics, "files": files,
        "teacher": teacher,
        "pronoun": "She", "pronoun_obj": "her", "pronoun_pos": "Her",
        "rel_desc": "project supervisor",
        "strength_phrase": STRENGTH_PHRASES["top5"],
        "deadline": "December 15, 2026",
        "today": datetime.date.today().strftime("%B %d, %Y"),
    }


def validate_template(source):
    """Check a template string. Returns ``(errors, warnings)``.

    A non-empty ``errors`` list must block the save. Errors are unbalanced or
    otherwise invalid Jinja tags (``TemplateSyntaxError``). Warnings are
    variable names the render context does not provide -- Jinja renders those
    as empty, so they are surfaced but never block the save.
    """
    source = source or ""
    errors, warnings = [], []
    try:
        ast = _JINJA.parse(source)
    except TemplateSyntaxError as exc:
        errors.append(f"Template syntax error on line {exc.lineno}: {exc.message}")
        return errors, warnings
    allowed = set(sample_context().keys())
    for name in sorted(meta.find_undeclared_variables(ast)):
        if name not in allowed:
            warnings.append(f'Unknown field "{name}" — it will render empty.')
    return errors, warnings


def render_source(source, context):
    """Render an unsaved template string against ``context``.

    Unlike ``render_letter`` (which swallows errors for saved templates), this
    lets ``TemplateError`` propagate so the preview endpoint can report it.
    """
    return _JINJA.from_string(source).render(context)


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


def build_docx_bytes(letter_text):
    """Render ``letter_text`` to .docx bytes, one paragraph per blank-line block."""
    document = Document()
    for block in letter_text.split("\n\n"):
        document.add_paragraph(_DOCX_ILLEGAL.sub("", block))
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# fpdf's core fonts are Latin-1 only, which turns a non-Latin name into "???".
# A TrueType font registered with uni=True embeds a subset and handles Unicode.
# DejaVu Sans covers Latin (incl. accents), Greek and Cyrillic, plus punctuation
# such as em dashes and curly quotes. It does NOT cover Devanagari - see README.
_UNICODE_FONT_PATH = os.path.join(
    settings.BASE_DIR, "static", "fonts", "dejavu", "DejaVuSans.ttf"
)
_UNICODE_FONT_FAMILY = "DejaVu"

# ``add_font(uni=True)`` defaults to caching parsed font metrics as a ``.pkl``
# written next to the ``.ttf`` (FPDF_CACHE_MODE 0), which fails on a read-only
# deployment. Mode 2 would relocate it to FPDF_CACHE_DIR, but that reintroduces
# ``pickle.load`` from a shared temp directory - an arbitrary-code-execution
# sink if that directory is writable by anyone else. Mode 1 disables the cache
# outright: no writes, no unpickling, at the cost of re-parsing the TTF per
# document, which is a few milliseconds against a request that already renders
# a template and streams a file.
_fpdf_module.fpdf.FPDF_CACHE_MODE = 1


def build_pdf_bytes(letter_text):
    """Render ``letter_text`` to PDF bytes with a Unicode-capable font."""
    pdf = FPDF()
    pdf.add_page()
    if os.path.exists(_UNICODE_FONT_PATH):
        pdf.add_font(_UNICODE_FONT_FAMILY, "", _UNICODE_FONT_PATH, uni=True)
        pdf.set_font(_UNICODE_FONT_FAMILY, size=12)
        encode = lambda line: line
    else:
        # Degrade rather than fail if the font is missing from the deployment.
        pdf.set_font("Arial", size=12)
        encode = lambda line: line.encode("latin-1", "replace").decode("latin-1")
    for block in letter_text.split("\n\n"):
        for line in block.split("\n"):
            pdf.multi_cell(0, 10, encode(line))
        pdf.ln(5)
    output = pdf.output(dest="S")
    # fpdf1 returns str, fpdf2 returns bytes/bytearray. fpdf1 holds the whole
    # document - embedded font subset included - as a latin-1 "binary string"
    # and does exactly this encode itself when writing to a file, so it is
    # lossless here and cannot raise, even with a TTF embedded.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
