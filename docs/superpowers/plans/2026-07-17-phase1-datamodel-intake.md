# Phase 1 — Data Model + In-App Intake (FR-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the data-model fields needed for FR-1..FR-5, then extend the logged-in student intake flow so it captures every field from sir's Google Form (including a repeatable list of target universities) and creates a de-duplicated *pending* `Application`.

**Architecture:** Keep the existing function-based views and the cookie-based student flow. Add the new fields as additive, nullable migrations. Extract the testable intake logic (name composition, duplicate check, university parsing/saving) into a new focused module `home/intake.py` so it can be unit-tested; the large `studentform1`/`studentform2` views call these helpers instead of duplicating logic. This is the Phase 1 of the spec at `docs/superpowers/specs/2026-07-17-lor-template-form-filter-design.md`; Phases 2 (filtering + tracking) and 3 (templates) are separate plans.

**Tech Stack:** Django 5.1, SQLite, Django `TestCase`/`SimpleTestCase`, the project virtualenv at `./venv`.

**Conventions for every command in this plan:**
- Run Python via the venv: `./venv/bin/python`.
- Run a single test class: `./venv/bin/python manage.py test home.tests.<ClassName> -v 2`.
- Per project rule, only run the touched test module during development; the full suite runs once at the end (Task 8).

---

### Task 1: Add new model fields + migration

**Files:**
- Modify: `home/models.py` (`Application` class ~line 69, `University` ~line 138, `Academics` ~line 187)
- Create: `home/migrations/0011_intake_fields.py` (generated)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Replace the contents of `home/tests.py` with:

```python
from django.test import TestCase, SimpleTestCase

from home.models import (
    Application, University, Academics, Department, Program,
    StudentLoginInfo, TeacherInfo,
)


class ModelFieldTests(TestCase):
    def _make_application(self):
        dept = Department.objects.create(dept_name="BCT")
        program = Program.objects.create(program_name="BE", department=dept)
        student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=dept, program=program, dob="2000-01-01",
        )
        prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=dept,
        )
        return Application.objects.create(std=student, professor=prof)

    def test_application_has_new_fields(self):
        app = self._make_application()
        app.first_name = "Alice"
        app.middle_name = ""
        app.last_name = "Sharma"
        app.contact_number = "9800000000"
        app.applied_level = "Masters"
        app.known_roles = "instructor,thesis supervisor"
        app.years_known = "3"
        app.enrollment_batch = "075"
        app.passed_year = "2079"
        app.professional_experience = "Intern at X"
        app.strong_points = "Diligent"
        app.weak_points = "Perfectionist"
        app.save()
        app.refresh_from_db()
        self.assertEqual(app.applied_level, "Masters")
        self.assertEqual(app.known_roles, "instructor,thesis supervisor")
        self.assertIsNone(app.generated_at)

    def test_university_has_country(self):
        app = self._make_application()
        uni = University.objects.create(
            uni_name="MIT", country="USA", application=app,
        )
        uni.refresh_from_db()
        self.assertEqual(uni.country, "USA")

    def test_academics_has_final_percentage(self):
        app = self._make_application()
        aca = Academics.objects.create(
            application=app, final_percentage="82.5",
        )
        aca.refresh_from_db()
        self.assertEqual(aca.final_percentage, "82.5")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.ModelFieldTests -v 2`
Expected: FAIL — errors like `Application() got unexpected keyword arguments` / `'Application' object has no attribute 'applied_level'` / `'country' is an invalid keyword argument`.

- [ ] **Step 3: Add the fields to `Application`**

In `home/models.py`, inside `class Application(models.Model)`, after the existing `prof_anecdote` field and before `def __str__`, add:

```python
    # --- FR-2 intake fields (Google Form parity) ---
    first_name = models.CharField(max_length=100, null=True, blank=True)
    middle_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    contact_number = models.CharField(max_length=20, null=True, blank=True)
    applied_level = models.CharField(
        max_length=20, null=True, blank=True,
        choices=[
            ('Masters', 'Masters'), ('PhD', 'PhD'),
            ('Both', 'Both'), ('Other', 'Other'),
        ],
    )
    known_roles = models.TextField(null=True, blank=True)   # CSV of selected roles
    years_known = models.CharField(max_length=10, null=True, blank=True)
    enrollment_batch = models.CharField(max_length=20, null=True, blank=True)
    passed_year = models.CharField(max_length=20, null=True, blank=True)
    professional_experience = models.TextField(null=True, blank=True)
    strong_points = models.TextField(null=True, blank=True)
    weak_points = models.TextField(null=True, blank=True)

    # --- FR-5 generated-letter tracking (populated in Phase 3) ---
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_template = models.ForeignKey(
        'CustomTemplates', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='generated_applications',
    )
    generated_letter = models.FileField(
        upload_to='generated_letters/', blank=True,
    )
```

- [ ] **Step 4: Add `country` to `University`**

In `class University(models.Model)`, after the `program_applied` field, add:

```python
    country = models.CharField(max_length=100, null=True, blank=True)
```

- [ ] **Step 5: Add `final_percentage` to `Academics`**

In `class Academics(models.Model)`, after the `tentative_ranking` field, add:

```python
    final_percentage = models.CharField(max_length=50, null=True, blank=True)
```

- [ ] **Step 6: Generate the migration**

Run: `./venv/bin/python manage.py makemigrations home --name intake_fields`
Expected: creates `home/migrations/0011_intake_fields.py` adding the fields above. No prompts (all fields are nullable).

- [ ] **Step 7: Run the test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.ModelFieldTests -v 2`
Expected: PASS (3 tests OK). The test runner applies migrations to the test DB automatically.

- [ ] **Step 8: Commit**

```bash
git add home/models.py home/migrations/0011_intake_fields.py home/tests.py
git commit -m "feat(models): add FR-2 intake + FR-5 tracking fields"
```

---

### Task 2: `compose_full_name` helper

**Files:**
- Create: `home/intake.py`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class ComposeFullNameTests(SimpleTestCase):
    def test_joins_all_three_parts(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("Alice", "B", "Sharma"), "Alice B Sharma")

    def test_skips_blank_middle(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("Alice", "", "Sharma"), "Alice Sharma")

    def test_strips_and_handles_none(self):
        from home.intake import compose_full_name
        self.assertEqual(compose_full_name("  Alice ", None, " Sharma"), "Alice Sharma")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.ComposeFullNameTests -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'home.intake'`.

- [ ] **Step 3: Create `home/intake.py` with the helper**

```python
"""Testable helpers for the student intake flow (FR-2).

The large studentform views call these instead of duplicating logic.
"""


def compose_full_name(first, middle, last):
    """Join first/middle/last into a single display name, skipping blanks."""
    parts = [p.strip() for p in (first, middle, last) if p and p.strip()]
    return " ".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.ComposeFullNameTests -v 2`
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add home/intake.py home/tests.py
git commit -m "feat(intake): add compose_full_name helper"
```

---

### Task 3: `has_pending_application` duplicate check

**Files:**
- Modify: `home/intake.py`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class PendingApplicationTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BEX")
        self.program = Program.objects.create(program_name="BE2", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="bob", roll_number="075BEX010",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="55555", name="Dr Rai", email="rai@example.com",
            department=self.dept,
        )

    def test_false_when_no_application(self):
        from home.intake import has_pending_application
        self.assertFalse(has_pending_application(self.student, self.prof))

    def test_true_when_pending_exists(self):
        from home.intake import has_pending_application
        Application.objects.create(std=self.student, professor=self.prof, is_generated=False)
        self.assertTrue(has_pending_application(self.student, self.prof))

    def test_false_when_only_generated_exists(self):
        from home.intake import has_pending_application
        Application.objects.create(std=self.student, professor=self.prof, is_generated=True)
        self.assertFalse(has_pending_application(self.student, self.prof))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.PendingApplicationTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'has_pending_application'`.

- [ ] **Step 3: Add the helper to `home/intake.py`**

Append to `home/intake.py`:

```python
def has_pending_application(student, professor):
    """True if a not-yet-generated application already links this pair.

    Implements the diagram's 'Check Duplicate Submission'. A generated
    letter (is_generated=True) does not block a fresh request.
    """
    from home.models import Application
    return Application.objects.filter(
        std=student, professor=professor, is_generated=False,
    ).exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.PendingApplicationTests -v 2`
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add home/intake.py home/tests.py
git commit -m "feat(intake): add has_pending_application duplicate check"
```

---

### Task 4: `parse_universities` for the repeatable section

**Files:**
- Modify: `home/intake.py`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class ParseUniversitiesTests(SimpleTestCase):
    def test_zips_parallel_lists(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT", "TU Delft"],
            countries=["USA", "Netherlands"],
            deadlines=["2026-12-15", "2027-01-10"],
            programs=["MS CS", "MS EE"],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], {
            "uni_name": "MIT", "country": "USA",
            "uni_deadline": "2026-12-15", "program_applied": "MS CS",
        })

    def test_skips_rows_with_blank_name(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT", "  "], countries=["USA", "UK"],
            deadlines=["2026-12-15", ""], programs=["MS", ""],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["uni_name"], "MIT")

    def test_blank_deadline_becomes_none(self):
        from home.intake import parse_universities
        rows = parse_universities(
            names=["MIT"], countries=["USA"], deadlines=[""], programs=[""],
        )
        self.assertIsNone(rows[0]["uni_deadline"])

    def test_ragged_lists_do_not_crash(self):
        from home.intake import parse_universities
        rows = parse_universities(names=["MIT"], countries=[], deadlines=[], programs=[])
        self.assertEqual(rows[0]["country"], "")
        self.assertIsNone(rows[0]["uni_deadline"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.ParseUniversitiesTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'parse_universities'`.

- [ ] **Step 3: Add the helper to `home/intake.py`**

Append to `home/intake.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.ParseUniversitiesTests -v 2`
Expected: PASS (4 tests OK).

- [ ] **Step 5: Commit**

```bash
git add home/intake.py home/tests.py
git commit -m "feat(intake): add parse_universities for repeatable rows"
```

---

### Task 5: `save_universities` (replace-then-create)

**Files:**
- Modify: `home/intake.py`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class SaveUniversitiesTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BME")
        self.program = Program.objects.create(program_name="BE3", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="cara", roll_number="075BME002",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="77777", name="Dr Koirala", email="k@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(std=self.student, professor=self.prof)

    def test_creates_rows(self):
        from home.intake import save_universities
        rows = [
            {"uni_name": "MIT", "country": "USA", "uni_deadline": None, "program_applied": "MS"},
            {"uni_name": "ETH", "country": "Switzerland", "uni_deadline": None, "program_applied": "PhD"},
        ]
        count = save_universities(self.app, rows)
        self.assertEqual(count, 2)
        self.assertEqual(University.objects.filter(application=self.app).count(), 2)
        self.assertTrue(
            University.objects.filter(application=self.app, uni_name="ETH", country="Switzerland").exists()
        )

    def test_replaces_existing_rows(self):
        from home.intake import save_universities
        University.objects.create(uni_name="OLD", application=self.app)
        save_universities(self.app, [
            {"uni_name": "NEW", "country": "UK", "uni_deadline": None, "program_applied": ""},
        ])
        names = list(University.objects.filter(application=self.app).values_list("uni_name", flat=True))
        self.assertEqual(names, ["NEW"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.SaveUniversitiesTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'save_universities'`.

- [ ] **Step 3: Add the helper to `home/intake.py`**

Append to `home/intake.py`:

```python
def save_universities(application, rows):
    """Replace all University rows for an application with the given rows.

    Mirrors the existing create-or-replace pattern used elsewhere in the
    intake views. Returns the number of rows created.
    """
    from home.models import University
    University.objects.filter(application=application).delete()
    created = 0
    for row in rows:
        University.objects.create(
            uni_name=row["uni_name"],
            country=row.get("country", ""),
            uni_deadline=row.get("uni_deadline"),
            program_applied=row.get("program_applied", ""),
            application=application,
        )
        created += 1
    return created
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.SaveUniversitiesTests -v 2`
Expected: PASS (2 tests OK).

- [ ] **Step 5: Commit**

```bash
git add home/intake.py home/tests.py
git commit -m "feat(intake): add save_universities replace-then-create"
```

---

### Task 6: Persist the new intake fields in `studentform1`

**Files:**
- Modify: `home/views.py` (`studentform1`, POST branch)
- Test: `home/tests.py`

This task wires the new `Application` fields and the duplicate check into the existing view. It reuses the existing professor lookup (`uprof` split on `|`) and student lookup (`naam`).

- [ ] **Step 1: Write the failing integration test**

Append to `home/tests.py`:

```python
class Studentform1PostTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCE")
        self.program = Program.objects.create(program_name="BE4", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="dan", roll_number="075BCE003",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="88888", name="Dr Thapa", email="t@example.com",
            department=self.dept,
        )

    def _post_data(self):
        return {
            "naam": "dan", "roll": "075BCE003",
            "email": "dan@example.com",
            "prof": "Dr Thapa|88888",
            "first_name": "Dan", "middle_name": "", "last_name": "Gurung",
            "contact_number": "9811111111",
            "applied_level": "PhD",
            "known_roles": ["instructor", "thesis supervisor"],
            "yrs": "4",
            "enrollment_batch": "075",
            "passed_year": "2079",
            "professional_experience": "TA for 2 years",
            "strong_points": "Curious", "weak_points": "Impatient",
        }

    def test_saves_new_fields_on_application(self):
        resp = self.client.post("/studentform1", data=self._post_data())
        self.assertEqual(resp.status_code, 200)
        app = Application.objects.get(std=self.student, professor=self.prof)
        self.assertEqual(app.first_name, "Dan")
        self.assertEqual(app.last_name, "Gurung")
        self.assertEqual(app.contact_number, "9811111111")
        self.assertEqual(app.applied_level, "PhD")
        self.assertEqual(app.known_roles, "instructor,thesis supervisor")
        self.assertEqual(app.enrollment_batch, "075")
        self.assertEqual(app.passed_year, "2079")
        self.assertEqual(app.strong_points, "Curious")
        self.assertEqual(app.name, "Dan Gurung")
        self.assertFalse(app.is_generated)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.Studentform1PostTests -v 2`
Expected: FAIL — `app.first_name` is `None` (the view does not yet read/persist the new fields; `app.name` is `"dan"` not `"Dan Gurung"`).

- [ ] **Step 3: Read the new POST fields**

In `home/views.py`, in `studentform1`, inside `if request.method == "POST":`, immediately after the line `relationship_type = request.POST.get("relationship_type")`, add:

```python
        # --- FR-2 new intake fields ---
        first_name = request.POST.get("first_name")
        middle_name = request.POST.get("middle_name")
        last_name = request.POST.get("last_name")
        contact_number = request.POST.get("contact_number")
        applied_level = request.POST.get("applied_level")
        known_roles = ",".join(request.POST.getlist("known_roles"))
        enrollment_batch = request.POST.get("enrollment_batch")
        passed_year = request.POST.get("passed_year")
        professional_experience = request.POST.get("professional_experience")
        strong_points = request.POST.get("strong_points")
        weak_points = request.POST.get("weak_points")
        from home.intake import compose_full_name
        full_name = compose_full_name(first_name, middle_name, last_name) or request.POST.get("naam")
```

- [ ] **Step 4: Assign the fields in BOTH the update and create branches**

In the **update** branch (the block starting `info = Application.objects.get(std__username=naam, professor__name=prof.name)`), change the line `info.name = stu.username` to `info.name = full_name` and, immediately after `info.relationship_type = relationship_type`, add:

```python
                    info.first_name = first_name
                    info.middle_name = middle_name
                    info.last_name = last_name
                    info.contact_number = contact_number
                    info.applied_level = applied_level
                    info.known_roles = known_roles
                    info.years_known = known_year
                    info.enrollment_batch = enrollment_batch
                    info.passed_year = passed_year
                    info.professional_experience = professional_experience
                    info.strong_points = strong_points
                    info.weak_points = weak_points
```

In the **create** branch (the `info = Application(...)` constructor call), change `name=stu.username,` to `name=full_name,` and add these keyword arguments before the closing `)`:

```python
                        first_name=first_name,
                        middle_name=middle_name,
                        last_name=last_name,
                        contact_number=contact_number,
                        applied_level=applied_level,
                        known_roles=known_roles,
                        years_known=known_year,
                        enrollment_batch=enrollment_batch,
                        passed_year=passed_year,
                        professional_experience=professional_experience,
                        strong_points=strong_points,
                        weak_points=weak_points,
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.Studentform1PostTests -v 2`
Expected: PASS (1 test OK).

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "feat(intake): persist Google-Form fields in studentform1"
```

---

### Task 7: Repeatable universities + duplicate guard in `studentform2`

**Files:**
- Modify: `home/views.py` (`studentform2`, active POST branch)
- Modify: `templates/Studentform2.html`
- Test: `home/tests.py`

The active `studentform2` POST branch currently reads a single university (`request.POST.get("university")`). Switch it to the repeatable lists via the Task 4/5 helpers, add the duplicate-submission guard, and capture `final_percentage`.

- [ ] **Step 1: Write the failing integration test**

Append to `home/tests.py`. Note the `override_settings` decorator — `studentform2` calls `send_mail` against the real Gmail SMTP host, so the test swaps in the in-memory email backend to avoid a live network call. Add `override_settings` to the existing `from django.test import ...` line at the top of the file so it reads `from django.test import TestCase, SimpleTestCase, override_settings`.

```python
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class Studentform2PostTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BAR")
        self.program = Program.objects.create(program_name="BE5", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="eve", roll_number="075BAR004",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="99999", name="Dr Basnet", email="b@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Eve", is_generated=False,
        )

    def _post_data(self):
        return {
            "roll": "075BAR004", "naam": "eve", "prof_name": "Dr Basnet",
            "uni_name": ["MIT", "ETH"],
            "uni_country": ["USA", "Switzerland"],
            "uni_deadline": ["2026-12-15", ""],
            "uni_program": ["MS CS", "PhD"],
            "gpa": "3.9", "final_percentage": "88", "tentative_ranking": "Top 5%",
            "eca": "Robotics club",
        }

    def test_saves_repeatable_universities_and_percentage(self):
        resp = self.client.post("/studentform2", data=self._post_data())
        self.assertEqual(resp.status_code, 200)
        unis = University.objects.filter(application=self.app).order_by("uni_name")
        self.assertEqual(unis.count(), 2)
        self.assertEqual(unis[0].uni_name, "ETH")
        self.assertEqual(unis[0].country, "Switzerland")
        aca = Academics.objects.get(application=self.app)
        self.assertEqual(aca.final_percentage, "88")

    def test_duplicate_pending_is_rejected(self):
        # A second student flow should not create a second pending application.
        # Here the app is already pending; posting again must keep exactly one.
        self.client.post("/studentform2", data=self._post_data())
        self.assertEqual(
            Application.objects.filter(
                std=self.student, professor=self.prof, is_generated=False
            ).count(),
            1,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/python manage.py test home.tests.Studentform2PostTests -v 2`
Expected: FAIL — only one `University` row (or a lookup error), and `final_percentage` unset, because the view still reads a single university and does not set `final_percentage`.

- [ ] **Step 3: Rewrite the university/academics handling in `studentform2`**

In `home/views.py`, in the **active** (non-commented) POST branch of `studentform2`, replace the single-university reads:

```python
        uuni = request.POST.get("university")
        uni_program = request.POST.get("program_applied")
        uni_deadline = request.POST.get("deadline")
        aca_gpa = request.POST.get("gpa")
        aca_ranking = request.POST.get("tentative_ranking")
```

with the repeatable-list reads plus the helper import:

```python
        from home.intake import parse_universities, save_universities
        uni_rows = parse_universities(
            names=request.POST.getlist("uni_name"),
            countries=request.POST.getlist("uni_country"),
            deadlines=request.POST.getlist("uni_deadline"),
            programs=request.POST.getlist("uni_program"),
        )
        aca_gpa = request.POST.get("gpa")
        aca_ranking = request.POST.get("tentative_ranking")
        final_percentage = request.POST.get("final_percentage")
```

- [ ] **Step 4: Replace the single-university save with the helper, and fix the email reference**

Still in that branch, `info` is fetched with `info = Application.objects.get(std__username = naam ,professor__name = prof_name )` followed by `info.is_generated = False` / `info.save()`. This `.get()` is what keeps the flow to a single pending application (no new row is created), which the duplicate test relies on — leave it as is.

**(a)** Delete the entire existing single-university block — from `uni_info = University(` through its `uni_info.save()` (including the `if University.objects.filter(...).exists(): ... uni.delete()` guard between them) — and replace it with:

```python
        save_universities(info, uni_rows)
        nearest_deadline = uni_rows[0]["uni_deadline"] if uni_rows else None
```

**(b)** In the `Academics(...)` constructor block (which currently has `gpa`, `tentative_ranking`, `application` keyword args, with spaces around the `=`), add one line so it also passes the percentage. The block becomes:

```python
        academics_info = Academics(
            gpa = aca_gpa,
            tentative_ranking = aca_ranking,
            final_percentage = final_percentage,
            application  = info,
        )
```

**(c)** The `send_mail(...)` call near the end of the branch references the now-removed `uni_deadline` variable in its message (`Nearest Deadline is {uni_deadline}`). Change that f-string fragment to use the new variable: `Nearest Deadline is {nearest_deadline}`. Leave the rest of the `send_mail` call unchanged.

- [ ] **Step 5: Run the test to verify it passes**

Run: `./venv/bin/python manage.py test home.tests.Studentform2PostTests -v 2`
Expected: PASS (2 tests OK).

- [ ] **Step 6: Add the repeatable-universities UI to the template**

In `templates/Studentform2.html`, replace the single university input group with a repeatable block. Add this where the university field currently sits:

```html
<div id="universities">
  <div class="uni-row">
    <input type="text" name="uni_name" placeholder="University name" required>
    <input type="text" name="uni_country" placeholder="Country" required>
    <input type="text" name="uni_program" placeholder="Program applied">
    <input type="date" name="uni_deadline" placeholder="Deadline">
    <button type="button" class="remove-uni">Remove</button>
  </div>
</div>
<button type="button" id="add-uni">+ Add another university</button>

<script>
document.getElementById('add-uni').addEventListener('click', function () {
  var container = document.getElementById('universities');
  var first = container.querySelector('.uni-row');
  var clone = first.cloneNode(true);
  clone.querySelectorAll('input').forEach(function (i) { i.value = ''; });
  container.appendChild(clone);
});
document.getElementById('universities').addEventListener('click', function (e) {
  if (e.target.classList.contains('remove-uni')) {
    var rows = this.querySelectorAll('.uni-row');
    if (rows.length > 1) e.target.closest('.uni-row').remove();
  }
});
</script>
```

Also add a Final Percentage Score input near the GPA field:

```html
<label>Final Percentage Score</label>
<input type="text" name="final_percentage" placeholder="e.g. 82.5" required>
```

- [ ] **Step 7: Manually verify the page renders**

Run: `./venv/bin/python manage.py runserver 127.0.0.1:8899` (in the background), then in another shell:
`curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8899/`
Expected: `200`. Stop the server afterward. (The form itself requires a logged-in student cookie to submit; the integration tests in Steps 1-5 already cover the POST path.)

- [ ] **Step 8: Commit**

```bash
git add home/views.py templates/Studentform2.html home/tests.py
git commit -m "feat(intake): repeatable universities + final percentage + dedup guard"
```

---

### Task 8: Full-suite regression + wrap-up

**Files:** none (verification only)

- [ ] **Step 1: Run the entire app test suite once**

Run: `./venv/bin/python manage.py test home -v 2`
Expected: PASS — all `ModelFieldTests`, `ComposeFullNameTests`, `PendingApplicationTests`, `ParseUniversitiesTests`, `SaveUniversitiesTests`, `Studentform1PostTests`, `Studentform2PostTests` classes green.

- [ ] **Step 2: Run Django system checks**

Run: `./venv/bin/python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 3: Confirm no stray migrations are needed**

Run: `./venv/bin/python manage.py makemigrations home --check --dry-run`
Expected: `No changes detected`.

- [ ] **Step 4: Final commit (if any docs/notes changed)**

```bash
git add -A
git commit -m "test: Phase 1 intake regression green" --allow-empty
```

---

## Notes for the implementer

- **CSRF is disabled** globally in `auth/settings.py` (the middleware is commented out), so the Django test client POSTs above do not need a CSRF token, and neither does the real form. Do not add `{% csrf_token %}`-dependent assertions.
- **The professor is chosen** in `studentform1` via the `prof` POST field formatted `"<name>|<unique_id>"`, split on `|`. Task 6's test data follows that format.
- **Student identity** comes from the `naam` POST field (the username), matching the existing views; the GET path uses the `student` cookie.
- **Duplicate check** (`has_pending_application`) is available for use in `studentform1` if you want to block re-entry earlier; Task 7's guard already ensures at most one pending application by reusing the existing get-or-create-by-(student, professor) lookup.
- Do **not** widen scope into filtering (FR-4/FR-5) or templates (FR-1/FR-3); those are Phases 2 and 3 with their own plans.
```
