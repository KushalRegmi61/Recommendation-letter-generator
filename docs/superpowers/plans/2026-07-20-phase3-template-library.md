# Phase 3: Template Library and Letter Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give professors a library of seeded system templates plus their own custom ones, let them pick which template a letter is generated from, and make the export path record `generated_at` / `generated_template` / `generated_letter` so the Phase 2 dashboard shows real data.

**Architecture:** Extract the ~150 lines of letter-context building, template selection, and PDF/DOCX production that are currently duplicated between `renderCustom` and `download_letter` into a new pure module `home/letters.py` (mirroring the Phase 2 `filters.py` / `dashboard.py` split). `CustomTemplates` gains a nullable `professor` and an `is_system` flag; a data migration seeds three ASCII-only Jinja templates. Template selection moves from name-string matching to primary-key matching and is threaded end-to-end: `formTeacher.html` -> `renderCustom` -> `test2.html` -> `download_letter`, which stamps the FR-5 fields.

**Tech Stack:** Django 5.1, Python 3.12, SQLite, Jinja2, `fpdf`, `python-docx`, Django `TestCase`.

---

## Environment notes for every task

- `python` is NOT on PATH. Always use `venv/bin/python`.
- Run tests with `venv/bin/python manage.py test home.tests.<ClassName> -v2`.
- **Run only the test classes your task touches.** Do not run the whole suite after each task; the full suite runs once at final review. This is a hard project rule.
- Never add `Co-Authored-By`, `Generated with Claude Code`, or any AI attribution to commits.
- Never `git add CLAUDE.md` (it is gitignored and must stay untracked).
- Existing suite: 73 tests in `home/tests.py`, 13 classes. Add new classes at the end of the file; put any new imports at the top with the existing imports.

## Test fixture requirements (applies to EVERY task below)

Several models have non-nullable FKs. The `setUp` blocks written inline in the tasks below are
abbreviated; **every one of them must satisfy these required fields** or you get an
`IntegrityError` instead of the failure the step predicts:

- `TeacherInfo` requires `department` (FK, non-null).
- `StudentLoginInfo` requires `department`, `program`, `password`, and `dob` in addition to
  `username` and `roll_number`.
- `Program` requires `department`.

Use this canonical preamble at the top of each new test class's `setUp`, matching the pattern
already used by `ApplicationFilterTests` (`home/tests.py:304`):

```python
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
```

then pass `department=self.dept` to every `TeacherInfo.objects.create(...)`, and
`department=self.dept, program=self.program, password="x", dob="2000-01-01"` to every
`StudentLoginInfo.objects.create(...)`.

**`db.sqlite3` is tracked but is NOT committed with migrations.** Phase 1's migration commit
(`0ea7aac`) left it out, and the README instructs users to run `migrate`. Running `migrate`
will dirty your working tree; leave `db.sqlite3` uncommitted, and never `git add` it.

## Constraints discovered by inspection (do not violate)

1. **PDF export encodes latin-1** (`views.py:2094`, `pdf.output(dest='S').encode('latin1')`). Every seeded template MUST be pure ASCII. No em dashes, no curly quotes, no ellipsis characters. Use `-`, `"`, `...`. Fixing latin-1 is explicitly out of scope for this phase.
2. **CSRF middleware is disabled project-wide.** New POST forms inherit this. Do not add CSRF-dependent logic.
3. **Teacher identity is the client-controlled `unique` cookie.** There is no `request.user` check on teacher views. Keep guarding with `TeacherInfo.objects.filter(unique_id=unique).exists()` and redirect to `/loginTeacher` when absent, matching `views.py:teacher()`.
4. `CustomTemplates.professor` is currently `on_delete=CASCADE` and non-null. Making it nullable must keep CASCADE for professor-owned rows.

---

## File Structure

| File | Responsibility |
|---|---|
| `home/letters.py` (**new**) | Pure functions: build the Jinja render context for an application, select a template, render it, and produce PDF/DOCX bytes. No HTTP, no `request`. |
| `home/migrations/0012_system_templates.py` (**new**) | Schema: `CustomTemplates.professor` nullable, add `is_system`. |
| `home/migrations/0013_seed_system_templates.py` (**new**) | Data: insert three ASCII system templates; reversible. |
| `home/models.py` (modify) | The two `CustomTemplates` field changes. |
| `home/views.py` (modify) | `renderCustom`, `template`, `download_letter` rewritten to call `home/letters.py`; new `duplicate_template` view. |
| `home/urls.py` (modify) | Route for `duplicate_template`. |
| `templates/formTeacher.html` (modify) | Template picker posts `template_id` (pk), grouped system vs mine. |
| `templates/test2.html` (modify) | Fix the orphaned textarea; carry `template_id` through to download. |
| `templates/customTemplate.html` (modify) | List system templates with a "Duplicate to my templates" button. |
| `home/tests.py` (modify) | New test classes appended. |
| `README.md` (modify) | Document the template library. |

---

## Task 1: Model fields for system templates

**Files:**
- Modify: `home/models.py:238-248`
- Create: `home/migrations/0012_system_templates.py` (generated)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class SystemTemplateModelTests(TestCase):
    """CustomTemplates must support shared system templates (FR-1)."""

    def test_a_system_template_needs_no_professor(self):
        tpl = CustomTemplates.objects.create(
            template_name="Formal / Academic",
            template="Dear Committee,",
            professor=None,
            is_system=True,
        )
        self.assertIsNone(tpl.professor)
        self.assertTrue(tpl.is_system)

    def test_professor_templates_are_not_system_by_default(self):
        teacher = TeacherInfo.objects.create(name="Prof A", unique_id="T-A")
        tpl = CustomTemplates.objects.create(
            template_name="Mine", template="Hello", professor=teacher
        )
        self.assertFalse(tpl.is_system)

    def test_str_does_not_crash_without_a_professor(self):
        tpl = CustomTemplates.objects.create(
            template_name="Formal", template="x", professor=None, is_system=True
        )
        self.assertIn("Formal", str(tpl))
```

Ensure `CustomTemplates` and `TeacherInfo` are imported at the top of `home/tests.py` (the file already imports from `home.models`; add them to that import if missing).

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.SystemTemplateModelTests -v2`
Expected: FAIL — `TypeError: CustomTemplates() got unexpected keyword arguments: 'is_system'`.

- [ ] **Step 3: Change the model**

Replace `home/models.py:238-248` entirely with:

```python
class CustomTemplates(models.Model):
    template_name = models.CharField(max_length=100, null=True, blank=True)
    template = models.TextField(null=True, blank=True)
    # System templates are shared by every professor and have no owner.
    professor = models.ForeignKey(
        TeacherInfo, on_delete=CASCADE, null=True, blank=True
    )
    is_default = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    def __str__(self):
        owner = self.professor or "System"
        return f"{owner} - {self.template_name or 'Untitled'} Template"

    class Meta:
        db_table = 'Template'
```

- [ ] **Step 4: Generate and apply the migration**

```bash
venv/bin/python manage.py makemigrations home --name system_templates
venv/bin/python manage.py migrate home
```

Expected: creates `home/migrations/0012_system_templates.py` with `AlterField` on `professor` and `AddField` for `is_system`; migrate reports `OK`.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.SystemTemplateModelTests -v2`
Expected: `OK` (3 tests).

- [ ] **Step 6: Commit**

```bash
git add home/models.py home/migrations/0012_system_templates.py home/tests.py
git commit -m "feat(templates): allow shared system templates without an owner"
```

---

## Task 2: Seed three system templates

**Files:**
- Create: `home/migrations/0013_seed_system_templates.py`
- Test: `home/tests.py`

**Why a data migration:** every deployment (including the committed `db.sqlite3`) needs the same starting library, and the three hardcoded copies of a default letter currently living in `views.py:1633`, `views.py:1994`, and `views.py:2133` become dead once real templates exist.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class SeededSystemTemplateTests(TestCase):
    """The data migration must ship a usable starter library (FR-1)."""

    def test_three_system_templates_are_seeded(self):
        seeded = CustomTemplates.objects.filter(is_system=True)
        self.assertEqual(seeded.count(), 3)

    def test_seeded_templates_have_names_and_bodies(self):
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                self.assertTrue(tpl.template_name)
                self.assertGreater(len(tpl.template), 100)
                self.assertIsNone(tpl.professor)
                self.assertFalse(tpl.is_default)

    def test_seeded_templates_are_ascii_only(self):
        # The PDF export encodes latin-1; a stray em dash crashes the download.
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                tpl.template.encode("ascii")

    def test_seeded_templates_are_valid_jinja(self):
        from jinja2 import Template
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                Template(tpl.template)  # raises TemplateSyntaxError if malformed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.SeededSystemTemplateTests -v2`
Expected: FAIL — `AssertionError: 0 != 3`.

- [ ] **Step 3: Write the data migration**

Create `home/migrations/0013_seed_system_templates.py`:

```python
from django.db import migrations

FORMAL = """{{ today }}

To Whom It May Concern

Re: Letter of Recommendation for {{ app.name }}

It is my pleasure to recommend {{ app.name }}, a student of the
{{ app.std.program.program_name }} program in the Department of
{{ app.std.department.dept_name }} at the Institute of Engineering,
Pulchowk Campus, Tribhuvan University.

I have known {{ app.name }} as {{ pronoun_pos|lower }} {{ rel_desc }}{% if app.subjects %},
having taught {{ pronoun_obj|lower }} in {{ app.subjects }}{% endif %}.
{% if academics.gpa %}{{ pronoun }} has maintained a GPA of {{ academics.gpa }}{% if app.ranking_percentile %},
placing {{ pronoun_obj|lower }} within the top {{ app.ranking_percentile }} percent of the cohort{% endif %}.
{% endif %}
{% if quality.quality %}{{ pronoun }} is, above all, {{ quality.quality }}.
{% endif %}{% if app.prof_anecdote %}{{ app.prof_anecdote }}
{% endif %}
I recommend {{ pronoun_obj|lower }} {{ strength_phrase }} and without reservation.

Sincerely,
{{ teacher.name }}
{{ teacher.email }}
Institute of Engineering, Pulchowk Campus
"""

RESEARCH = """{{ today }}

{% if university.uni_name %}Admissions Committee
{% if university.program_applied %}{{ university.program_applied }} Program
{% endif %}{{ university.uni_name }}
{% else %}To Whom It May Concern
{% endif %}
Re: Graduate Application of {{ app.name }}

I write in strong support of {{ app.name }}'s application
{% if university.program_applied %}to the {{ university.program_applied }} program{% endif %}
{% if university.uni_name %}at {{ university.uni_name }}{% endif %}.

{{ pronoun }} completed {{ pronoun_pos|lower }} undergraduate studies in
{{ app.std.department.dept_name }} at the Institute of Engineering, Pulchowk Campus,
where I served as {{ pronoun_pos|lower }} {{ rel_desc }}.

{% if app.is_paper and paper.paper_title %}{{ pronoun }} authored "{{ paper.paper_title }}",
which speaks directly to {{ pronoun_pos|lower }} readiness for independent research.
{% endif %}{% if project.project_title %}{{ pronoun }} also led a project titled
"{{ project.project_title }}".
{% endif %}
{% if academics.gpa %}Academically {{ pronoun|lower }} holds a GPA of {{ academics.gpa }}{% if academics.tentative_ranking %},
ranked {{ academics.tentative_ranking }}{% if app.class_size %} of {{ app.class_size }}{% endif %}{% endif %}.
{% endif %}
{% if deadline %}I understand the application deadline is {{ deadline }}.
{% endif %}I recommend {{ pronoun_obj|lower }} {{ strength_phrase }} for admission.

Sincerely,
{{ teacher.name }}
{{ teacher.email }}
"""

GENERAL = """{{ today }}

To Whom It May Concern

I am glad to recommend {{ app.name }}, whom I have known as
{{ pronoun_pos|lower }} {{ rel_desc }} at the Institute of Engineering,
Pulchowk Campus, Tribhuvan University.

{% if app.subjects %}I taught {{ pronoun_obj|lower }} in {{ app.subjects }}.
{% endif %}{% if academics.gpa %}{{ pronoun }} has maintained a GPA of {{ academics.gpa }}.
{% endif %}
{% if quality.leadership %}{{ pronoun }} shows genuine leadership.
{% endif %}{% if quality.hardworking %}{{ pronoun }} is consistently hardworking.
{% endif %}{% if quality.teamwork %}{{ pronoun }} works well within a team.
{% endif %}{% if quality.friendly %}{{ pronoun }} is approachable and well liked by peers.
{% endif %}
{% if quality.recommend %}{{ quality.recommend }}
{% endif %}
I recommend {{ pronoun_obj|lower }} {{ strength_phrase }}.

Sincerely,
{{ teacher.name }}
{{ teacher.email }}
"""

SEEDS = (
    ("Formal / Academic", FORMAL),
    ("Research / Graduate School", RESEARCH),
    ("General Purpose", GENERAL),
)


def seed(apps, schema_editor):
    CustomTemplates = apps.get_model("home", "CustomTemplates")
    for name, body in SEEDS:
        CustomTemplates.objects.update_or_create(
            template_name=name,
            is_system=True,
            defaults={"template": body, "professor": None, "is_default": False},
        )


def unseed(apps, schema_editor):
    CustomTemplates = apps.get_model("home", "CustomTemplates")
    CustomTemplates.objects.filter(
        is_system=True, template_name__in=[name for name, _ in SEEDS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0012_system_templates"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
```

- [ ] **Step 4: Apply the migration**

```bash
venv/bin/python manage.py migrate home
```

Expected: `Applying home.0013_seed_system_templates... OK`.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.SeededSystemTemplateTests -v2`
Expected: `OK` (4 tests).

- [ ] **Step 6: Verify the migration reverses cleanly**

```bash
venv/bin/python manage.py migrate home 0012 && venv/bin/python manage.py migrate home
```

Expected: both directions report `OK`, no traceback.

- [ ] **Step 7: Commit**

```bash
git add home/migrations/0013_seed_system_templates.py home/tests.py
git commit -m "feat(templates): seed three shared system letter templates"
```

---

## Task 3: Extract the letter render context into `home/letters.py`

**Files:**
- Create: `home/letters.py`
- Test: `home/tests.py`

**Why:** `renderCustom` (`views.py:1560-1729`) and `download_letter` (`views.py:1942-2100`) each rebuild the same context by hand, and the two copies have already drifted. One tested function replaces both.

Note the related objects are all `.get()` today, which raises `DoesNotExist` when a satellite row is missing. Use `.filter(...).first()` so a partially-filled application still renders — the Jinja templates already guard every field with `{% if %}`.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class LetterContextTests(TestCase):
    """build_letter_context assembles everything the Jinja templates read."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof B", unique_id="T-B")
        self.student = StudentLoginInfo.objects.create(
            roll_number="080BCT042", username="Ramesh Shrestha",
            email="r@example.com", gender="Male",
        )
        self.application = Application.objects.create(
            name="Ramesh Shrestha", std=self.student, professor=self.teacher,
            subjects="Data Structures,Algorithms",
        )

    def test_pronouns_follow_the_student_gender(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["pronoun"], "He")
        self.assertEqual(ctx["pronoun_obj"], "him")
        self.assertEqual(ctx["pronoun_pos"], "His")

    def test_unknown_gender_falls_back_to_they(self):
        from home.letters import build_letter_context
        self.student.gender = ""
        self.student.save()
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["pronoun"], "They")
        self.assertEqual(ctx["pronoun_obj"], "them")

    def test_subjects_are_split_into_list_and_last(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["subjects"], ["Data Structures"])
        self.assertEqual(ctx["subject"], "Algorithms")

    def test_single_subject_sets_value_true(self):
        from home.letters import build_letter_context
        self.application.subjects = "Algorithms"
        self.application.save()
        ctx = build_letter_context(self.application)
        self.assertTrue(ctx["value"])

    def test_firstname_is_the_first_word(self):
        from home.letters import build_letter_context
        self.assertEqual(build_letter_context(self.application)["firstname"], "Ramesh")

    def test_missing_satellite_rows_do_not_raise(self):
        # No Paper/Project/University/Qualities/Academics/Files rows exist.
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        for key in ("paper", "project", "university", "quality", "academics", "files"):
            with self.subTest(key=key):
                self.assertIsNone(ctx[key])
        self.assertEqual(ctx["deadline"], "")

    def test_teacher_and_app_aliases_are_present(self):
        from home.letters import build_letter_context
        ctx = build_letter_context(self.application)
        self.assertEqual(ctx["teacher"], self.teacher)
        self.assertEqual(ctx["app"], self.application)
        self.assertEqual(ctx["student"], self.application)
        self.assertTrue(ctx["today"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.LetterContextTests -v2`
Expected: FAIL — `ModuleNotFoundError: No module named 'home.letters'`.

- [ ] **Step 3: Create `home/letters.py`**

```python
"""Pure letter-generation helpers: context, template selection, rendering, export.

Nothing here touches ``request``. Views in ``home/views.py`` supply an
``Application`` and a template choice; everything below is testable in isolation.
"""

import datetime
import io

from docx import Document
from fpdf import FPDF
from jinja2 import Template

# Every Jinja template guards its fields with ``{% if %}``, so a missing
# satellite row is rendered as an omitted paragraph rather than an error.
PRONOUNS = {
    "male": ("He", "him", "His"),
    "female": ("She", "her", "Her"),
}
DEFAULT_PRONOUNS = ("They", "them", "Their")


def build_letter_context(application):
    """Assemble the dict every letter template renders against."""
    from home.models import (
        Academics, Files, Paper, Project, Qualities, University,
    )

    def first(model):
        return model.objects.filter(application=application).first()

    university = first(University)
    gender = (application.std.gender or "").lower()
    pronoun, pronoun_obj, pronoun_pos = PRONOUNS.get(gender, DEFAULT_PRONOUNS)

    raw_subjects = (application.subjects or "").split(",")
    subjects = [s for s in raw_subjects[:-1] if s]
    subject = raw_subjects[-1] if raw_subjects else ""

    name = application.name or ""
    return {
        # Two aliases for the application: legacy templates use both.
        "student": application,
        "app": application,
        "subjects": subjects,
        "subject": subject,
        "value": len([s for s in raw_subjects if s]) == 1,
        "firstname": name.split(" ")[0] if name else "",
        "paper": first(Paper),
        "project": first(Project),
        "university": university,
        "quality": first(Qualities),
        "academics": first(Academics),
        "files": first(Files),
        "teacher": application.professor,
        "pronoun": pronoun,
        "pronoun_obj": pronoun_obj,
        "pronoun_pos": pronoun_pos,
        "rel_desc": "teacher",
        "strength_phrase": "with great enthusiasm",
        "deadline": (
            university.uni_deadline.strftime("%B %d, %Y")
            if university and university.uni_deadline else ""
        ),
        "today": datetime.date.today().strftime("%B %d, %Y"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.LetterContextTests -v2`
Expected: `OK` (7 tests).

- [ ] **Step 5: Commit**

```bash
git add home/letters.py home/tests.py
git commit -m "refactor(letters): extract the letter render context into one tested helper"
```

---

## Task 4: Template selection and rendering in `home/letters.py`

**Files:**
- Modify: `home/letters.py`
- Test: `home/tests.py`

**Selection rules**, in order — a professor's explicit pick wins, then their default, then the first system template:

1. If `template_id` names a template the professor may use (their own, or any system one), use it.
2. Otherwise use the professor's `is_default=True` template.
3. Otherwise use the first system template by name.
4. Otherwise `None` (caller renders nothing).

Selecting by **pk** rather than name is the change from the old code: two templates could share a name, and a rename silently fell through to the default.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class TemplateSelectionTests(TestCase):
    """select_template resolves a professor's pick, default, then system (FR-1)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof C", unique_id="T-C")
        self.other = TeacherInfo.objects.create(name="Prof D", unique_id="T-D")
        self.mine = CustomTemplates.objects.create(
            template_name="Mine", template="mine", professor=self.teacher
        )
        self.my_default = CustomTemplates.objects.create(
            template_name="My Default", template="default",
            professor=self.teacher, is_default=True,
        )
        self.theirs = CustomTemplates.objects.create(
            template_name="Theirs", template="theirs", professor=self.other
        )

    def test_an_explicit_own_template_wins(self):
        from home.letters import select_template
        self.assertEqual(select_template(self.teacher, self.mine.pk), self.mine)

    def test_a_system_template_may_be_selected(self):
        from home.letters import select_template
        system = CustomTemplates.objects.filter(is_system=True).first()
        self.assertEqual(select_template(self.teacher, system.pk), system)

    def test_another_professors_template_is_refused(self):
        from home.letters import select_template
        # Falls back to this professor's default rather than leaking Prof D's.
        self.assertEqual(select_template(self.teacher, self.theirs.pk), self.my_default)

    def test_no_choice_uses_the_professors_default(self):
        from home.letters import select_template
        self.assertEqual(select_template(self.teacher, None), self.my_default)

    def test_blank_and_malformed_ids_use_the_default(self):
        from home.letters import select_template
        for bad in ("", "   ", "abc", None, "0"):
            with self.subTest(value=bad):
                self.assertEqual(select_template(self.teacher, bad), self.my_default)

    def test_string_ids_from_post_data_work(self):
        from home.letters import select_template
        self.assertEqual(select_template(self.teacher, str(self.mine.pk)), self.mine)

    def test_without_a_default_it_falls_back_to_a_system_template(self):
        from home.letters import select_template
        CustomTemplates.objects.filter(professor=self.teacher).delete()
        chosen = select_template(self.teacher, None)
        self.assertTrue(chosen.is_system)


class RenderLetterTests(TestCase):
    """render_letter fills the chosen template with application data (FR-1)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof E", unique_id="T-E")
        self.student = StudentLoginInfo.objects.create(
            roll_number="080BCT001", username="Sita Rai",
            email="s@example.com", gender="Female",
        )
        self.application = Application.objects.create(
            name="Sita Rai", std=self.student, professor=self.teacher,
            subjects="Physics",
        )

    def test_the_chosen_template_body_is_used(self):
        from home.letters import render_letter
        tpl = CustomTemplates.objects.create(
            template_name="Terse", template="Hello {{ app.name }} from {{ teacher.name }}.",
            professor=self.teacher,
        )
        self.assertEqual(
            render_letter(self.application, tpl), "Hello Sita Rai from Prof E."
        )

    def test_pronouns_reach_the_template(self):
        from home.letters import render_letter
        tpl = CustomTemplates.objects.create(
            template_name="P", template="{{ pronoun }} and {{ pronoun_obj }}",
            professor=self.teacher,
        )
        self.assertEqual(render_letter(self.application, tpl), "She and her")

    def test_no_template_renders_empty(self):
        from home.letters import render_letter
        self.assertEqual(render_letter(self.application, None), "")

    def test_every_seeded_system_template_renders(self):
        from home.letters import render_letter
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = render_letter(self.application, tpl)
                self.assertIn("Sita Rai", letter)
                self.assertIn("Prof E", letter)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.TemplateSelectionTests home.tests.RenderLetterTests -v2`
Expected: FAIL — `ImportError: cannot import name 'select_template' from 'home.letters'`.

- [ ] **Step 3: Append to `home/letters.py`**

```python
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

    if pk:
        # A professor may pick their own template or any shared system one,
        # never another professor's.
        chosen = CustomTemplates.objects.filter(pk=pk).filter(
            Q(professor=teacher) | Q(is_system=True)
        ).first()
        if chosen:
            return chosen

    default = CustomTemplates.objects.filter(
        professor=teacher, is_default=True
    ).first()
    if default:
        return default

    return CustomTemplates.objects.filter(is_system=True).order_by("template_name").first()


def render_letter(application, template_obj):
    """Render ``template_obj`` against ``application``. No template -> empty text."""
    if not template_obj or not template_obj.template:
        return ""
    return Template(template_obj.template).render(build_letter_context(application))


def available_templates(teacher):
    """Every template ``teacher`` may generate from: theirs plus system ones."""
    from home.models import CustomTemplates

    return CustomTemplates.objects.filter(
        Q(professor=teacher) | Q(is_system=True)
    ).order_by("-is_default", "is_system", "template_name")
```

Add `from django.db.models import Q` to the imports at the top of `home/letters.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.TemplateSelectionTests home.tests.RenderLetterTests -v2`
Expected: `OK` (11 tests).

- [ ] **Step 5: Commit**

```bash
git add home/letters.py home/tests.py
git commit -m "feat(templates): select templates by id with a system fallback"
```

---

## Task 5: PDF and DOCX byte production in `home/letters.py`

**Files:**
- Modify: `home/letters.py`
- Test: `home/tests.py`

**Why extract:** Task 7 needs the exported file both as an HTTP response body *and* as bytes to save into `generated_letter`. Producing bytes once and reusing them avoids rendering twice.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class LetterExportTests(TestCase):
    """PDF/DOCX bytes are produced from letter text (FR-1)."""

    def test_pdf_bytes_look_like_a_pdf(self):
        from home.letters import build_pdf_bytes
        data = build_pdf_bytes("Dear Committee,\n\nRegards,\nProf")
        self.assertTrue(data.startswith(b"%PDF"))

    def test_docx_bytes_look_like_a_zip(self):
        # .docx is a zip container; PK is the zip magic number.
        from home.letters import build_docx_bytes
        data = build_docx_bytes("Dear Committee,\n\nRegards,\nProf")
        self.assertTrue(data.startswith(b"PK"))

    def test_docx_keeps_one_paragraph_per_block(self):
        from docx import Document
        from home.letters import build_docx_bytes
        import io
        data = build_docx_bytes("First block.\n\nSecond block.")
        doc = Document(io.BytesIO(data))
        texts = [p.text for p in doc.paragraphs]
        self.assertIn("First block.", texts)
        self.assertIn("Second block.", texts)

    def test_empty_text_still_produces_a_file(self):
        from home.letters import build_docx_bytes, build_pdf_bytes
        self.assertTrue(build_pdf_bytes("").startswith(b"%PDF"))
        self.assertTrue(build_docx_bytes("").startswith(b"PK"))

    def test_non_latin1_characters_are_replaced_not_crashed(self):
        # fpdf encodes latin-1; an em dash used to raise UnicodeEncodeError.
        from home.letters import build_pdf_bytes
        self.assertTrue(build_pdf_bytes("A — B").startswith(b"%PDF"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.LetterExportTests -v2`
Expected: FAIL — `ImportError: cannot import name 'build_pdf_bytes' from 'home.letters'`.

- [ ] **Step 3: Append to `home/letters.py`**

```python
def build_docx_bytes(letter_text):
    """Render ``letter_text`` to .docx bytes, one paragraph per blank-line block."""
    document = Document()
    for block in letter_text.split("\n\n"):
        document.add_paragraph(block)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def build_pdf_bytes(letter_text):
    """Render ``letter_text`` to PDF bytes.

    ``fpdf`` only speaks latin-1. Seeded templates are ASCII, but a professor
    may paste a curly quote into their own template, so unsupported characters
    are replaced rather than allowed to abort the download.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for block in letter_text.split("\n\n"):
        for line in block.split("\n"):
            safe = line.encode("latin-1", "replace").decode("latin-1")
            pdf.multi_cell(0, 10, safe)
        pdf.ln(5)
    output = pdf.output(dest="S")
    # fpdf1 returns str, fpdf2 returns bytes/bytearray.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.LetterExportTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add home/letters.py home/tests.py
git commit -m "feat(letters): produce pdf and docx bytes from one helper"
```

---

## Task 6: Rewrite `renderCustom` to use `home/letters.py`

**Files:**
- Modify: `home/views.py:1560-1729` (the whole `renderCustom` function)
- Modify: `templates/formTeacher.html:294-301`
- Test: `home/tests.py`

The picker currently posts `temp` (a name). It must post `template_id` (a pk), and the preview must forward that pk to the download step.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class RenderCustomViewTests(TestCase):
    """The preview renders the professor's chosen template (FR-1)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof F", unique_id="T-F")
        self.student = StudentLoginInfo.objects.create(
            roll_number="080BCT007", username="Hari Thapa",
            email="h@example.com", gender="Male",
        )
        self.application = Application.objects.create(
            name="Hari Thapa", std=self.student, professor=self.teacher,
            subjects="Networks",
        )
        Qualities.objects.create(application=self.application)
        self.chosen = CustomTemplates.objects.create(
            template_name="Chosen", template="CHOSEN for {{ app.name }}",
            professor=self.teacher,
        )
        self.fallback = CustomTemplates.objects.create(
            template_name="Fallback", template="FALLBACK", professor=self.teacher,
            is_default=True,
        )
        self.client.cookies["unique"] = "T-F"

    def test_the_selected_template_is_rendered(self):
        response = self.client.post("/renderCustom", {
            "roll": "080BCT007", "template_id": self.chosen.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CHOSEN for Hari Thapa")

    def test_without_a_selection_the_default_is_rendered(self):
        response = self.client.post("/renderCustom", {"roll": "080BCT007"})
        self.assertContains(response, "FALLBACK")

    def test_the_chosen_template_id_is_carried_into_the_download_form(self):
        response = self.client.post("/renderCustom", {
            "roll": "080BCT007", "template_id": self.chosen.pk,
        })
        self.assertContains(response, f'name="template_id" value="{self.chosen.pk}"')

    def test_the_professor_anecdote_is_still_saved(self):
        self.client.post("/renderCustom", {
            "roll": "080BCT007", "template_id": self.chosen.pk,
            "prof_anecdote": "He rebuilt the lab router overnight.",
        })
        self.application.refresh_from_db()
        self.assertEqual(
            self.application.prof_anecdote, "He rebuilt the lab router overnight."
        )

    def test_the_quality_checkboxes_are_still_saved(self):
        self.client.post("/renderCustom", {
            "roll": "080BCT007", "template_id": self.chosen.pk,
            "quality1": "on", "quality2": "on", "qual": "diligent",
        })
        quality = Qualities.objects.get(application=self.application)
        self.assertTrue(quality.leadership)
        self.assertTrue(quality.hardworking)
        self.assertFalse(quality.social)
        self.assertEqual(quality.quality, "diligent")

    def test_a_stale_cookie_redirects_to_login(self):
        self.client.cookies["unique"] = "NOPE"
        response = self.client.post("/renderCustom", {"roll": "080BCT007"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.RenderCustomViewTests -v2`
Expected: FAIL — the old view reads `temp`, so `CHOSEN for Hari Thapa` is absent and `template_id` is not in the response.

- [ ] **Step 3: Replace `renderCustom` in `home/views.py`**

Delete the entire existing `renderCustom` function (from `def renderCustom(request):` through the `return render(request, 'test2.html', ...)` line, roughly lines 1560-1729) and put this in its place:

```python
def renderCustom(request):
    """Preview a letter for one student from the professor's chosen template."""
    if request.method != "POST":
        return redirect("/teacher")

    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")

    roll = request.POST.get("roll")
    application = get_object_or_404(
        Application, std__roll_number=roll, professor__unique_id=unique
    )

    anecdote = request.POST.get("prof_anecdote")
    if anecdote is not None:
        application.prof_anecdote = anecdote
        application.save()

    Qualities.objects.filter(application=application).update(
        leadership=request.POST.get("quality1") == "on",
        hardworking=request.POST.get("quality2") == "on",
        social=request.POST.get("quality3") == "on",
        teamwork=request.POST.get("quality4") == "on",
        friendly=request.POST.get("quality5") == "on",
        quality=request.POST.get("qual"),
        presentation=request.POST.get("presentation"),
        recommend=request.POST.get("recommend"),
    )

    template_obj = select_template(application.professor, request.POST.get("template_id"))
    return render(request, "test2.html", {
        "letter": render_letter(application, template_obj),
        "student": application,
        # Carried into the download form so the export uses the same template.
        "template_id": template_obj.pk if template_obj else "",
    })
```

Add to the imports near `from home.dashboard import build_teacher_dashboard_context` (around line 113):

```python
from home.letters import (
    available_templates, build_docx_bytes, build_pdf_bytes,
    render_letter, select_template,
)
```

`get_object_or_404` is already imported (`views.py:4`) — no import change needed for it.

- [ ] **Step 4: Update the picker in `templates/formTeacher.html`**

Replace lines 294-301 with:

```html
<select name="template_id" id="template" required>
  {% for template in templates %}
  <option value="{{ template.pk }}" {% if default_template and template.pk == default_template.pk %}selected{% endif %}>
    {{ template.template_name }}{% if template.is_system %} (system){% endif %}
  </option>
  {% endfor %}
</select>
```

- [ ] **Step 5: Point `make_letter` at the full template list**

In `home/views.py`, in `make_letter`, replace these two lines (currently 432-433):

```python
        templates = CustomTemplates.objects.filter(professor = appli.professor)
        default_template = templates.filter(is_default=True).first()
```

with:

```python
        templates = available_templates(appli.professor)
        default_template = templates.filter(is_default=True).first()
```

`available_templates` returns a queryset, so the `.filter(is_default=True)` chain still works — and since system templates are never `is_default`, the default still resolves to one of the professor's own.

- [ ] **Step 6: Add the hidden field to `templates/test2.html`**

In each of the two forms (`#pdfForm` and `#docxForm`), directly after the existing `<input type="hidden" name="roll" ...>` line, add:

```html
        <input type="hidden" name="template_id" value="{{ template_id }}">
```

- [ ] **Step 7: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.RenderCustomViewTests -v2`
Expected: `OK` (6 tests).

- [ ] **Step 8: Commit**

```bash
git add home/views.py templates/formTeacher.html templates/test2.html home/tests.py
git commit -m "feat(letters): preview from the template the professor selects"
```

---

## Task 7: Rewrite `download_letter` to honour the selection, keep edits, and stamp FR-5

**Files:**
- Modify: `home/views.py:1942-2100` (the whole `download_letter` function)
- Modify: `templates/test2.html:15` (move the orphaned textarea)
- Test: `home/tests.py`

**Three defects being fixed here:**

1. The `edited_letter` textarea sits *outside* both forms (`test2.html:15`, forms start at `:17`), so it is never submitted and **every professor edit is silently discarded**. Move one copy inside each form.
2. `download_letter` never reads a template choice — it only tries `is_default` then the name `Default`, so the pick made on the preview screen is lost on export.
3. Nothing writes `generated_at`, `generated_template`, `generated_letter`, or `is_generated`, so the Phase 2 dashboard columns are permanently empty.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class DownloadLetterTests(TestCase):
    """Exporting a letter stores it and stamps the tracking fields (FR-1/FR-5)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof G", unique_id="T-G")
        self.student = StudentLoginInfo.objects.create(
            roll_number="080BCT099", username="Gita Kc",
            email="g@example.com", gender="Female",
        )
        self.application = Application.objects.create(
            name="Gita Kc", std=self.student, professor=self.teacher,
            subjects="Signals",
        )
        self.tpl = CustomTemplates.objects.create(
            template_name="Export", template="EXPORTED for {{ app.name }}",
            professor=self.teacher,
        )
        self.client.cookies["unique"] = "T-G"

    def _post(self, **extra):
        payload = {"roll": "080BCT099", "format": "pdf", "template_id": self.tpl.pk}
        payload.update(extra)
        return self.client.post("/download_letter/", payload)

    def test_pdf_download_returns_a_pdf(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("Gita Kc", response["Content-Disposition"])

    def test_docx_download_returns_a_docx(self):
        response = self._post(format="docx")
        self.assertEqual(response.status_code, 200)
        self.assertIn("wordprocessingml", response["Content-Type"])

    def test_generation_stamps_the_tracking_fields(self):
        self._post()
        self.application.refresh_from_db()
        self.assertTrue(self.application.is_generated)
        self.assertIsNotNone(self.application.generated_at)
        self.assertEqual(self.application.generated_template, self.tpl)
        self.assertTrue(self.application.generated_letter)

    def test_the_stored_file_is_the_downloaded_file(self):
        response = self._post()
        self.application.refresh_from_db()
        with self.application.generated_letter.open("rb") as handle:
            self.assertEqual(handle.read(), response.content)

    def test_edited_text_is_used_instead_of_the_template(self):
        response = self._post(format="docx", edited_letter="HAND WRITTEN VERSION")
        from docx import Document
        import io
        texts = [p.text for p in Document(io.BytesIO(response.content)).paragraphs]
        self.assertIn("HAND WRITTEN VERSION", texts)
        self.assertNotIn("EXPORTED for Gita Kc", texts)

    def test_regenerating_replaces_the_stored_file_and_timestamp(self):
        self._post()
        self.application.refresh_from_db()
        first_at = self.application.generated_at
        self._post(format="docx")
        self.application.refresh_from_db()
        self.assertGreaterEqual(self.application.generated_at, first_at)
        self.assertTrue(self.application.generated_letter.name.endswith(".docx"))

    def test_another_professor_cannot_export_this_letter(self):
        TeacherInfo.objects.create(name="Prof H", unique_id="T-H")
        self.client.cookies["unique"] = "T-H"
        self.assertEqual(self._post().status_code, 404)

    def test_a_stale_cookie_redirects_to_login(self):
        self.client.cookies["unique"] = "NOPE"
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])

    def test_an_unknown_format_is_rejected(self):
        self.assertEqual(self._post(format="txt").status_code, 400)

    def test_a_rejected_format_does_not_stamp_anything(self):
        self._post(format="txt")
        self.application.refresh_from_db()
        self.assertFalse(self.application.is_generated)
        self.assertIsNone(self.application.generated_at)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.DownloadLetterTests -v2`
Expected: FAIL — `generated_at` is `None` and `generated_letter` is empty; the ownership test returns 500 rather than 404.

- [ ] **Step 3: Replace `download_letter` in `home/views.py`**

Delete the entire existing `download_letter` function including its `@csrf_exempt` decorator (roughly lines 1941-2100) and put this in its place. **Keep `@csrf_exempt` attached** — it is a POST view and CSRF middleware being disabled today does not make the decorator safe to drop.

```python
@csrf_exempt
def download_letter(request):
    """Export a letter as PDF/DOCX, store a copy, and record the FR-5 tracking fields."""
    if request.method != "POST":
        return redirect("/teacher")

    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")

    file_format = request.POST.get("format")
    if file_format not in ("pdf", "docx"):
        # Reject before touching the database so a bad request stamps nothing.
        return HttpResponse("Invalid format", status=400)

    application = get_object_or_404(
        Application,
        std__roll_number=request.POST.get("roll"),
        professor__unique_id=unique,
    )
    template_obj = select_template(application.professor, request.POST.get("template_id"))

    # A professor may hand-edit the preview; their text wins over the template.
    edited_text = request.POST.get("edited_letter")
    letter_text = edited_text if edited_text else render_letter(application, template_obj)

    if file_format == "docx":
        payload = build_docx_bytes(letter_text)
        content_type = (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )
    else:
        payload = build_pdf_bytes(letter_text)
        content_type = "application/pdf"

    safe_name = slugify(application.name) or "letter"
    filename = f"Recommendation_{safe_name}.{file_format}"

    # FR-5: record what was generated so the dashboard can list and re-serve it.
    application.generated_letter.save(filename, ContentFile(payload), save=False)
    application.generated_template = template_obj
    application.generated_at = timezone.now()
    application.is_generated = True
    application.save()

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
```

Add these imports at the top of `home/views.py`, directly after `from django.shortcuts import ...` on line 4. None of the three is currently imported:

```python
from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify
```

`Q` is added here because Task 8 needs it too.

- [ ] **Step 4: Fix the orphaned textarea in `templates/test2.html`**

Delete line 15 (`<textarea id="edited_letter" name="edited_letter" style="display:none;"></textarea>`) and its preceding comment. Inside **each** of the two forms, after the `template_id` hidden input added in Task 6, add:

```html
        <textarea name="edited_letter" class="edited_letter" style="display:none;"></textarea>
```

Then replace the `prepareEdit` function in the `<script>` block with:

```javascript
    // Copy the edited letter into every form's hidden textarea before submitting.
    function prepareEdit() {
        var editable = document.getElementById('letter_editable');
        if (!editable) { return; }
        var fields = document.getElementsByClassName('edited_letter');
        for (var i = 0; i < fields.length; i++) {
            fields[i].value = editable.innerText;
        }
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.DownloadLetterTests -v2`
Expected: `OK` (10 tests).

- [ ] **Step 6: Confirm the Phase 2 re-download still works**

Run: `venv/bin/python manage.py test home.tests.DownloadGeneratedTests -v2`
Expected: `OK` (6 tests). These cover `download_generated`, which now finally has real files to serve.

- [ ] **Step 7: Commit**

```bash
git add home/views.py templates/test2.html home/tests.py
git commit -m "feat(letters): store generated letters and record generation metadata"
```

---

## Task 8: Duplicate a system template into a professor's library

**Files:**
- Modify: `home/views.py` (new view, place it directly after `getTemplate`)
- Modify: `home/urls.py`
- Test: `home/tests.py`

FR-3: a professor starts from a system template, gets an editable copy of their own, then edits it through the existing `customTemplate.html` flow.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class DuplicateTemplateTests(TestCase):
    """A professor can copy a system template into their own library (FR-3)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof I", unique_id="T-I")
        self.other = TeacherInfo.objects.create(name="Prof J", unique_id="T-J")
        self.system = CustomTemplates.objects.filter(is_system=True).first()
        self.client.cookies["unique"] = "T-I"

    def test_duplicating_creates_an_owned_editable_copy(self):
        response = self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        self.assertEqual(response.status_code, 302)
        copy = CustomTemplates.objects.get(professor=self.teacher)
        self.assertEqual(copy.template, self.system.template)
        self.assertFalse(copy.is_system)
        self.assertFalse(copy.is_default)

    def test_the_copy_is_named_after_the_original(self):
        self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        copy = CustomTemplates.objects.get(professor=self.teacher)
        self.assertEqual(copy.template_name, f"{self.system.template_name} (copy)")

    def test_duplicating_twice_does_not_collide(self):
        self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        names = list(
            CustomTemplates.objects.filter(professor=self.teacher)
            .values_list("template_name", flat=True)
        )
        self.assertEqual(len(names), 2)
        self.assertEqual(len(set(names)), 2)

    def test_the_original_system_template_is_untouched(self):
        self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        self.system.refresh_from_db()
        self.assertTrue(self.system.is_system)
        self.assertIsNone(self.system.professor)

    def test_a_professor_may_duplicate_their_own_template(self):
        mine = CustomTemplates.objects.create(
            template_name="Mine", template="body", professor=self.teacher
        )
        self.client.post("/duplicateTemplate", {"template_id": mine.pk})
        self.assertEqual(
            CustomTemplates.objects.filter(professor=self.teacher).count(), 2
        )

    def test_another_professors_template_cannot_be_duplicated(self):
        theirs = CustomTemplates.objects.create(
            template_name="Theirs", template="secret", professor=self.other
        )
        response = self.client.post("/duplicateTemplate", {"template_id": theirs.pk})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(CustomTemplates.objects.filter(professor=self.teacher).exists())

    def test_a_stale_cookie_redirects_to_login(self):
        self.client.cookies["unique"] = "NOPE"
        response = self.client.post("/duplicateTemplate", {"template_id": self.system.pk})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])

    def test_a_malformed_id_is_not_served(self):
        response = self.client.post("/duplicateTemplate", {"template_id": "abc"})
        self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.DuplicateTemplateTests -v2`
Expected: FAIL — 404 for every case, since `/duplicateTemplate` does not exist.

- [ ] **Step 3: Add the view to `home/views.py`**

Place directly after the end of `getTemplate`:

```python
@csrf_exempt
def duplicate_template(request):
    """Copy a system (or own) template into this professor's editable library (FR-3)."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")

    teacher = TeacherInfo.objects.get(unique_id=unique)
    try:
        template_id = int(request.POST.get("template_id", ""))
    except (TypeError, ValueError):
        raise Http404("No valid template requested.")

    # Only shared system templates and the professor's own may be copied.
    source = get_object_or_404(
        CustomTemplates.objects.filter(Q(professor=teacher) | Q(is_system=True)),
        pk=template_id,
    )

    base_name = f"{source.template_name} (copy)"
    name = base_name
    suffix = 2
    while CustomTemplates.objects.filter(professor=teacher, template_name=name).exists():
        name = f"{base_name} {suffix}"
        suffix += 1

    CustomTemplates.objects.create(
        template_name=name,
        template=source.template,
        professor=teacher,
        is_default=False,
        is_system=False,
    )
    messages.success(request, f'Copied "{source.template_name}" into your templates.')
    return redirect("/makeTemplate")
```

`Q` was added to the imports in Task 7 Step 3. If you are executing Task 8 standalone, add `from django.db.models import Q` after line 4 of `home/views.py`.

- [ ] **Step 4: Add the route to `home/urls.py`**

Directly after the `getTemplate` line (currently line 52):

```python
    path('duplicateTemplate', views.duplicate_template, name='duplicateTemplate'),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.DuplicateTemplateTests -v2`
Expected: `OK` (8 tests).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/urls.py home/tests.py
git commit -m "feat(templates): duplicate a system template into a professor's library"
```

---

## Task 9: Show the system library in the template editor

**Files:**
- Modify: `home/views.py` (the `template` view)
- Modify: `templates/customTemplate.html`
- Test: `home/tests.py`

The `template` view currently does an unguarded `TeacherInfo.objects.get(unique_id=unique)`, which raises `DoesNotExist` (a 500 with a full `DEBUG` traceback) for a stale cookie. Guard it the same way every other teacher view now does.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class TemplateEditorViewTests(TestCase):
    """The editor lists system templates alongside the professor's own (FR-3)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof K", unique_id="T-K")
        self.other = TeacherInfo.objects.create(name="Prof L", unique_id="T-L")
        self.mine = CustomTemplates.objects.create(
            template_name="My Own Template", template="body", professor=self.teacher
        )
        CustomTemplates.objects.create(
            template_name="Not Mine At All", template="body", professor=self.other
        )
        self.client.cookies["unique"] = "T-K"

    def test_the_professors_own_templates_are_listed(self):
        response = self.client.get("/makeTemplate")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Own Template")

    def test_system_templates_are_offered(self):
        response = self.client.get("/makeTemplate")
        self.assertContains(response, "Formal / Academic")

    def test_another_professors_templates_are_not_shown(self):
        response = self.client.get("/makeTemplate")
        self.assertNotContains(response, "Not Mine At All")

    def test_each_system_template_has_a_duplicate_button(self):
        response = self.client.get("/makeTemplate")
        system = CustomTemplates.objects.filter(is_system=True).first()
        self.assertContains(response, "/duplicateTemplate")
        self.assertContains(response, f'name="template_id" value="{system.pk}"')

    def test_a_stale_cookie_redirects_instead_of_crashing(self):
        self.client.cookies["unique"] = "NOPE"
        response = self.client.get("/makeTemplate")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.TemplateEditorViewTests -v2`
Expected: FAIL — no system templates in the page, and the stale-cookie case raises `TeacherInfo.DoesNotExist`.

- [ ] **Step 3: Replace the `template` view in `home/views.py`**

```python
def template(request):
    """The professor's template editor: their own templates plus the system library."""
    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")

    teacher = TeacherInfo.objects.get(unique_id=unique)
    return render(request, "customTemplate.html", {
        "professor": teacher,
        "templates": CustomTemplates.objects.filter(professor=teacher),
        "system_templates": CustomTemplates.objects.filter(
            is_system=True
        ).order_by("template_name"),
    })
```

- [ ] **Step 4: Update `home/views.py` `getTemplate` to return the system list too**

`getTemplate` re-renders `customTemplate.html` after saving. Its final `render` call must pass the same key or the system section vanishes after every save. Replace its final `return render(...)` line with:

```python
        return render(request, "customTemplate.html", {
            'professor': teacher,
            'templates': CustomTemplates.objects.filter(professor=teacher),
            'system_templates': CustomTemplates.objects.filter(
                is_system=True
            ).order_by("template_name"),
            'template': template_obj,
        })
```

- [ ] **Step 5: Add the system-template section to `templates/customTemplate.html`**

Immediately before the existing form that posts to `/getTemplate` (around line 218), insert:

```html
<div class="system-templates" style="margin: 20px 0;">
  <h3>Starter templates</h3>
  <p>Copy one into your own templates, then edit it however you like.</p>
  {% for template in system_templates %}
  <form method="post" action="/duplicateTemplate" style="display:inline-block; margin:4px;">
    <input type="hidden" name="template_id" value="{{ template.pk }}">
    <button type="submit" class="btn btn-secondary">
      Duplicate "{{ template.template_name }}"
    </button>
  </form>
  {% empty %}
  <p>No starter templates are installed.</p>
  {% endfor %}
</div>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.TemplateEditorViewTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 7: Commit**

```bash
git add home/views.py templates/customTemplate.html home/tests.py
git commit -m "feat(templates): offer the starter library in the template editor"
```

---

## Task 10: Close the `getTemplate` ownership hole

**Files:**
- Modify: `home/views.py` (the `getTemplate` view)
- Test: `home/tests.py`

`getTemplate` reads the professor id from a **hidden form field** (`uid`), not the cookie. Posting another professor's `unique_id` rewrites their templates. This phase makes templates a first-class feature, so the hole gets closed here rather than left to grow.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class GetTemplateOwnershipTests(TestCase):
    """Saving a template writes to the signed-in professor only (FR-3)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof M", unique_id="T-M")
        self.victim = TeacherInfo.objects.create(name="Prof N", unique_id="T-N")
        self.client.cookies["unique"] = "T-M"

    def test_a_template_is_saved_to_the_signed_in_professor(self):
        self.client.post("/getTemplate", {
            "content": "Dear Committee", "templateName": "Mine", "uid": "T-M",
        })
        saved = CustomTemplates.objects.get(template_name="Mine")
        self.assertEqual(saved.professor, self.teacher)

    def test_a_forged_uid_cannot_write_to_another_professor(self):
        self.client.post("/getTemplate", {
            "content": "Injected", "templateName": "Forged", "uid": "T-N",
        })
        self.assertFalse(CustomTemplates.objects.filter(professor=self.victim).exists())
        self.assertTrue(CustomTemplates.objects.filter(professor=self.teacher).exists())

    def test_marking_default_clears_the_previous_default(self):
        old = CustomTemplates.objects.create(
            template_name="Old", template="x", professor=self.teacher, is_default=True
        )
        self.client.post("/getTemplate", {
            "content": "New body", "templateName": "New", "is_default": "on", "uid": "T-M",
        })
        old.refresh_from_db()
        self.assertFalse(old.is_default)
        self.assertTrue(CustomTemplates.objects.get(template_name="New").is_default)

    def test_saving_the_same_name_updates_rather_than_duplicates(self):
        self.client.post("/getTemplate", {
            "content": "First", "templateName": "Same", "uid": "T-M",
        })
        self.client.post("/getTemplate", {
            "content": "Second", "templateName": "Same", "uid": "T-M",
        })
        matches = CustomTemplates.objects.filter(
            professor=self.teacher, template_name="Same"
        )
        self.assertEqual(matches.count(), 1)
        self.assertIn("Second", matches.first().template)

    def test_a_stale_cookie_redirects_to_login(self):
        self.client.cookies["unique"] = "NOPE"
        response = self.client.post("/getTemplate", {
            "content": "x", "templateName": "y", "uid": "T-M",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.GetTemplateOwnershipTests -v2`
Expected: FAIL on `test_a_forged_uid_cannot_write_to_another_professor` — the template lands on Prof N.

- [ ] **Step 3: Replace the identity lookup in `getTemplate`**

In `home/views.py`, inside `getTemplate`, delete these two lines:

```python
        uid = request.POST.get("uid")
        ...
        teacher = TeacherInfo.objects.get(unique_id= uid)
```

and replace the start of the function body with:

```python
def getTemplate(request):
    if request.method != "POST":
        return redirect("/makeTemplate")

    # Identity comes from the cookie, never from the posted ``uid`` field: a
    # hidden input is client-controlled and could name another professor.
    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")

    teacher = TeacherInfo.objects.get(unique_id=unique)
    content = request.POST.get("content") or ""
    name = request.POST.get("templateName")
    make_default = request.POST.get("is_default") == 'on'
    # legacy: if template is named "Default" treat as default
    if name and name.strip().lower() == 'default':
        make_default = True
```

Then de-indent the remainder of the function body by one level so it sits directly under `def getTemplate`, since the `if request.method == "POST":` wrapper is gone. Leave the editor-artifact cleanup, the default-clearing, the update-or-create, and the final `render` (as updated in Task 9) exactly as they are.

The hidden `uid` input in `customTemplate.html:256` can stay; it is simply ignored now.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.GetTemplateOwnershipTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 5: Re-run the editor tests to confirm nothing regressed**

Run: `venv/bin/python manage.py test home.tests.TemplateEditorViewTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "fix(templates): take the template owner from the session cookie, not the form"
```

---

## Task 11: Remove the dead hardcoded template copies

**Files:**
- Modify: `home/views.py` (remove `add_default_template_to_all_professors`)
- Test: `home/tests.py`

Tasks 6 and 7 deleted two of the three hardcoded default-letter strings. The third lives in `add_default_template_to_all_professors` (around lines 2130-2201), a helper that is **not routed in `urls.py` and not called anywhere**. Seeded system templates replace it.

- [ ] **Step 1: Verify it really is unreferenced**

```bash
grep -rn "add_default_template_to_all_professors" --include=*.py --include=*.html .
```

Expected: matches only inside `home/views.py` itself (the definition). If any other file references it, **stop and report** rather than deleting.

- [ ] **Step 2: Write the failing test**

Append to `home/tests.py`:

```python
class NoHardcodedTemplatesTests(TestCase):
    """Letter bodies live in the database, not in views.py (FR-1)."""

    def test_views_no_longer_carries_a_hardcoded_letter(self):
        import inspect
        from home import views
        source = inspect.getsource(views)
        self.assertNotIn("default_template_content", source)

    def test_the_seeding_helper_is_gone(self):
        from home import views
        self.assertFalse(hasattr(views, "add_default_template_to_all_professors"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.NoHardcodedTemplatesTests -v2`
Expected: FAIL — `add_default_template_to_all_professors` still exists.

- [ ] **Step 4: Delete the helper**

Remove the whole `add_default_template_to_all_professors` function from `home/views.py`, including its docstring and the hardcoded template string inside it.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.NoHardcodedTemplatesTests -v2`
Expected: `OK` (2 tests).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "refactor(templates): drop the unused hardcoded default-template helper"
```

---

## Task 12: Dashboard link and documentation

**Files:**
- Modify: `templates/Teacher.html:139-143`
- Modify: `README.md:112-150`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class DashboardTemplateLinkTests(TestCase):
    """The dashboard points professors at the template library (FR-3)."""

    def setUp(self):
        self.teacher = TeacherInfo.objects.create(name="Prof O", unique_id="T-O")
        self.client.cookies["unique"] = "T-O"

    def test_the_dashboard_links_to_the_template_editor(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/makeTemplate")

    def test_a_professor_with_no_default_is_told_about_the_starter_library(self):
        response = self.client.get("/teacher")
        self.assertContains(response, "starter template")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.DashboardTemplateLinkTests -v2`
Expected: FAIL on the second test — the phrase is absent.

- [ ] **Step 3: Update `templates/Teacher.html`**

Replace lines 138-143, which currently read:

```html
  {% comment %} display current default template if exists (provided by view) {% endcomment %}
  {% if default_template %}
  <h4>Current default template: <em>{{ default_template.template_name }}</em></h4>
  {% endif %}
  <h2>Manage Templates:</h2>
  <a href="/makeTemplate" class="btn btn-primary">Create / Edit Templates</a>
```

with:

```html
  {% comment %} display current default template if exists (provided by view) {% endcomment %}
  {% if default_template %}
  <h4>Current default template: <em>{{ default_template.template_name }}</em></h4>
  {% else %}
  <h4>No default template yet. Duplicate a starter template to get going.</h4>
  {% endif %}
  <h2>Manage Templates:</h2>
  <a href="/makeTemplate" class="btn btn-primary">Create / Edit Templates</a>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.DashboardTemplateLinkTests -v2`
Expected: `OK` (2 tests).

- [ ] **Step 5: Update `README.md`**

Replace the "Teacher / Professor" step 5 and step 6 (lines 131-134) with:

```markdown
5. The recommended-students table shows **when** each letter was generated, **which template**
   produced it, and a **Re-download** link for the stored file.
6. **Templates.** Open **Create / Edit Templates**. Three starter templates ship with the app
   (*Formal / Academic*, *Research / Graduate School*, *General Purpose*) — press **Duplicate**
   on one to get your own editable copy, then edit and save it. Tick *default* to make a
   template the one pre-selected for every new letter.
7. **Generate.** Pick a template on the letter form, preview it, edit the text inline if you
   want, then download as PDF or DOCX. The download is what gets stored and listed on your
   dashboard.
```

Also update the test count on line 144 from `70 tests` to the real number reported by the final full-suite run in Task 13, and add to the "Project layout" block after the `dashboard.py` line:

```
  letters.py     Letter context, template selection, rendering, PDF/DOCX export
```

> **Note:** starter templates are plain ASCII on purpose. The PDF exporter encodes latin-1, so
> characters like em dashes or curly quotes in a custom template are replaced with `?` in the
> PDF. Keep custom templates to plain ASCII for a clean export.

- [ ] **Step 6: Commit**

```bash
git add templates/Teacher.html README.md home/tests.py
git commit -m "docs: document the template library and starter templates"
```

---

## Task 13: Final full-suite verification

**Files:** none modified unless failures appear.

This is the **only** point in the plan where the whole suite runs.

- [ ] **Step 1: Run the full suite**

```bash
venv/bin/python manage.py test home -v2
```

Expected: `OK`. Total should be roughly 73 (Phase 2) + 68 new = ~141 tests. Some tests deliberately exercise 404 paths, so `[WARNING] Not Found: ...` lines are expected output, not failures.

- [ ] **Step 2: Confirm the migrations are consistent**

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`. If it reports pending changes, the model and migrations have drifted — generate the missing migration and re-run the suite.

- [ ] **Step 3: Smoke-test the real server**

```bash
venv/bin/python manage.py runserver
```

Log in as a professor, open **Create / Edit Templates**, duplicate a starter template, edit and save it, then generate a letter for a student choosing that template, edit a sentence in the preview, and download the PDF. Confirm the dashboard's recommended table now shows a real timestamp, the template name, and a working **Re-download** link. Stop the server with Ctrl-C.

- [ ] **Step 4: Update the README test count**

Set the number on `README.md:144` to the exact count printed in Step 1.

- [ ] **Step 5: Verify commit hygiene**

```bash
git log --format='%H %s%n%b' origin/main..HEAD | grep -ci "co-authored-by\|claude\|generated with"
git status --porcelain | grep -c "CLAUDE.md"
```

Expected: `0` from both commands.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: update the test count"
```

- [ ] **Step 7: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill with argument `phase3-template-library`.

---

## Notes for the reviewer

Things a reviewer should specifically try to break:

1. **Cross-professor leakage.** `select_template`, `duplicate_template`, `download_letter`, and `getTemplate` all take an id or name from client input. Post Prof A's template id while holding Prof B's cookie in each and confirm you get a fallback or a 404, never Prof A's content.
2. **The `.distinct()`-style trap.** `available_templates` ORs two conditions on one table without a join, so no dedup is needed — but confirm a professor's own template does not appear twice.
3. **Stamping on failure.** `download_letter` must not stamp `is_generated` when the format is rejected. Try `format=txt` and a missing `roll`.
4. **The edited-letter path.** This is the one that was silently broken. Type into the preview, download, then open the stored file from the dashboard's Re-download link and confirm your edit is in it.
5. **Migration reversibility.** `migrate home 0011` and back up to `0013`; confirm no duplicate seeded rows appear (the seed uses `update_or_create`).
6. **The seeded templates against a sparse application.** Create an Application with no `Paper`, `Project`, `University`, `Qualities`, `Academics`, or `Files` rows and render all three system templates. None may raise.
