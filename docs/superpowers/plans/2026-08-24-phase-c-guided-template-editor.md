# Phase C — Guided Template Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a professor insert friendly-named fields and balanced optional sections into a recommendation-letter template from a menu, validate the template on save, and preview it — on the existing Django stack with no build step.

**Architecture:** A field registry + validation + sample-context helpers live in `home/letters.py` (pure, mostly DB-free). `home/views.py` gains a preview endpoint and validation on the existing save handler (`getTemplate`), plus a shared editor-context helper. `templates/customTemplate.html` swaps TinyMCE for CodeMirror 5 (CDN, `jinja2` mode) with an Insert-field dropdown, an Insert-optional-section helper, and a Preview panel.

**Tech Stack:** Django 5.1, Jinja2 `SandboxedEnvironment`, CodeMirror 5 (cdnjs UMD), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-08-24-phase-c-guided-template-editor-design.md`

**Repo rules (all tasks):** No AI attribution in commits. Never `git add` `CLAUDE.md`, `db.sqlite3`, or `docs/mockups/`. All POSTs keep `{% csrf_token %}`. Identity via `current_teacher`; own-templates/own-applications only. Activate the venv first: `source venv/bin/activate`. **Per-task test scoping: run only the named test class(es); the full suite runs once at the final task.**

---

## File Structure

- `home/letters.py` — add `FIELDS`, `grouped_fields()`, `sample_context()`, `validate_template()`, `render_source()`. (Field surface + validation + preview rendering all belong with the existing render helpers.)
- `home/views.py` — add `_template_editor_context()` helper; add validation + drop TinyMCE cleanup in `getTemplate`; add `preview_template`.
- `home/urls.py` — add the `previewTemplate` route.
- `templates/customTemplate.html` — replace TinyMCE with CodeMirror 5 + toolbar + preview.
- `templates/template_preview.html` — **new**, the fragment `preview_template` returns.
- `home/tests.py` — new test classes.

---

## Task 1: Field registry + sample context (`home/letters.py`)

**Files:**
- Modify: `home/letters.py` (add after `join_subjects`, near line 72)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `home/tests.py` (find any existing `from home.letters import ...` style; these use `SimpleTestCase`, no DB):

```python
class TemplateFieldRegistryTests(SimpleTestCase):
    def test_grouped_fields_groups_in_first_seen_order(self):
        from home.letters import grouped_fields
        groups = grouped_fields()
        names = [g["group"] for g in groups]
        self.assertEqual(names, list(dict.fromkeys(names)))  # no group repeats
        self.assertEqual(names[0], "Student")
        # each field row exposes a label and an expr
        first = groups[0]["fields"][0]
        self.assertIn("label", first)
        self.assertIn("expr", first)

    def test_every_field_top_name_is_a_real_context_key(self):
        from home.letters import FIELDS, sample_context, _field_top_name
        allowed = set(sample_context().keys())
        for label, expr, group in FIELDS:
            self.assertIn(
                _field_top_name(expr), allowed,
                f"{label!r} -> {expr!r} references an unknown top-level name",
            )

    def test_sample_context_renders_a_representative_template(self):
        from home.letters import sample_context, _JINJA
        tpl = ("{{ app.name }} in {{ app.std.program.program_name }}; "
               "GPA {{ academics.gpa }}; {{ teacher.name }}; {{ today }}"
               "{% if academics.gpa %} ranked {{ app.ranking_percentile }}{% endif %}")
        out = _JINJA.from_string(tpl).render(sample_context())
        self.assertIn("Asmita", out)
        self.assertIn("3.82", out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test home.tests.TemplateFieldRegistryTests -v 2`
Expected: FAIL / ERROR — `cannot import name 'grouped_fields'` (and `FIELDS`, `sample_context`).

- [ ] **Step 3: Implement the registry + sample context**

In `home/letters.py`, add after `join_subjects` (about line 72):

```python
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
    """``FIELDS`` grouped by group label, preserving first-seen group order."""
    from collections import OrderedDict
    groups = OrderedDict()
    for label, expr, group in FIELDS:
        groups.setdefault(group, []).append({"label": label, "expr": expr})
    return [{"group": g, "fields": items} for g, items in groups.items()]


def sample_context():
    """A dummy render context mirroring build_letter_context's keys, for previews.

    Uses ``SimpleNamespace`` stand-ins so the attribute access the templates use
    (``app.name``, ``app.std.program.program_name``, ``academics.gpa`` ...) resolves.
    Touches no database and exposes no real student.
    """
    from types import SimpleNamespace
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
```

Note: `re`, `datetime`, `STRENGTH_PHRASES`, `join_subjects`, and `_JINJA` already exist at the top of `home/letters.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test home.tests.TemplateFieldRegistryTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add home/letters.py home/tests.py
git commit -m "feat(templates): field registry and sample render context"
```

---

## Task 2: Template validation (`home/letters.py`)

**Files:**
- Modify: `home/letters.py` (add after `sample_context`)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
class ValidateTemplateTests(SimpleTestCase):
    def test_clean_template_has_no_errors_or_warnings(self):
        from home.letters import validate_template
        errors, warnings = validate_template("Dear {{ app.name }}, {{ today }}.")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_unbalanced_tag_is_a_blocking_error(self):
        from home.letters import validate_template
        errors, warnings = validate_template("{% if academics.gpa %}hi")  # no endif
        self.assertTrue(errors)
        self.assertIn("syntax", errors[0].lower())

    def test_unknown_variable_is_a_non_blocking_warning(self):
        from home.letters import validate_template
        errors, warnings = validate_template("Hello {{ nmae }}")
        self.assertEqual(errors, [])
        self.assertTrue(any("nmae" in w for w in warnings))

    def test_known_nested_attribute_is_not_warned(self):
        from home.letters import validate_template
        errors, warnings = validate_template("{{ app.name }} {{ teacher.email }}")
        self.assertEqual((errors, warnings), ([], []))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test home.tests.ValidateTemplateTests -v 2`
Expected: FAIL — `cannot import name 'validate_template'`.

- [ ] **Step 3: Implement `validate_template`**

At the top of `home/letters.py`, extend the jinja import (currently `from jinja2 import TemplateError`):

```python
from jinja2 import TemplateError, TemplateSyntaxError, meta
```

Add after `sample_context` in `home/letters.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test home.tests.ValidateTemplateTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add home/letters.py home/tests.py
git commit -m "feat(templates): validate_template and render_source helpers"
```

---

## Task 3: Preview endpoint (`home/views.py`, `home/urls.py`, new fragment template)

**Files:**
- Create: `templates/template_preview.html`
- Modify: `home/views.py` (extend the `home.letters` import block near line 116; add `preview_template` after `renderCustom`)
- Modify: `home/urls.py` (add route near the other template routes, ~line 53)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
class PreviewTemplateTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-PC", department=self.dept)
        self.teacher = TeacherInfo.objects.create(
            unique_id="TP1", name="Prof P", email="pp@example.com", department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="stu", roll_number="080BCT700", department=self.dept,
            program=self.program, dob="2000-01-01",
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.teacher, name="Stu One",
        )
        login_as_teacher(self.client, self.teacher)

    def test_sample_mode_renders_the_posted_content(self):
        resp = self.client.post("/previewTemplate", {
            "content": "Hello {{ app.name }} on {{ today }}.", "mode": "sample",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Asmita Sharma")

    def test_application_mode_uses_the_real_student(self):
        resp = self.client.post("/previewTemplate", {
            "content": "Hello {{ app.name }}.", "mode": "application",
            "application_id": str(self.app.pk),
        })
        self.assertContains(resp, "Stu One")

    def test_a_foreign_application_is_404(self):
        other_teacher = TeacherInfo.objects.create(
            unique_id="TP2", name="Prof Q", email="pq@example.com", department=self.dept,
        )
        foreign = Application.objects.create(
            std=self.student, professor=other_teacher, name="Not Yours",
        )
        resp = self.client.post("/previewTemplate", {
            "content": "x", "mode": "application", "application_id": str(foreign.pk),
        })
        self.assertEqual(resp.status_code, 404)

    def test_a_syntax_error_is_reported_not_rendered(self):
        resp = self.client.post("/previewTemplate", {
            "content": "{% if academics.gpa %}oops", "mode": "sample",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "syntax")

    def test_logged_out_cannot_preview(self):
        self.client.cookies.clear()
        resp = self.client.post("/previewTemplate", {"content": "x", "mode": "sample"})
        self.assertNotEqual(resp.status_code, 200)  # redirected to login
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test home.tests.PreviewTemplateTests -v 2`
Expected: FAIL — 404 for the URL / `preview_template` does not exist.

- [ ] **Step 3a: Create the fragment template**

Create `templates/template_preview.html`:

```django
{% if error %}
  <div class="tpl-preview-error">{{ error }}</div>
{% else %}
  {% if warnings %}
  <div class="tpl-preview-warn">
    <strong>Warnings:</strong>
    <ul>{% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>
  </div>
  {% endif %}
  <pre class="tpl-preview-letter" style="white-space:pre-wrap;font-family:Georgia,serif;">{{ letter }}</pre>
{% endif %}
```

- [ ] **Step 3b: Extend the letters import in `home/views.py`**

Find (around line 116):

```python
from home.letters import (
    available_templates, build_docx_bytes, build_pdf_bytes,
    render_letter, select_template, system_templates, visible_to,
)
```

Replace with:

```python
from home.letters import (
    available_templates, build_docx_bytes, build_pdf_bytes,
    build_letter_context, grouped_fields, render_letter, render_source,
    sample_context, select_template, system_templates, validate_template,
    visible_to,
)
```

- [ ] **Step 3c: Add the `preview_template` view**

In `home/views.py`, add immediately after `renderCustom` (ends ~line 1350):

```python
def preview_template(request):
    """Render unsaved editor content against sample or own-application data."""
    if request.method != "POST":
        return redirect("/makeTemplate")

    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")

    content = request.POST.get("content") or ""
    errors, warnings = validate_template(content)
    if errors:
        return render(request, "template_preview.html", {"error": " ".join(errors)})

    mode = request.POST.get("mode") or "sample"
    if mode == "application":
        app_id = (request.POST.get("application_id") or "").strip()
        if not app_id.isdigit():
            raise Http404("No application selected.")
        # Own applications only: a foreign or unknown id is a 404, never a peek
        # at another professor's student.
        application = get_object_or_404(Application, pk=app_id, professor=teacher)
        context = build_letter_context(application)
    else:
        context = sample_context()

    try:
        letter = render_source(content, context)
    except TemplateError:
        return render(request, "template_preview.html",
                      {"error": "This template could not be rendered."})
    return render(request, "template_preview.html",
                  {"letter": letter, "warnings": warnings})
```

Add the import near the other `home.letters`/jinja imports at the top of `home/views.py` if not present:

```python
from jinja2 import TemplateError
```

- [ ] **Step 3d: Add the URL**

In `home/urls.py`, after the `setDefaultTemplate` line (~line 53):

```python
    path('previewTemplate', views.preview_template, name='previewTemplate'),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test home.tests.PreviewTemplateTests -v 2`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/urls.py templates/template_preview.html home/tests.py
git commit -m "feat(templates): preview endpoint for sample or own-application data"
```

---

## Task 4: Validation on save + shared editor context (`home/views.py`)

**Files:**
- Modify: `home/views.py` — add `_template_editor_context`; rewrite the render calls in `template` and `getTemplate`; add validation; drop the TinyMCE HTML-artifact cleanup.
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing tests**

```python
class TemplateSaveValidationTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            unique_id="TS1", name="Prof S", email="ps@example.com", department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_unbalanced_template_is_rejected_and_not_saved(self):
        from home.models import CustomTemplates
        resp = self.client.post("/getTemplate", {
            "templateName": "Broken", "content": "{% if academics.gpa %}no end",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "syntax")
        self.assertFalse(
            CustomTemplates.objects.filter(professor=self.teacher, template_name="Broken").exists()
        )

    def test_unknown_variable_saves_but_warns(self):
        from home.models import CustomTemplates
        resp = self.client.post("/getTemplate", {
            "templateName": "Typo", "content": "Hi {{ nmae }}",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "nmae")
        tpl = CustomTemplates.objects.get(professor=self.teacher, template_name="Typo")
        self.assertEqual(tpl.template, "Hi {{ nmae }}")

    def test_editor_page_lists_fields_and_uses_codemirror(self):
        resp = self.client.get("/makeTemplate")
        self.assertContains(resp, "codemirror")
        self.assertContains(resp, 'id="insertField"')
        self.assertContains(resp, "Student name")
        self.assertNotContains(resp, "tinymce")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test home.tests.TemplateSaveValidationTests -v 2`
Expected: FAIL — unbalanced template currently saves (no validation), and the page still says `tinymce` (Task 5 fixes the page; this task fixes the save + context).

Note: `test_editor_page_lists_fields_and_uses_codemirror` fully passes only after Task 5. It is written here with the save tests because it asserts the context keys this task adds; expect it RED until Task 5. (Subagent: report it as a known cross-task assertion; do not force it green by editing the template in this task.)

- [ ] **Step 3a: Add the shared editor-context helper**

In `home/views.py`, add just above `def template(request):` (~line 1352):

```python
def _template_editor_context(teacher, **extra):
    """Context every render of customTemplate.html needs.

    Centralised so the editor page, the save re-renders and the clash re-render
    all expose the field palette and the professor's own applications.
    """
    ctx = {
        "professor": teacher,
        "templates": CustomTemplates.objects.filter(professor=teacher),
        "system_templates": system_templates().order_by("template_name"),
        "field_groups": grouped_fields(),
        "applications": Application.objects.filter(
            professor=teacher
        ).order_by("std__roll_number"),
    }
    ctx.update(extra)
    return ctx
```

- [ ] **Step 3b: Use it in `template` (the editor page)**

Replace the body of `template` (the `return render(...)` at ~1358) with:

```python
    return render(request, "customTemplate.html", _template_editor_context(teacher))
```

- [ ] **Step 3c: Add validation + drop TinyMCE cleanup in `getTemplate`**

In `getTemplate`, **delete** these six TinyMCE-artifact lines (~1387-1393):

```python
    # cleanup editor artifacts
    content = content.replace('<p>&nbsp;</p>\n<p>&nbsp;</p>', '')
    content = content.replace('<p>&nbsp;</p>', '')
    content = content.replace('</p>\n<p>', '<br>')
    content = content.replace('</p>\r\n<p>', '<br>')
    content = content.replace('</p>\r<p>', '<br>')
    content = content.replace('<p>', '<p><br>')
```

Then, immediately after the name check block (right after the `make_default`/legacy-"default" lines, ~line 1385) insert:

```python
    # CodeMirror edits the raw template, so validate before writing: unbalanced
    # tags block the save; unknown variables are surfaced as non-blocking
    # warnings (Jinja renders them empty).
    errors, warnings = validate_template(content)
    if errors:
        return render(request, "customTemplate.html", _template_editor_context(
            teacher, error=" ".join(errors),
            submitted_name=name, submitted_content=content,
        ))
```

Replace the **clash** re-render (~1421) with:

```python
            return render(request, "customTemplate.html", _template_editor_context(
                teacher, template=template_obj,
                error=f'You already have a template named "{name}".',
            ))
```

(Remove the inline `messages.error(...)` line above it — the error now shows in the banner.)

Replace the **final success** re-render (~1451) with:

```python
    return render(request, "customTemplate.html", _template_editor_context(
        teacher, template=template_obj, warnings=warnings,
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test home.tests.TemplateSaveValidationTests -v 2`
Expected: the two save tests PASS; `test_editor_page_lists_fields_and_uses_codemirror` stays RED until Task 5.

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "feat(templates): validate on save; share editor context; drop tinymce cleanup"
```

---

## Task 5: CodeMirror editor page (`templates/customTemplate.html`)

**Files:**
- Modify (full replace): `templates/customTemplate.html`
- Test: `home/tests.py` (`TemplateSaveValidationTests.test_editor_page_lists_fields_and_uses_codemirror` from Task 4 turns green here)

- [ ] **Step 1: Confirm the target test exists and is red**

Run: `python manage.py test home.tests.TemplateSaveValidationTests.test_editor_page_lists_fields_and_uses_codemirror -v 2`
Expected: FAIL — page still contains `tinymce`, no `codemirror`.

- [ ] **Step 2: Replace `templates/customTemplate.html` in full**

```django
{% extends 'base2.html' %} {% block title %}Create Template{% endblock title %}
{% block raw %}
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/jinja2/jinja2.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/addon/edit/matchbrackets.min.js"></script>
{% endblock raw %}
{% block body %}
<div class="center-content">
  <h3>Create Recommendation Letter Template</h3>
  <p class="tpl-sub">Insert fields and optional sections from the menus — you never type a brace. Save checks the template; Preview shows a finished letter.</p>

  {% if error %}
  <div class="tpl-banner tpl-banner-error">{{ error }}</div>
  {% endif %}
  {% if warnings %}
  <div class="tpl-banner tpl-banner-warn">
    <strong>Saved with warnings:</strong>
    <ul>{% for w in warnings %}<li>{{ w }}</li>{% endfor %}</ul>
  </div>
  {% endif %}

  <div class="system-templates" style="margin: 20px 0;">
    <h3>Starter templates</h3>
    <p>Copy one into your own templates, then edit it however you like.</p>
    {% for sys_tpl in system_templates %}
    <form method="post" action="/duplicateTemplate" style="display:inline-block; margin:4px;">
      {% csrf_token %}
      <input type="hidden" name="template_id" value="{{ sys_tpl.pk }}">
      <button type="submit" class="btn btn-secondary">Duplicate "{{ sys_tpl.template_name }}"</button>
    </form>
    {% empty %}
    <p>No starter templates are installed.</p>
    {% endfor %}
  </div>

  {% if templates and templates.count > 0 %}
  <div class="my-templates" style="text-align:left; margin: 12px 0 20px;">
    <span class="details">Your templates:</span>
    <ul style="list-style:none; padding:0; margin:8px 0;">
      {% for tmp in templates %}
      <li style="display:flex; align-items:center; gap:10px; padding:8px 10px; border:1px solid #e4e3dc; border-radius:8px; margin-bottom:6px;">
        <strong style="flex:1">{{ tmp.template_name }}{% if tmp.is_default %} <em style="color:#2f9e44">(default)</em>{% endif %}</strong>
        <button type="button" class="btn btn-secondary" onclick="loadTemplateIntoEditor({{ tmp.pk }})">Edit</button>
        <form action="/setDefaultTemplate" method="post" style="display:inline">
          {% csrf_token %}
          <input type="hidden" name="template_id" value="{{ tmp.pk }}">
          <button type="submit" class="btn btn-secondary">Set default</button>
        </form>
        <form action="/deleteTemplate" method="post" style="display:inline" onsubmit="return confirm('Delete this template?');">
          {% csrf_token %}
          <input type="hidden" name="template_id" value="{{ tmp.pk }}">
          <button type="submit" class="btn btn-secondary">Delete</button>
        </form>
      </li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}

  <form action="/getTemplate" method="post">
    {% csrf_token %}
    <input type="hidden" name="template_id" id="templateId" value="{{ template.pk|default:'' }}">
    <div class="user-details">
      <div class="input-box">
        <span class="details">Template Name : </span>
        <input type="text" placeholder="Template Name" name="templateName" id="templateName" required />
      </div>
      <span class="details2">Template Content : </span>
    </div>

    <div class="tpl-toolbar">
      <label>Insert field:
        <select id="insertField">
          <option value="">— choose —</option>
          {% for grp in field_groups %}
          <optgroup label="{{ grp.group }}">
            {% for f in grp.fields %}<option value="{{ f.expr }}">{{ f.label }}</option>{% endfor %}
          </optgroup>
          {% endfor %}
        </select>
      </label>
      <span class="tpl-optional">
        <label>Optional section if:
          <select id="optionalField">
            <option value="">— choose —</option>
            {% for grp in field_groups %}
            <optgroup label="{{ grp.group }}">
              {% for f in grp.fields %}<option value="{{ f.expr }}">{{ f.label }}</option>{% endfor %}
            </optgroup>
            {% endfor %}
          </select>
        </label>
        <button type="button" id="insertOptional" class="btn btn-secondary">Insert optional section</button>
      </span>
    </div>

    <textarea id="editor" name="content"></textarea>

    <div class="tpl-preview-controls">
      <label>Preview with:
        <select id="previewWith">
          <option value="sample">Sample student</option>
          {% for a in applications %}
          <option value="{{ a.pk }}">{{ a.name|default:a.std.roll_number }} ({{ a.std.roll_number }})</option>
          {% endfor %}
        </select>
      </label>
      <button type="button" id="previewBtn" class="btn btn-secondary">Preview letter</button>
    </div>

    <div>
      <label><input type="checkbox" name="is_default" id="is_default" /> Make this my default template</label>
    </div>
    <div class="button-container"><div class="button"><input type="submit" value="Save Template" /></div></div>
  </form>
</div>

<div id="previewModal" class="tpl-modal" style="display:none">
  <div class="tpl-modal-inner">
    <button type="button" id="previewClose" class="btn btn-secondary" style="float:right">Close</button>
    <h4>Preview</h4>
    <div id="previewBody"></div>
  </div>
</div>

<div id="tpl-store" style="display:none">
  {% for tmp in templates %}
  <input type="hidden" class="tpl-row" data-id="{{ tmp.pk }}" data-name="{{ tmp.template_name }}" data-content="{{ tmp.template }}" data-default="{{ tmp.is_default }}">
  {% endfor %}
</div>

{% if template %}
{{ template.template_name|json_script:"tmpname" }}
{{ template.template|json_script:"tmpbody" }}
{{ template.is_default|json_script:"tmpdefault" }}
{% endif %}
{% if submitted_content is not None %}
{{ submitted_name|json_script:"subname" }}
{{ submitted_content|json_script:"subbody" }}
{% endif %}

<script>
(function () {
  // Braces are assembled at runtime so Django's template engine never parses
  // them out of this script.
  var OPEN = '{' + '{', CLOSE = '}' + '}', TO = '{' + '%', TC = '%' + '}';

  var cm = CodeMirror.fromTextArea(document.getElementById('editor'), {
    mode: 'jinja2', lineNumbers: true, matchBrackets: true, lineWrapping: true
  });
  window.__cm = cm;

  function insert(text) { cm.replaceSelection(text); cm.focus(); }

  document.getElementById('insertField').addEventListener('change', function () {
    if (this.value) { insert(OPEN + ' ' + this.value + ' ' + CLOSE); this.selectedIndex = 0; }
  });

  document.getElementById('insertOptional').addEventListener('click', function () {
    var expr = document.getElementById('optionalField').value;
    if (!expr) { return; }
    var body = cm.getSelection() || ' ...your text... ';
    insert(TO + ' if ' + expr + ' ' + TC + body + TO + ' endif ' + TC);
  });

  var CSRF = document.querySelector('input[name=csrfmiddlewaretoken]').value;
  document.getElementById('previewBtn').addEventListener('click', function () {
    cm.save();
    var pv = document.getElementById('previewWith').value;
    var fd = new FormData();
    fd.append('content', cm.getValue());
    if (pv === 'sample') { fd.append('mode', 'sample'); }
    else { fd.append('mode', 'application'); fd.append('application_id', pv); }
    fd.append('csrfmiddlewaretoken', CSRF);
    fetch('/previewTemplate', { method: 'POST', body: fd })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        document.getElementById('previewBody').innerHTML = html;
        document.getElementById('previewModal').style.display = 'block';
      });
  });
  document.getElementById('previewClose').addEventListener('click', function () {
    document.getElementById('previewModal').style.display = 'none';
  });

  window.loadTemplateIntoEditor = function (pk) {
    var row = document.querySelector('#tpl-store .tpl-row[data-id="' + pk + '"]');
    if (!row) { return; }
    document.getElementById('templateName').value = row.getAttribute('data-name');
    document.getElementById('templateId').value = pk;
    document.getElementById('is_default').checked = row.getAttribute('data-default') === 'True';
    cm.setValue(row.getAttribute('data-content') || '');
    document.getElementById('templateName').scrollIntoView({ behavior: 'smooth' });
  };

  // Refill after a save (edit) or a rejected save (validation error).
  var subBody = document.getElementById('subbody');
  var tmpBody = document.getElementById('tmpbody');
  if (subBody) {
    document.getElementById('templateName').value = JSON.parse(document.getElementById('subname').textContent);
    cm.setValue(JSON.parse(subBody.textContent) || '');
  } else if (tmpBody) {
    document.getElementById('templateName').value = JSON.parse(document.getElementById('tmpname').textContent);
    document.getElementById('is_default').checked = JSON.parse(document.getElementById('tmpdefault').textContent);
    cm.setValue(JSON.parse(tmpBody.textContent) || '');
  }
})();
</script>

<style>
  .center-content { width: 90%; margin: 0 auto; text-align: center; }
  .tpl-sub { color: #545b66; font-size: 14px; margin: 0 0 14px; }
  .button-container { width: 200px; margin: 16px auto 0; }
  form .input-box span.details, .details2 {
    display: block; align-self: flex-start; font-weight: 500; margin-bottom: 5px; text-align: left;
  }
  .tpl-toolbar, .tpl-preview-controls {
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    text-align: left; margin: 10px 0; padding: 8px 10px;
    background: #f4f3ee; border: 1px solid #e4e3dc; border-radius: 8px;
  }
  .tpl-toolbar select, .tpl-preview-controls select { padding: 5px 8px; border: 1px solid #ccc; border-radius: 6px; }
  .CodeMirror { height: 380px; border: 1px solid #ccc; border-radius: 6px; text-align: left; font-size: 14px; }
  .tpl-banner { text-align: left; padding: 10px 14px; border-radius: 6px; margin: 10px 0; }
  .tpl-banner-error { background: #fdecea; color: #b00020; }
  .tpl-banner-warn { background: #fff8e1; color: #8a6d00; }
  .tpl-banner ul { margin: 6px 0 0; }
  .tpl-modal {
    position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 1000;
    display: flex; align-items: flex-start; justify-content: center; padding: 40px 16px; overflow: auto;
  }
  .tpl-modal-inner {
    background: #fff; max-width: 720px; width: 100%; border-radius: 10px;
    padding: 22px 26px; text-align: left; box-shadow: 0 10px 30px rgba(0,0,0,.25);
  }
  .tpl-preview-error { color: #b00020; }
</style>
{% endblock body %}
```

- [ ] **Step 3: Run the targeted render test**

Run: `python manage.py test home.tests.TemplateSaveValidationTests.test_editor_page_lists_fields_and_uses_codemirror -v 2`
Expected: PASS.

- [ ] **Step 4: Run the full template-editor test set for this feature**

Run: `python manage.py test home.tests.TemplateFieldRegistryTests home.tests.ValidateTemplateTests home.tests.PreviewTemplateTests home.tests.TemplateSaveValidationTests -v 2`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add templates/customTemplate.html home/tests.py
git commit -m "feat(templates): CodeMirror guided editor with insert-field, optional-section and preview"
```

---

## Task 6: Final review (full suite + manual smoke)

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite once**

Run: `python manage.py test`
Expected: all pass **except** the one known pre-existing failure
`home.test_csrf_repro.CsrfRoundTripTests.test_public_form_pages_round_trip`
(unhandled `Department.DoesNotExist` in `registerStudent`, unrelated to this work). If any *other* test fails, fix it before finishing.

- [ ] **Step 2: Migrations check (no model changes expected)**

Run: `python manage.py makemigrations --check --dry-run`
Expected: "No changes detected". (Phase C adds no model fields.)

- [ ] **Step 3: Manual smoke (optional but recommended)**

Log in as a professor, open `/makeTemplate`:
- Insert a field → `{{ app.name }}` appears at the cursor.
- Insert optional section around a selection → balanced `{% if ... %}...{% endif %}`.
- Preview with Sample → a letter with "Asmita Sharma"; Preview with a real application → that student.
- Save a template with `{% if x %}` and no `{% endif %}` → rejected with a syntax error, nothing saved.
- Save a template with `{{ nmae }}` → saved, warning shown.

- [ ] **Step 4: Finish the branch**

Use superpowers:finishing-a-development-branch.

---

## Self-Review Notes (author)

- **Spec coverage:** friendly-name dropdown (Task 1 registry + Task 5 UI), insert-optional-section (Task 5), validate-on-save with warn-vs-block (Task 2 + Task 4), preview sample|own-application (Task 3 + Task 5), CodeMirror-no-build (Task 5), single-source field registry (Task 1). All covered.
- **No model change** → no migration (asserted in Task 6).
- **Cross-task assertion:** `test_editor_page_lists_fields_and_uses_codemirror` is authored in Task 4 (it needs the context keys added there) but only goes green in Task 5; flagged in both tasks so a subagent does not thrash.
- **Braces-in-JS:** assembled at runtime (`'{'+'{'`) so the Django template engine never consumes them; no `{% verbatim %}` needed. The Django-driven `<select>` options carry only expressions as data.
