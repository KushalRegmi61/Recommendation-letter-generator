# Phase 4a: Outstanding Follow-Ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the five defects left open at the end of Phase 3 — silent loss of the professor's checkbox input, a 500 on any student who skipped an upload, unreadable non-Latin-1 PDFs, dead code that includes a live unauthenticated write endpoint, and an untracked scratch directory.

**Architecture:** Five independent fixes, each self-contained. No new modules. The only non-obvious one is the PDF font: `fpdf==1.7.2` supports `add_font(..., uni=True)` with a TTF, so Unicode becomes a font-registration change rather than an engine swap.

**Tech Stack:** Django 5.1, Python 3.12, SQLite, `fpdf` 1.7.2, `python-docx`, Django `TestCase`.

---

## Environment notes for every task

- `python` is NOT on PATH. Always use `venv/bin/python`.
- Run tests with `venv/bin/python manage.py test home.tests.<ClassName> -v2`.
- **Run only the test classes your task touches.** The full suite runs once, at the end. Hard project rule.
- Never add `Co-Authored-By`, `Generated with Claude Code`, or any AI attribution to commit messages.
- Never `git add CLAUDE.md` (gitignored) and never `git add db.sqlite3` (tracked, but excluded from commits by project convention — running `migrate` or the tests dirties it; leave it unstaged).
- Baseline: **229 tests pass** on `main` at merge commit `d324fc7`.

## Test fixture requirements (non-nullable FKs)

- `TeacherInfo` requires `department`. `Program` requires `department`.
- `StudentLoginInfo` requires `department`, `program`, `password`, `dob`, `username`, `roll_number`.

Canonical preamble:
```python
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
```

Any test class that writes files needs `@override_settings(MEDIA_ROOT=tempfile.mkdtemp())`. Note that as a **class** decorator this evaluates `mkdtemp()` once at import, so all methods share one directory and the filesystem is not rolled back between them — if a method counts directory contents, give that method its own `MEDIA_ROOT` (see the existing example on `DownloadLetterTests.test_re_exporting_leaves_only_one_stored_file`).

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `home/views.py` | `renderCustom` quality persistence; `studentform2` atomicity; delete the `edit` view | 1, 4 |
| `templates/formTeacher.html` | Guard four `.url` dereferences | 2 |
| `templates/Teacher.html`, `profileUpdate.html`, `userDetails.html`, `studentDetails.html` | Same guard, other templates | 2 |
| `static/fonts/dejavu/` (**new**) | A Unicode TTF for PDF export | 3 |
| `home/letters.py` | Register the Unicode font in `build_pdf_bytes` | 3 |
| `home/urls.py` | Drop the `edit` route | 4 |
| `templates/test.html`, `print.html`, `testing.html` | Delete (orphaned) | 4 |
| `.gitignore` | Ignore `googleform-ss/` | 5 |
| `home/tests.py` | New test classes | 1–4 |

---

## Task 1: Stop discarding the professor's checkbox input

**Files:**
- Modify: `home/views.py` (`renderCustom`, the `Qualities.objects.filter(...).update(...)` call)
- Modify: `home/views.py` (`studentform2`, lines ~837-852)
- Test: `home/tests.py`

**The bug:** `renderCustom` persists the professor's quality checkboxes with
`Qualities.objects.filter(application=application).update(...)`. `.update()` on an empty
queryset updates zero rows and raises nothing, so when an `Application` has no `Qualities`
row the professor's input is silently discarded — 200 OK, nothing saved, no error.

**Is it reachable?** Yes. `studentform2` (`views.py:849-852`) deletes the existing `Qualities`
row *before* saving the replacement, with no transaction around it. If the save raises, the
Application is left permanently `Qualities`-less. Rows created through the Django admin
(`home/admin.py` registers `Application` and `Qualities` separately) also lack one. The
existing test `RenderCustomViewTests.test_an_application_with_no_satellite_rows_still_previews`
already exercises an application in exactly this state — it asserts the 200 but never checks
that anything persisted.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class QualityPersistenceTests(TestCase):
    """The professor's checkbox input must survive a missing Qualities row."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.teacher = TeacherInfo.objects.create(
            name="Prof P", unique_id="T-P", email="p@example.com", department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="Quality Student", roll_number="080BCT770", department=self.dept,
            program=self.program, password="x", dob="2000-01-01", gender="Male",
        )
        self.application = Application.objects.create(
            name="Quality Student", std=self.student, professor=self.teacher,
            subjects="Networks",
        )
        self.tpl = CustomTemplates.objects.create(
            template_name="Q", template="{{ app.name }}", professor=self.teacher,
        )
        self.client.cookies["unique"] = "T-P"

    def _post(self, **extra):
        payload = {"roll": "080BCT770", "template_id": self.tpl.pk}
        payload.update(extra)
        return self.client.post("/renderCustom", payload)

    def test_qualities_are_saved_when_no_row_exists_yet(self):
        # This is the data-loss case: .update() on an empty queryset is a silent no-op.
        self.assertFalse(Qualities.objects.filter(application=self.application).exists())
        self._post(quality1="on", quality2="on", qual="diligent")
        quality = Qualities.objects.get(application=self.application)
        self.assertTrue(quality.leadership)
        self.assertTrue(quality.hardworking)
        self.assertFalse(quality.social)
        self.assertEqual(quality.quality, "diligent")

    def test_qualities_are_updated_when_a_row_already_exists(self):
        Qualities.objects.create(application=self.application, leadership=True)
        self._post(quality2="on", qual="thorough")
        quality = Qualities.objects.get(application=self.application)
        self.assertFalse(quality.leadership)
        self.assertTrue(quality.hardworking)
        self.assertEqual(quality.quality, "thorough")

    def test_no_duplicate_qualities_row_is_created(self):
        self._post(quality1="on")
        self._post(quality2="on")
        self.assertEqual(
            Qualities.objects.filter(application=self.application).count(), 1
        )

    def test_an_existing_extracurricular_value_is_preserved(self):
        # ``extracirricular`` comes from the student's intake form and is not
        # part of the professor's checkbox set; updating must not clear it.
        Qualities.objects.create(
            application=self.application, extracirricular="Robotics club",
        )
        self._post(quality1="on")
        quality = Qualities.objects.get(application=self.application)
        self.assertEqual(quality.extracirricular, "Robotics club")
        self.assertTrue(quality.leadership)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.QualityPersistenceTests -v2`
Expected: FAIL — `test_qualities_are_saved_when_no_row_exists_yet` raises
`Qualities.DoesNotExist`, because `.update()` silently created nothing.

- [ ] **Step 3: Replace the `.update()` with `update_or_create`**

In `home/views.py`, inside `renderCustom`, replace:

```python
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
```

with:

```python
    # ``update_or_create`` rather than ``filter().update()``: an application with
    # no Qualities row would silently discard everything the professor ticked.
    Qualities.objects.update_or_create(
        application=application,
        defaults={
            "leadership": request.POST.get("quality1") == "on",
            "hardworking": request.POST.get("quality2") == "on",
            "social": request.POST.get("quality3") == "on",
            "teamwork": request.POST.get("quality4") == "on",
            "friendly": request.POST.get("quality5") == "on",
            "quality": request.POST.get("qual"),
            "presentation": request.POST.get("presentation"),
            "recommend": request.POST.get("recommend"),
        },
    )
```

`defaults` is applied on both the create and the update path, and fields not listed
(`extracirricular`, `recommendation_strength`) are left untouched on update — which is what
`test_an_existing_extracurricular_value_is_preserved` pins.

**Watch out:** `update_or_create` raises `MultipleObjectsReturned` if two `Qualities` rows
share an application. Nothing enforces uniqueness on that FK. Before implementing, run:

```bash
venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','auth.settings')
django.setup()
from django.db.models import Count
from home.models import Qualities
dupes = (Qualities.objects.values('application')
         .annotate(n=Count('id')).filter(n__gt=1))
print('applications with duplicate Qualities rows:', list(dupes))
"
```

If that prints any rows, **stop and report** — the fix needs a dedup step first and I want to
decide that rather than have you guess.

- [ ] **Step 4: Make `studentform2`'s delete-then-recreate atomic**

This is what creates the `Qualities`-less state in the first place. In `home/views.py`,
`studentform2` currently does (around lines 837-852):

```python
        qualities_info = Qualities(
            ...
            extracirricular = extra,
            application = info ,
        )
        
        if Qualities.objects.filter(application = info ).exists():
            quality = Qualities.objects.get(application = info )
            quality.delete()
            
        qualities_info.save()
```

Wrap the delete-and-recreate so a failure cannot leave the row deleted. Add
`from django.db import transaction` to the imports at the top of `home/views.py` (verify it
is absent first), then:

```python
        qualities_info = Qualities(
            extracirricular = extra,
            application = info ,
        )

        # Delete-then-recreate must be atomic: a failure between the two used to
        # leave the application permanently without a Qualities row.
        with transaction.atomic():
            Qualities.objects.filter(application=info).delete()
            qualities_info.save()
```

Note the commented-out field assignments in the original are dead and can go with it. Leave
the `Files` and `Academics` blocks above alone — they have the same pattern, but changing them
is out of scope for this task and I would rather do it deliberately than as a drive-by.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.QualityPersistenceTests home.tests.RenderCustomViewTests home.tests.Studentform2PostTests -v2`
Expected: `OK`. `Studentform2PostTests` covers the view you changed in Step 4.

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "fix(letters): persist professor quality input when no row exists yet"
```

---

## Task 2: Guard every unprotected `.url` dereference

**Files:**
- Modify: `templates/formTeacher.html` (lines 2, 7, 49, 51, 72, 90, 92, 113)
- Modify: `templates/Teacher.html:4`, `templates/profileUpdate.html:3,11`, `templates/userDetails.html:4,12`, `templates/studentDetails.html:4`
- Test: `home/tests.py`

**The bug:** Django's `FieldFile.url` raises `ValueError: The 'X' attribute has no file
associated with it` when no file is attached. Any student who skipped an upload makes the
letter form 500 — with `DEBUG=True` that is a full traceback to the caller.

**The subtle one:** `formTeacher.html:49` reads
`{% if files.transcript.url|lower|slice:'-4:' == '.pdf' %}`. The guard *is itself* the
dereference — `.url` is evaluated to build the condition, so it raises before the `{% if %}`
can protect anything. Same at `:90` for `files.CV`. These need an outer `{% if files.transcript %}`
wrapper, not a tweak to the condition.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py` (add `import tempfile` and `from django.test import override_settings` at the top if absent):

```python
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MissingUploadTests(TestCase):
    """A student who skipped an upload must not 500 the letter form."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.teacher = TeacherInfo.objects.create(
            name="Prof R", unique_id="T-R", email="r@example.com", department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="No Upload", roll_number="080BCT880", department=self.dept,
            program=self.program, password="x", dob="2000-01-01", gender="Female",
        )
        self.application = Application.objects.create(
            name="No Upload", std=self.student, professor=self.teacher, subjects="Maths",
        )
        Paper.objects.create(application=self.application)
        Project.objects.create(application=self.application)
        University.objects.create(
            application=self.application, uni_name="MIT", country="USA",
        )
        Qualities.objects.create(application=self.application)
        Academics.objects.create(application=self.application)
        # Every file field left empty - the case that used to crash.
        Files.objects.create(application=self.application)
        self.user = User.objects.create_user(username="profr", password="pw")
        self.user.first_name = "Prof R/T-R"
        self.user.save()
        self.client.force_login(self.user)
        self.client.cookies["unique"] = "T-R"

    def test_the_letter_form_renders_without_any_uploads(self):
        response = self.client.post("/makeLetter", {"roll": "080BCT880"})
        self.assertEqual(response.status_code, 200)

    def test_the_dashboard_renders_without_a_teacher_photo(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)

    def test_a_present_upload_still_renders_its_link(self):
        from django.core.files.base import ContentFile
        files = Files.objects.get(application=self.application)
        files.transcript.save("transcript.pdf", ContentFile(b"%PDF-1.4 fake"), save=True)
        response = self.client.post("/makeLetter", {"roll": "080BCT880"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "transcript")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.MissingUploadTests -v2`
Expected: FAIL — `ValueError: The 'Photo' attribute has no file associated with it`
(or `transcript`, depending on which template line is reached first).

- [ ] **Step 3: Guard `templates/formTeacher.html`**

Line 2 — wrap the teacher photo:
```html
{% block teacher %}<a href="teacher">{% if teacher_model.images %}<img src="{{ teacher_model.images.url }}" alt="" class="user-photo">{% endif %}</a>{% endblock teacher %}
```
Read the real line first and preserve whatever attributes and classes it already carries;
only add the `{% if %}` wrapper.

Line 7 — wrap the student photo:
```html
{% if files.Photo %}<img src="{{ files.Photo.url }}" class="rounded mx-auto d-block" height="100px" width="100px">{% endif %}
```

Lines 49-72 — wrap the whole transcript block in an outer existence check, so `.url` is never
evaluated when the field is empty:
```html
{% if files.transcript %}
  {% if files.transcript.url|lower|slice:'-4:' == '.pdf' %}
    ... existing PDF branch, unchanged ...
  {% else %}
    ... existing non-PDF branch, unchanged ...
  {% endif %}
{% else %}
  <p>No transcript uploaded.</p>
{% endif %}
```

Lines 90-113 — the identical treatment for `files.CV`, with `<p>No CV uploaded.</p>` as the
empty branch.

Read the real markup before editing; keep every existing attribute, class and inner element
exactly as it is. You are only adding wrappers.

- [ ] **Step 4: Guard the other templates**

Apply the same `{% if <field> %}...{% endif %}` wrapper to:
- `templates/Teacher.html:4` — `{{ teacher_model.images.url }}`
- `templates/profileUpdate.html:3` and `:11` — `{{ teacher.images.url }}`
- `templates/userDetails.html:4` and `:12` — `{{ teacher.images.url }}`
- `templates/studentDetails.html:4` — `{{ teacher.images.url }}`

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.MissingUploadTests home.tests.MakeLetterTemplateListTests home.tests.TeacherDashboardViewTests -v2`
Expected: `OK`. The latter two cover the templates you touched.

- [ ] **Step 6: Commit**

```bash
git add templates/ home/tests.py
git commit -m "fix(templates): render the letter form when a student skipped an upload"
```

---

## Task 3: Unicode PDF export

**Files:**
- Create: `static/fonts/dejavu/DejaVuSans.ttf` (downloaded)
- Modify: `home/letters.py` (`build_pdf_bytes`)
- Test: `home/tests.py`

**The bug:** `fpdf` core fonts are Latin-1 only, so `build_pdf_bytes` replaces every
unsupported character with `?`. For a Tribhuvan University app that means a student named
`राम बहादुर श्रेष्ठ` gets a PDF reading `??? ?????? ???????` — silently, with no warning.

**The fix:** `fpdf==1.7.2` supports `add_font(family, style, fname, uni=True)` with TrueType
subsetting. This is a font registration, not an engine change. The repo already has TTFs at
`static/fonts/poppins/` but only Bold/Black/ExtraBold weights and no Devanagari coverage, so
they are not usable here.

- [ ] **Step 1: Obtain a Unicode font**

DejaVu Sans covers Latin, Greek, Cyrillic and is the conventional `uni=True` choice. It does
**not** cover Devanagari — for that you need Noto Sans Devanagari. Get both:

```bash
mkdir -p static/fonts/dejavu
curl -L -o static/fonts/dejavu/DejaVuSans.ttf \
  https://github.com/dejavu-fonts/dejavu-fonts/raw/version_2_37/ttf/DejaVuSans.ttf
ls -la static/fonts/dejavu/
```

Expected: a file of roughly 700 KB.

**If the download fails or the network is unavailable, STOP and report** — do not fall back to
a font that lacks the coverage, and do not silently skip the task. I will supply the file.

Verify it is a real TrueType file before going further:
```bash
file static/fonts/dejavu/DejaVuSans.ttf
```
Expected: `TrueType Font data` (not `HTML document`, which is what a failed redirect gives you).

- [ ] **Step 2: Write the failing test**

Append to `home/tests.py`:

```python
class UnicodePdfTests(TestCase):
    """Non-Latin-1 text must survive PDF export (FR-1)."""

    def test_an_em_dash_is_preserved_not_replaced(self):
        from home.letters import build_pdf_bytes
        data = build_pdf_bytes("A — B")
        self.assertTrue(data.startswith(b"%PDF"))

    def test_a_devanagari_name_does_not_become_question_marks(self):
        # The whole point: a Nepali student's name must be readable.
        from home.letters import build_pdf_bytes
        name = "राम बहादुर"
        data = build_pdf_bytes(f"I recommend {name} warmly.")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertNotIn(b"???", data)

    def test_curly_quotes_survive(self):
        from home.letters import build_pdf_bytes
        self.assertTrue(build_pdf_bytes("“Quoted”").startswith(b"%PDF"))

    def test_plain_ascii_still_works(self):
        from home.letters import build_pdf_bytes
        self.assertTrue(build_pdf_bytes("Dear Committee,\n\nRegards").startswith(b"%PDF"))

    def test_the_seeded_templates_still_export(self):
        from home.letters import build_pdf_bytes, render_letter
        dept = Department.objects.create(dept_name="BCT")
        program = Program.objects.create(program_name="BE-BCT", department=dept)
        teacher = TeacherInfo.objects.create(
            name="Prof U", unique_id="T-U", email="u@example.com", department=dept,
        )
        student = StudentLoginInfo.objects.create(
            username="Uni Student", roll_number="080BCT900", department=dept,
            program=program, password="x", dob="2000-01-01", gender="Female",
        )
        application = Application.objects.create(
            name="Uni Student", std=student, professor=teacher, subjects="Physics",
        )
        for tpl in CustomTemplates.objects.filter(is_system=True):
            with self.subTest(name=tpl.template_name):
                letter = render_letter(application, tpl)
                self.assertTrue(build_pdf_bytes(letter).startswith(b"%PDF"))
```

The `assertNotIn(b"???", data)` assertion is the real check: with the old Latin-1 path the
replacement characters appear in the content stream; with an embedded Unicode font they do not.
Verify that claim by running the test against the *unchanged* code first — if `b"???"` does not
appear even before the fix, the assertion is vacuous and you need a stronger one (look for
`FontFile2` in the output instead, which only appears once a TTF subset is embedded).

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.UnicodePdfTests -v2`
Expected: FAIL on `test_a_devanagari_name_does_not_become_question_marks` —
`b"???"` is found in the output.

- [ ] **Step 4: Register the font in `build_pdf_bytes`**

Replace `build_pdf_bytes` in `home/letters.py`:

```python
# fpdf's core fonts are Latin-1 only, which turns a Devanagari name into "???".
# A TrueType font registered with uni=True embeds a subset and handles Unicode.
_UNICODE_FONT_PATH = os.path.join(
    settings.BASE_DIR, "static", "fonts", "dejavu", "DejaVuSans.ttf"
)
_UNICODE_FONT_FAMILY = "DejaVu"


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
    # fpdf1 returns str, fpdf2 returns bytes/bytearray.
    if isinstance(output, str):
        return output.encode("latin-1")
    return bytes(output)
```

Add to the imports at the top of `home/letters.py` (check each is absent first):
```python
import os

from django.conf import settings
```

**Two things to verify, not assume:**

1. **`pdf.output(dest="S")` with a Unicode font.** In fpdf 1.7.2 the returned `str` may no
   longer be safely `.encode("latin-1")` once a TTF is embedded, because the content stream
   contains the subset. Test it. If it raises `UnicodeEncodeError`, the correct call is
   `pdf.output(dest="S").encode("latin-1", "replace")` — no; that would corrupt the font data.
   The right fix is to write to a temp file with `pdf.output(path)` and read the bytes back.
   **Work out which is correct and tell me what you did.**

2. **The font cache.** `add_font(uni=True)` writes a `.pkl` cache file next to the `.ttf`.
   On a read-only deployment that fails. Check whether 1.7.2 lets you set the cache directory
   (`FPDF(..., font_cache_dir=...)` exists in fpdf2; 1.7.2 may use `fpdf.set_global`). Report
   what you find. If the cache is unavoidable, add `static/fonts/**/*.pkl` to `.gitignore`.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.UnicodePdfTests home.tests.LetterExportTests home.tests.DownloadLetterTests -v2`
Expected: `OK`.

**`LetterExportTests` currently contains `test_non_latin1_characters_are_replaced_not_crashed`
and `test_curly_quotes_do_not_crash_the_pdf`.** Those assert the *old* replacement behaviour.
They should still pass (both only assert `startswith(b"%PDF")`), but read them and confirm
neither asserts that a `?` appears. If one does, update it — the behaviour it pinned is the
bug we are fixing. Report what you changed.

- [ ] **Step 6: Verify the PDF is actually readable**

```bash
venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','auth.settings')
django.setup()
from home.letters import build_pdf_bytes
open('/tmp/unicode_check.pdf','wb').write(
    build_pdf_bytes('Recommendation for राम बहादुर\n\nRegards — Prof.')
)
print('written')
"
pdftotext /tmp/unicode_check.pdf - 2>/dev/null || echo "pdftotext not installed"
```

If `pdftotext` is available, the Devanagari and the em dash must appear in the extracted text.
If it is not installed, say so plainly in your report rather than claiming the PDF renders —
this is the one thing the automated tests cannot fully prove.

- [ ] **Step 7: Update the README note**

`README.md` carries a note added in Phase 3 stating that non-Latin-1 characters are replaced
with `?` in the PDF. Find it and replace it with:

```markdown
> **Note on PDF export.** Letters are rendered with an embedded DejaVu Sans subset, so accented
> Latin, Greek and Cyrillic text exports correctly. Devanagari requires a font with Devanagari
> coverage — drop a suitable TTF into `static/fonts/` and point `_UNICODE_FONT_PATH` in
> `home/letters.py` at it. If the font file is missing entirely the exporter falls back to
> Latin-1 and replaces unsupported characters with `?`.
```

Adjust the wording to match whatever coverage the font you actually shipped provides — if you
were able to obtain a Devanagari-capable font, say so instead.

- [ ] **Step 8: Commit**

```bash
git add static/fonts/ home/letters.py home/tests.py README.md .gitignore
git commit -m "feat(letters): embed a unicode font so non-latin names export correctly"
```

---

## Task 4: Delete the orphans — including a live unauthenticated write endpoint

**Files:**
- Modify: `home/views.py` (delete `edit`, delete `testing`)
- Modify: `home/urls.py:42` (delete the `edit` route)
- Delete: `templates/test.html`, `templates/print.html`
- Modify: `templates/formTeacher.html:322` (stale comment)
- Test: `home/tests.py`

**Why this is a security fix, not tidying.** `edit` is routed at `home/urls.py:42` and reads
`request.COOKIES.get("unique")` **unguarded** (`views.py:1457`), then writes to the database.
No template posts to it any more — Phase 3 removed the JS that did — but the route is still
live, so it is an unauthenticated write endpoint reachable by anyone who knows the path.

Confirmed orphaned by survey:
- `edit` view + `urls.py:42` + `templates/test.html` (rendered only by `edit`)
- `templates/print.html` — zero references anywhere
- `testing` view (`views.py:1551`) — no URL entry, and it renders `templates/testing.html`
  **which does not exist**; it would `NameError` on `textarea` for a GET regardless

- [ ] **Step 1: Verify the orphan status yourself**

```bash
grep -rn "views.edit\|'edit'\|\"edit\"\|url 'edit'" home/urls.py templates/ home/*.py
grep -rn "test\.html\|print\.html\|testing\.html\|views.testing" home/ templates/ --include=*.py --include=*.html
```

Expected: `edit` appears only in `home/urls.py:42` and its own definition; `test.html` only in
`views.py`'s `edit` and in prose comments at `customTemplate.html:9,11`; `print.html` and
`testing.html` nowhere.

**If anything else references them, STOP and report rather than deleting.**

- [ ] **Step 2: Write the failing test**

Append to `home/tests.py`:

```python
class RemovedEndpointTests(TestCase):
    """Dead endpoints are gone, not merely unlinked."""

    def test_the_edit_endpoint_no_longer_exists(self):
        # It was routed, unguarded, and wrote to the database.
        self.assertEqual(self.client.post("/edit", {"roll": "x"}).status_code, 404)

    def test_the_edit_view_is_gone(self):
        from home import views
        self.assertFalse(hasattr(views, "edit"))

    def test_the_testing_view_is_gone(self):
        from home import views
        self.assertFalse(hasattr(views, "testing"))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.RemovedEndpointTests -v2`
Expected: FAIL — `/edit` returns 500 or 302 rather than 404, and both `hasattr` checks pass.

- [ ] **Step 4: Delete the code**

- Remove the whole `edit` function from `home/views.py` (starts at `views.py:1454`, ends at the
  `return render(request, "test.html", {...})` block around `:1533`). Check what immediately
  follows and make sure you do not take a neighbouring function or its decorator with it — this
  has nearly gone wrong twice on this project.
- Remove the whole `testing` function (`views.py:1551`).
- Remove `path('edit', views.edit, name='edit'),` from `home/urls.py:42`.
- `git rm templates/test.html templates/print.html`
- At `templates/formTeacher.html:322`, the comment reads
  `<!-- The picker used to reroute the form to /edit for the magic "default" ... -->`.
  Update it so it does not refer to a route that no longer exists, or delete it.

After deleting, run `venv/bin/python manage.py check` — expect `System check identified no issues`.

- [ ] **Step 5: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.RemovedEndpointTests home.tests.RenderCustomViewTests -v2`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/urls.py templates/ home/tests.py
git commit -m "fix(security): remove the unauthenticated /edit write endpoint and dead templates"
```

---

## Task 5: Ignore the scratch directory

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Check what is in there first**

```bash
ls -la googleform-ss/ | head -20
du -sh googleform-ss/
```

Report what you find. If it contains anything that looks like source code rather than
screenshots or scratch material, **stop and tell me** before ignoring it.

- [ ] **Step 2: Add the entry**

In `.gitignore`, directly under the existing `CLAUDE.md` block at the top:

```
# Local scratch: Google Form screenshots, not part of the app
googleform-ss/
```

- [ ] **Step 3: Verify**

```bash
git status --porcelain
```
Expected: `googleform-ss/` no longer appears as untracked. `db.sqlite3` may still show as
modified — that is expected and must stay unstaged.

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: ignore the local googleform screenshots directory"
```

---

## Task 6: Full-suite verification

- [ ] **Step 1: Run the whole suite**

```bash
venv/bin/python manage.py test home -v2
```
Expected: `OK`. Baseline was 229; this plan adds roughly 17, so expect ~246. Tests that
deliberately exercise 404 paths log `[WARNING] Not Found: ...` — expected output, not failures.

- [ ] **Step 2: Confirm no migration drift**

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: `No changes detected`. This plan adds no model changes, so any output here means
something unintended happened.

- [ ] **Step 3: Update the README test count**

Set the number on the `python manage.py test home` line in `README.md` to the exact count from
Step 1.

- [ ] **Step 4: Commit hygiene check**

```bash
git log --format='%H %s%n%b' main..HEAD | grep -ci "co-authored-by\|claude\|generated with"
git status --porcelain | grep -c "CLAUDE.md"
```
Expected: `0` from both.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: update the test count"
```

---

## Notes for the reviewer

Probe these specifically:

1. **`update_or_create` and the `defaults` semantics.** Confirm that a field NOT in `defaults`
   (`extracirricular`, `recommendation_strength`) survives an update, and that a second POST
   does not create a duplicate row. Try an application that already has two `Qualities` rows
   and report what happens.
2. **The `.url` guards.** The `formTeacher.html:49`/`:90` cases are the subtle ones — the old
   guard was itself the dereference. Construct an application with transcript present but CV
   absent, and vice versa, and confirm both render.
3. **The PDF font.** Verify the bytes actually contain an embedded font subset rather than a
   silent fallback — check for `FontFile2` in the PDF. Then confirm the fallback branch still
   works by temporarily renaming the TTF.
4. **`/edit` is genuinely gone**, not just 404-ing because of a URL typo. Confirm the view
   object no longer exists and that nothing else imported it.
5. **Nothing else regressed** — the full suite is the backstop, but check specifically that the
   Phase 3 letter-generation flow still works end to end.
