# Phase 2 — Professor Filtering (FR-4) & Generated-Letter Tracking (FR-5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a professor filter their incoming *and* already-generated applications by Department / Country / College, search them by student name / roll number / email, see when each letter was generated, and re-download a previously generated letter.

**Architecture:** Two new small modules keep logic out of the 2300-line `views.py`. `home/filters.py` owns the queryset filtering + dropdown-option derivation (pure, easily unit-tested against the ORM). `home/dashboard.py` owns a single `build_teacher_dashboard_context()` that both `teacher()` and `loginTeacher()` call — removing the duplicated context block and fixing a latent `Application.objects.get()` crash in `loginTeacher`. `Teacher.html` gains a GET filter bar and a richer generated-letters table. A new `download_generated` view serves the stored `Application.generated_letter` file, degrading gracefully for legacy rows that have none.

**Tech Stack:** Django 5.1, SQLite, Django `TestCase` + test client, function-based views, Bootstrap-ish templates.

---

## Context an implementer needs

Read these before starting:

- **Spec:** `docs/superpowers/specs/2026-07-17-lor-template-form-filter-design.md` — §5 (FR-4), §5b (FR-5), §8 (phases). The spec is authoritative on field names.
- **Phase 1 plan (done):** `docs/superpowers/plans/2026-07-17-phase1-datamodel-intake.md`.

**Key facts about this codebase:**

- The Django project is `auth`, the single app is `home`. Run everything from the repo root with the venv active.
- **Teachers are identified by a cookie**, not `request.user`: `unique = request.COOKIES.get("unique")`, which is a `TeacherInfo.unique_id`. Applications are scoped with `professor__unique_id=unique`.
- Relevant model relationships (`home/models.py`):
  - `Application.std` → `StudentLoginInfo`; `StudentLoginInfo.department` → `Department`; `Department.dept_name` is the label.
  - `University.application` → `Application` (no `related_name`), so the reverse lookup from `Application` is **`university`**: `Application.objects.filter(university__country="Nepal")`. Because it is a to-many join, **always `.distinct()`**.
  - `University.uni_name` is the "College/University" filter; `University.country` is the "Country" filter (both added in Phase 1).
  - `Application.generated_at`, `Application.generated_template` (FK to `CustomTemplates`, `SET_NULL`), `Application.generated_letter` (`FileField(upload_to='generated_letters/')`) already exist from Phase 1 migration `0011_intake_fields` and are currently **always empty** — Phase 3 populates them at generation time. Phase 2 must therefore handle empty values everywhere.
  - `Application.is_generated` (bool) is the pending/generated split. `False` = pending.
- **CSRF middleware is disabled** project-wide (commented out in `auth/settings.py`). The filter bar is a GET form, so this is not a concern, but do not add CSRF-dependent logic.
- **Tests:** `python manage.py test home` (whole app) or `python manage.py test home.tests.ClassName` (one class). Per project rule, **run only the test class relevant to your task** while implementing; the full suite runs once at final review.
- **Commit messages must contain no AI/assistant attribution** — no `Co-Authored-By: Claude`, no "Generated with Claude Code". Never `git add CLAUDE.md` (it is gitignored).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `home/filters.py` | **Create** | Pure filtering logic: apply GET filter params (dropdowns + free-text search) to an `Application` queryset; derive dropdown options from a queryset. No HTTP, no cookies. |
| `home/dashboard.py` | **Create** | Build the full `Teacher.html` render context (pending list, generated list, filter options, counters) from a `unique_id` + filter params. No HTTP response building. |
| `home/views.py` | Modify | `teacher()` (~line 1717) and `loginTeacher()` GET branch (~line 953) delegate to `build_teacher_dashboard_context`. Add new `download_generated()` view. |
| `home/urls.py` | Modify | Add `path('download_generated/', views.download_generated, name='download_generated')`. |
| `templates/Teacher.html` | Modify | Add the GET filter bar; add Generated-on / Template / Re-download columns to the generated table. |
| `home/tests.py` | Modify (append) | New test classes: `ApplicationFilterTests`, `FilterOptionTests`, `DashboardContextTests`, `TeacherDashboardViewTests`, `DownloadGeneratedTests`. |

Nothing in Phase 2 changes `home/models.py` — **no new migration is needed.** If you find yourself writing one, stop: you have misread the plan.

---

## Task 1: Filter a queryset by Department

**Files:**
- Create: `home/filters.py`
- Test: `home/tests.py` (append class `ApplicationFilterTests`)

- [ ] **Step 1: Write the failing test**

Add this import to the **import block at the top** of `home/tests.py` (not mid-file — later tasks add more imports there too):

```python
from home.filters import apply_application_filters, filter_options
```

Then append this class to the end of `home/tests.py`:

```python
class ApplicationFilterTests(TestCase):
    def setUp(self):
        self.dept_bct = Department.objects.create(dept_name="BCT")
        self.dept_bce = Department.objects.create(dept_name="BCE")
        prog_bct = Program.objects.create(program_name="BE-BCT", department=self.dept_bct)
        prog_bce = Program.objects.create(program_name="BE-BCE", department=self.dept_bce)
        self.prof = TeacherInfo.objects.create(
            unique_id="T100", name="Prof One", email="p1@example.com",
            department=self.dept_bct,
        )
        self.stu_bct = StudentLoginInfo.objects.create(
            username="alice", roll_number="080BCT001", department=self.dept_bct,
            program=prog_bct, password="x", dob="2000-01-01",
        )
        self.stu_bce = StudentLoginInfo.objects.create(
            username="bob", roll_number="080BCE002", department=self.dept_bce,
            program=prog_bce, password="x", dob="2000-01-01",
        )
        self.app_bct = Application.objects.create(
            name="alice", email="a@example.com", professor=self.prof, std=self.stu_bct,
        )
        self.app_bce = Application.objects.create(
            name="bob", email="b@example.com", professor=self.prof, std=self.stu_bce,
        )
        University.objects.create(
            uni_name="MIT", country="USA", application=self.app_bct,
        )
        University.objects.create(
            uni_name="TU Delft", country="Netherlands", application=self.app_bce,
        )

    def base_qs(self):
        return Application.objects.filter(professor__unique_id="T100")

    def test_empty_params_returns_everything(self):
        result = apply_application_filters(self.base_qs(), {})
        self.assertEqual(result.count(), 2)

    def test_blank_values_are_ignored(self):
        result = apply_application_filters(
            self.base_qs(), {"department": "", "country": "", "college": ""}
        )
        self.assertEqual(result.count(), 2)

    def test_filter_by_department(self):
        result = apply_application_filters(self.base_qs(), {"department": "BCT"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])
```

Make sure the imports at the top of `home/tests.py` already include `Department`, `Program`, `TeacherInfo`, `StudentLoginInfo`, `Application`, `University` from `home.models`. Phase 1's tests import most of these; add any that are missing to the existing import line rather than adding a second import statement.

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: `ImportError` / `ModuleNotFoundError: No module named 'home.filters'`.

- [ ] **Step 3: Write minimal implementation**

Create `home/filters.py`:

```python
"""Queryset filtering for the professor dashboard (FR-4 / FR-5).

Pure ORM logic — no HTTP, no cookies. Callers pass an already-scoped
``Application`` queryset (normally scoped to one professor) plus the raw
GET parameters.
"""

#: GET parameter names the dashboard understands.
FILTER_PARAMS = ("department", "country", "college")


def apply_application_filters(queryset, params):
    """Narrow ``queryset`` by any of department / country / college.

    ``params`` is a dict-like (e.g. ``request.GET``). Missing or blank
    values are ignored, so an empty filter bar shows everything. Filters
    combine with AND.
    """
    department = (params.get("department") or "").strip()
    if department:
        # ``icontains``: the dashboard renders this as a typeable combobox, so
        # partial values must match. See Task 2 for the full rationale.
        queryset = queryset.filter(std__department__dept_name__icontains=department)
    return queryset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add home/filters.py home/tests.py
git commit -m "feat(filters): filter professor applications by department"
```

---

## Task 2: Filter by Country and College, and combine filters

**Files:**
- Modify: `home/filters.py`
- Test: `home/tests.py` (extend `ApplicationFilterTests`)

- [ ] **Step 1: Write the failing test**

Add these methods to `ApplicationFilterTests` in `home/tests.py`:

```python
    def test_filter_by_country(self):
        result = apply_application_filters(self.base_qs(), {"country": "USA"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_filter_by_college(self):
        result = apply_application_filters(self.base_qs(), {"college": "TU Delft"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_filters_combine_with_and(self):
        # BCT department but a Netherlands university -> no match
        result = apply_application_filters(
            self.base_qs(), {"department": "BCT", "country": "Netherlands"}
        )
        self.assertEqual(result.count(), 0)

        result = apply_application_filters(
            self.base_qs(), {"department": "BCT", "country": "USA"}
        )
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_partial_and_case_insensitive_dropdown_values_match(self):
        # The dropdowns are typeable comboboxes, so a half-typed value must work.
        result = apply_application_filters(self.base_qs(), {"country": "us"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

        result = apply_application_filters(self.base_qs(), {"college": "delft"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

        result = apply_application_filters(self.base_qs(), {"department": "bct"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_no_duplicate_rows_when_application_has_many_universities(self):
        # A second USA university on the same application must not duplicate it.
        University.objects.create(
            uni_name="Stanford", country="USA", application=self.app_bct,
        )
        result = apply_application_filters(self.base_qs(), {"country": "USA"})
        self.assertEqual(result.count(), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: FAIL — `test_filter_by_country` and `test_filter_by_college` return 2 rows instead of 1 (the params are currently ignored).

- [ ] **Step 3: Write minimal implementation**

Replace the body of `apply_application_filters` in `home/filters.py` with:

```python
def apply_application_filters(queryset, params):
    """Narrow ``queryset`` by any of department / country / college.

    ``params`` is a dict-like (e.g. ``request.GET``). Missing or blank
    values are ignored, so an empty filter bar shows everything. Filters
    combine with AND.
    """
    department = (params.get("department") or "").strip()
    country = (params.get("country") or "").strip()
    college = (params.get("college") or "").strip()

    # ``icontains`` rather than exact: the dashboard renders these as typeable
    # <datalist> comboboxes, so a professor may type a partial value ("United",
    # "Kath") instead of picking one. Exact matching would silently return
    # nothing and read as a broken filter.
    if department:
        queryset = queryset.filter(std__department__dept_name__icontains=department)
    if country:
        queryset = queryset.filter(university__country__icontains=country)
    if college:
        queryset = queryset.filter(university__uni_name__icontains=college)

    if country or college:
        # ``university`` is a to-many join: without distinct() an application
        # with two matching universities would appear twice.
        queryset = queryset.distinct()
    return queryset
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add home/filters.py home/tests.py
git commit -m "feat(filters): add country and college filters with AND combination"
```

---

## Task 3: Derive dropdown options from a professor's own applications

The filter dropdowns must only offer values that actually occur in *this* professor's applications — an empty result set is confusing, and other professors' data must not leak.

**Files:**
- Modify: `home/filters.py`
- Test: `home/tests.py` (append class `FilterOptionTests`)

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class FilterOptionTests(TestCase):
    def setUp(self):
        dept_bct = Department.objects.create(dept_name="BCT")
        dept_bex = Department.objects.create(dept_name="BEX")
        prog_bct = Program.objects.create(program_name="BE-BCT", department=dept_bct)
        prog_bex = Program.objects.create(program_name="BE-BEX", department=dept_bex)
        self.mine = TeacherInfo.objects.create(
            unique_id="T200", name="Mine", email="mine@example.com", department=dept_bct,
        )
        other = TeacherInfo.objects.create(
            unique_id="T201", name="Other", email="other@example.com", department=dept_bct,
        )
        stu_a = StudentLoginInfo.objects.create(
            username="ann", roll_number="080BCT010", department=dept_bct,
            program=prog_bct, password="x", dob="2000-01-01",
        )
        stu_b = StudentLoginInfo.objects.create(
            username="ben", roll_number="080BEX011", department=dept_bex,
            program=prog_bex, password="x", dob="2000-01-01",
        )
        app_a = Application.objects.create(
            name="ann", email="ann@example.com", professor=self.mine, std=stu_a,
        )
        app_b = Application.objects.create(
            name="ben", email="ben@example.com", professor=self.mine, std=stu_b,
        )
        app_other = Application.objects.create(
            name="zed", email="zed@example.com", professor=other, std=stu_a,
        )
        University.objects.create(uni_name="MIT", country="USA", application=app_a)
        University.objects.create(uni_name="MIT", country="USA", application=app_b)
        University.objects.create(uni_name="Aalto", country="Finland", application=app_b)
        University.objects.create(
            uni_name="SecretU", country="Japan", application=app_other,
        )

    def base_qs(self):
        return Application.objects.filter(professor__unique_id="T200")

    def test_options_are_sorted_and_deduplicated(self):
        options = filter_options(self.base_qs())
        self.assertEqual(options["departments"], ["BCT", "BEX"])
        self.assertEqual(options["countries"], ["Finland", "USA"])
        self.assertEqual(options["colleges"], ["Aalto", "MIT"])

    def test_options_exclude_other_professors_values(self):
        options = filter_options(self.base_qs())
        self.assertNotIn("Japan", options["countries"])
        self.assertNotIn("SecretU", options["colleges"])

    def test_blank_and_null_values_are_omitted(self):
        app = Application.objects.get(name="ann")
        University.objects.create(uni_name="", country=None, application=app)
        options = filter_options(self.base_qs())
        self.assertNotIn("", options["colleges"])
        self.assertNotIn(None, options["countries"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.FilterOptionTests -v 2`

Expected: FAIL — `ImportError: cannot import name 'filter_options'` (or `AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Append to `home/filters.py`:

```python
def _distinct_values(queryset, field):
    """Sorted, de-duplicated, non-empty values of ``field`` in ``queryset``."""
    values = queryset.values_list(field, flat=True).distinct()
    return sorted({v for v in values if v not in (None, "")})


def filter_options(queryset):
    """Dropdown choices derived from the applications in ``queryset``.

    Scoping the options to the professor's own applications keeps other
    professors' students out of the filter bar and avoids offering
    combinations that can only ever return nothing.
    """
    return {
        "departments": _distinct_values(queryset, "std__department__dept_name"),
        "countries": _distinct_values(queryset, "university__country"),
        "colleges": _distinct_values(queryset, "university__uni_name"),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.FilterOptionTests -v 2`

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add home/filters.py home/tests.py
git commit -m "feat(filters): derive filter dropdown options from a professor's applications"
```

---

## Task 3b: Free-text search across student name, roll number and email

The dropdowns answer "which country / college"; they do not help a professor find one
named student among forty pending requests. A single search box that matches name, roll
number, or email covers that without making the professor choose a field first.

Deliberately **not** searched: university name and country — the dropdowns already handle
those, and folding them into the text box produces confusing cross-matches.

**Files:**
- Modify: `home/filters.py`
- Test: `home/tests.py` (extend `ApplicationFilterTests`)

- [ ] **Step 1: Write the failing test**

Add these methods to `ApplicationFilterTests`. They rely on the `setUp` from Task 1
(`alice` / `080BCT001` / `a@example.com` and `bob` / `080BCE002` / `b@example.com`):

```python
    def test_search_matches_application_name(self):
        result = apply_application_filters(self.base_qs(), {"q": "alice"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_is_case_insensitive_and_partial(self):
        result = apply_application_filters(self.base_qs(), {"q": "AL"})
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_matches_roll_number(self):
        result = apply_application_filters(self.base_qs(), {"q": "080bce"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_matches_email(self):
        result = apply_application_filters(self.base_qs(), {"q": "b@example.com"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_matches_first_or_last_name_fields(self):
        self.app_bce.first_name = "Bobby"
        self.app_bce.last_name = "Tables"
        self.app_bce.save()
        result = apply_application_filters(self.base_qs(), {"q": "tables"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_blank_search_is_ignored(self):
        result = apply_application_filters(self.base_qs(), {"q": "   "})
        self.assertEqual(result.count(), 2)

    def test_search_combines_with_dropdown_filters(self):
        # alice matches the text, but her university is in the USA, not Finland.
        result = apply_application_filters(
            self.base_qs(), {"q": "alice", "country": "Netherlands"}
        )
        self.assertEqual(result.count(), 0)

        result = apply_application_filters(
            self.base_qs(), {"q": "alice", "country": "USA"}
        )
        self.assertEqual([a.pk for a in result], [self.app_bct.pk])

    def test_search_terms_are_anded_regardless_of_word_order(self):
        self.app_bce.first_name = "Ramesh"
        self.app_bce.last_name = "Shrestha"
        self.app_bce.save()
        result = apply_application_filters(self.base_qs(), {"q": "shrestha ramesh"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_search_terms_may_match_different_fields(self):
        result = apply_application_filters(self.base_qs(), {"q": "bob 080bce"})
        self.assertEqual([a.pk for a in result], [self.app_bce.pk])

    def test_every_term_must_match(self):
        result = apply_application_filters(self.base_qs(), {"q": "bob 080bct"})
        self.assertEqual(result.count(), 0)

    def test_search_does_not_match_university_name(self):
        # University search is the dropdowns' job; matching it here would
        # surprise a professor searching for a person.
        result = apply_application_filters(self.base_qs(), {"q": "MIT"})
        self.assertEqual(result.count(), 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: FAIL — the search tests return 2 rows instead of 1, because `q` is ignored.

- [ ] **Step 3: Write minimal implementation**

In `home/filters.py`, add the import at the top of the file:

```python
from django.db.models import Q
```

Extend `FILTER_PARAMS` and the search-relevant constant:

```python
#: GET parameter names the dashboard understands.
FILTER_PARAMS = ("department", "country", "college", "q")

#: Fields the free-text box searches. Student identity only — university
#: name/country are covered by the dropdowns.
SEARCH_FIELDS = (
    "name",
    "first_name",
    "last_name",
    "email",
    "std__roll_number",
    "std__username",
)
```

Then add the search clause inside `apply_application_filters`, immediately after the
`college` filter and **before** the `distinct()` block:

```python
    search = (params.get("q") or "").strip()
    if search:
        # Each whitespace-separated term must match SOME field (AND of ORs), so
        # "shrestha ramesh" finds "Ramesh Shrestha" despite the word order, and
        # "ramesh 080bct" can match the name and the roll number separately.
        for term in search.split():
            matches = Q()
            for field in SEARCH_FIELDS:
                matches |= Q(**{f"{field}__icontains": term})
            queryset = queryset.filter(matches)
```

Substring matching (`icontains` → SQL `LIKE '%term%'`) is deliberate: a professor
typing `esh` or a partial roll number `080BCT` expects a hit, which word-indexed
full-text search would not give. No index is added — one professor's applications
number in the tens, so the scan is trivially fast. If this ever grew into the
thousands, the upgrade path is Postgres + `pg_trgm`, not a search engine.

And update the `distinct()` condition so a search joined with a to-many filter still
de-duplicates:

```python
    if country or college:
        # ``university`` is a to-many join: without distinct() an application
        # with two matching universities would appear twice.
        queryset = queryset.distinct()
```

(That condition is unchanged — `SEARCH_FIELDS` contains no to-many joins, so search alone
cannot duplicate rows. Leave it as-is; this step is a check, not an edit.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.ApplicationFilterTests -v 2`

Expected: PASS (19 tests).

- [ ] **Step 5: Commit**

```bash
git add home/filters.py home/tests.py
git commit -m "feat(filters): add free-text search over student name, roll number and email"
```

---

## Task 4: Shared dashboard context builder

`teacher()` and `loginTeacher()` currently build the same `Teacher.html` context twice. `loginTeacher` does it with `Application.objects.get(professor__unique_id=unique, is_generated=True)` — a **bug**: `.get()` raises `DoesNotExist` when the professor has generated nothing and `MultipleObjectsReturned` once they have generated two letters. Extracting one builder fixes it and gives filtering a single home.

**Files:**
- Create: `home/dashboard.py`
- Test: `home/tests.py` (append class `DashboardContextTests`)

- [ ] **Step 1: Write the failing test**

Add to the import block at the top of `home/tests.py`:

```python
from home.dashboard import build_teacher_dashboard_context
```

Then append this class to `home/tests.py`:

```python
class DashboardContextTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T300", name="Prof Three", email="p3@example.com", department=dept,
        )
        self.stu = StudentLoginInfo.objects.create(
            username="cara", roll_number="080BCT020", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.pending = Application.objects.create(
            name="cara pending", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=False,
        )
        self.older = Application.objects.create(
            name="cara older", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=True,
            generated_at=timezone.make_aware(datetime(2026, 1, 1, 9, 0)),
        )
        self.newer = Application.objects.create(
            name="cara newer", email="c@example.com", professor=self.prof,
            std=self.stu, is_generated=True,
            generated_at=timezone.make_aware(datetime(2026, 5, 1, 9, 0)),
        )
        University.objects.create(uni_name="MIT", country="USA", application=self.newer)
        University.objects.create(
            uni_name="Aalto", country="Finland", application=self.older,
        )

    def test_splits_pending_and_generated(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual([a.pk for a in ctx["student_list"]], [self.pending.pk])
        self.assertEqual(len(ctx["all_students"]), 2)

    def test_generated_list_is_newest_first(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual(
            [a.pk for a in ctx["all_students"]], [self.newer.pk, self.older.pk]
        )

    def test_filters_apply_to_both_lists(self):
        ctx = build_teacher_dashboard_context("T300", {"country": "USA"})
        self.assertEqual([a.pk for a in ctx["all_students"]], [self.newer.pk])
        # The pending application has no USA university, so it drops out too.
        self.assertEqual(list(ctx["student_list"]), [])

    def test_context_exposes_options_and_active_filters(self):
        ctx = build_teacher_dashboard_context("T300", {"country": "USA"})
        self.assertEqual(ctx["filter_options"]["countries"], ["Finland", "USA"])
        self.assertEqual(ctx["active_filters"]["country"], "USA")
        self.assertEqual(ctx["active_filters"]["department"], "")
        self.assertTrue(ctx["filters_active"])

    def test_no_filters_means_filters_inactive(self):
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertFalse(ctx["filters_active"])

    def test_search_narrows_both_lists_and_counts_as_active(self):
        ctx = build_teacher_dashboard_context("T300", {"q": "newer"})
        self.assertEqual([a.pk for a in ctx["all_students"]], [self.newer.pk])
        self.assertEqual(list(ctx["student_list"]), [])
        self.assertEqual(ctx["active_filters"]["q"], "newer")
        self.assertTrue(ctx["filters_active"])

    def test_teacher_with_no_generated_letters_does_not_crash(self):
        Application.objects.filter(is_generated=True).delete()
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertEqual(list(ctx["all_students"]), [])
        self.assertFalse(ctx["check_value"])

    def test_check_value_true_when_nothing_pending(self):
        self.pending.delete()
        ctx = build_teacher_dashboard_context("T300", {})
        self.assertTrue(ctx["check_value"])
```

Add to the imports at the top of `home/tests.py` (merge into existing lines where one already exists):

```python
from datetime import datetime
from django.utils import timezone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.DashboardContextTests -v 2`

Expected: `ModuleNotFoundError: No module named 'home.dashboard'`.

- [ ] **Step 3: Write minimal implementation**

Create `home/dashboard.py`:

```python
"""Render context for the professor dashboard (``Teacher.html``).

Both ``views.teacher`` and the GET branch of ``views.loginTeacher`` render
the same template; this module is the single source of truth for what that
template receives.
"""

from django.core import serializers

from home.filters import FILTER_PARAMS, apply_application_filters, filter_options


def build_teacher_dashboard_context(unique_id, params):
    """Build the ``Teacher.html`` context for the professor ``unique_id``.

    ``params`` is a dict-like of GET filter values (see
    ``home.filters.FILTER_PARAMS``). Filters apply to both the pending and
    the generated list so the two views of the dashboard stay consistent.
    """
    from home.models import Application, TeacherInfo

    teacher_model = TeacherInfo.objects.get(unique_id=unique_id)
    scoped = Application.objects.filter(professor__unique_id=unique_id)

    # Options come from the UNFILTERED set, so selecting one filter never
    # empties the other dropdowns.
    options = filter_options(scoped)

    filtered = apply_application_filters(scoped, params)
    pending = filtered.filter(is_generated=False)
    generated = filtered.filter(is_generated=True).order_by("-generated_at", "-id")

    active_filters = {key: (params.get(key) or "").strip() for key in FILTER_PARAMS}

    return {
        "all_students": generated,
        "student_list": pending,
        "check_value": not pending.exists(),
        "teacher_number": scoped.count(),
        "std_dataharu": serializers.serialize("json", generated),
        "teacher_model": teacher_model,
        "default_template": teacher_model.customtemplates_set.filter(
            is_default=True
        ).first(),
        "filter_options": options,
        "active_filters": active_filters,
        "filters_active": any(active_filters.values()),
        "generated_count": generated.count(),
    }
```

Note: `order_by("-generated_at", "-id")` puts rows with `generated_at=NULL` last on SQLite (NULLs sort lowest, so descending places them at the end) and falls back to insertion order for the legacy rows Phase 1 left unstamped.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.DashboardContextTests -v 2`

Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add home/dashboard.py home/tests.py
git commit -m "feat(dashboard): add shared professor dashboard context builder"
```

---

## Task 5: Wire the builder into `teacher()` and `loginTeacher()`

**Files:**
- Modify: `home/views.py` — `teacher()` (~line 1717) and the teacher branch of `loginTeacher()` (~line 977–1017)
- Test: `home/tests.py` (append class `TeacherDashboardViewTests`)

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class TeacherDashboardViewTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T400", name="Prof Four", email="p4@example.com", department=dept,
        )
        stu = StudentLoginInfo.objects.create(
            username="dan", roll_number="080BCT030", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.usa_app = Application.objects.create(
            name="dan usa", email="d@example.com", professor=self.prof,
            std=stu, is_generated=False,
        )
        self.fin_app = Application.objects.create(
            name="dan finland", email="d@example.com", professor=self.prof,
            std=stu, is_generated=False,
        )
        University.objects.create(
            uni_name="MIT", country="USA", application=self.usa_app,
        )
        University.objects.create(
            uni_name="Aalto", country="Finland", application=self.fin_app,
        )
        self.client.cookies["unique"] = "T400"
        self.client.cookies["username"] = "Prof Four"

    def test_teacher_view_renders_all_applications_by_default(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dan usa")
        self.assertContains(response, "dan finland")

    def test_teacher_view_applies_country_filter(self):
        response = self.client.get("/teacher", {"country": "USA"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_teacher_view_exposes_filter_options(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.context["filter_options"]["countries"],
                         ["Finland", "USA"])

    def test_login_teacher_get_does_not_crash_without_generated_letters(self):
        # Regression: loginTeacher used Application.objects.get(is_generated=True),
        # which raised DoesNotExist for a professor with no generated letters.
        response = self.client.get("/loginTeacher")
        self.assertEqual(response.status_code, 200)

    def test_login_teacher_get_does_not_crash_with_two_generated_letters(self):
        # Regression: the same .get() raised MultipleObjectsReturned.
        Application.objects.filter(professor=self.prof).update(is_generated=True)
        response = self.client.get("/loginTeacher")
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: FAIL — `test_teacher_view_applies_country_filter` fails (both names render, filter ignored), `test_teacher_view_exposes_filter_options` raises `KeyError: 'filter_options'`, and the two `loginTeacher` regression tests fail with `DoesNotExist` / `MultipleObjectsReturned`.

- [ ] **Step 3: Write minimal implementation**

**3a.** Add the import near the other `home.*` imports at the top of `home/views.py`:

```python
from home.dashboard import build_teacher_dashboard_context
```

**3b.** Replace the **entire body** of `teacher()` (currently views.py:1717 through the `return response` that ends it) with:

```python
def teacher(request):
    unique = request.COOKIES.get("unique")
    context = build_teacher_dashboard_context(unique, request.GET)
    return render(request, "Teacher.html", context)
```

**3c.** In `loginTeacher()`, inside `if TeacherInfo.objects.filter(name__exact=user).exists():`, replace everything from `value = 0` down to and including `return response` with:

```python
                unique = request.COOKIES.get('unique')
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
```

Keep the surrounding indentation exactly as it is in that block (16 spaces — it is nested inside `if request.method == "GET":` and then the `if TeacherInfo...` check). Do not touch the student branch above it or the `return render(request, "loginTeacher.html")` below it.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: PASS (5 tests).

Then confirm nothing else broke:

Run: `python manage.py test home.tests.DashboardContextTests home.tests.ApplicationFilterTests home.tests.FilterOptionTests -v 2`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "refactor(teacher): use shared dashboard context and honour GET filters"
```

---

## Task 5b: Route the remaining `Teacher.html` renders through the builder

**Discovered during Task 5 review.** `Teacher.html` is rendered from **six** places, not two.
Task 5 converted `teacher()` and the `loginTeacher` GET branch. Four hand-built copies of the
same ~35-line context block remain:

| Line (approx) | Function |
|---|---|
| ~121 | `index()` |
| ~316 | `registerStudent()` |
| ~413 | `loginStudent()` |
| ~1036 | `loginTeacher()` **POST branch** |

All four use `.filter()` and so do **not** carry the `.get()` crash bug — this is not a bug fix.
But none supplies `filter_options`, `active_filters`, `filters_active`, or `generated_count`.
Django renders missing template variables as empty, so once Task 6 lands, any professor arriving
through one of these paths would see a filter bar with **empty dropdowns** and a heading reading
`Students You Have Recommended ():`. The `loginTeacher` POST branch is the path a professor takes
every time they log in, so this is the common case, not an edge case.

Converting all four also removes ~140 lines of copy-paste and makes the builder genuinely the
single source of truth.

**Files:**
- Modify: `home/views.py`
- Test: `home/tests.py` (append to `TeacherDashboardViewTests`)

- [ ] **Step 1: Write the failing test**

Add these methods to `TeacherDashboardViewTests`:

```python
    def test_all_teacher_dashboard_entry_points_supply_filter_options(self):
        # Teacher.html is rendered from several views; every one of them must
        # provide the filter context or the filter bar renders empty.
        for path in ("/", "/loginStudent", "/registerStudent"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["filter_options"]["countries"],
                    ["Finland", "USA"],
                )
                self.assertEqual(response.context["generated_count"], 0)

    def test_login_teacher_post_supplies_filter_options(self):
        user = User.objects.create_user(
            username="prof4", email="p4@example.com", password="secret",
        )
        user.first_name = "Prof Four/T400"
        user.save()
        response = self.client.post(
            "/loginTeacher", {"username": "p4@example.com", "password": "secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["filter_options"]["countries"], ["Finland", "USA"]
        )
```

Add to the import block at the top of `home/tests.py`:

```python
from django.contrib.auth.models import User
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: FAIL — `KeyError: 'filter_options'` on the entry points that still hand-build context.

- [ ] **Step 3: Write minimal implementation**

In each of the four locations, replace the hand-built block with a call to the builder. The block
to replace in each case starts at the line reading:

```python
                teacher_model = TeacherInfo.objects.get(unique_id=unique)
```

and ends at its `return response`. Replace the whole span with:

```python
                context = build_teacher_dashboard_context(unique, request.GET)
                return render(request, "Teacher.html", context)
```

**Preserve the exact existing indentation at each site** (they differ — check each one; most are
16 spaces). Do not change the `if` conditions above the block, the cookie lookups that compute
`unique`, or anything after the block.

After each replacement, some preceding lines may become dead (e.g. a `value = 0` initialiser that
nothing reads any more). Remove a line ONLY if you have confirmed by reading the enclosing function
that nothing else references it. If you are unsure, leave it and note it in your report.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: PASS (7 tests).

Then: `venv/bin/python manage.py check` — expected: no issues.

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "refactor(teacher): route every Teacher.html render through the shared context builder"
```

---

## Task 6: Filter bar and richer generated table in `Teacher.html`

The view now supplies `filter_options` and `active_filters`, but nothing renders them. Without this task FR-4 is invisible to a real professor — exactly the gap Phase 1 hit with `Studentform1.html`.

**Files:**
- Modify: `templates/Teacher.html`
- Test: `home/tests.py` (append to `TeacherDashboardViewTests`)

- [ ] **Step 1: Write the failing test**

Add these methods to `TeacherDashboardViewTests`:

```python
    def test_filter_bar_is_rendered_with_typeable_comboboxes(self):
        response = self.client.get("/teacher")
        self.assertContains(response, 'name="department"')
        self.assertContains(response, 'name="country"')
        self.assertContains(response, 'name="college"')
        # Each field is an <input list=...> backed by a <datalist> of suggestions,
        # so the professor can either pick a value or type a partial one.
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, '<datalist id="country-options">')
        self.assertContains(response, '<option value="Finland">')
        self.assertContains(response, '<option value="MIT">')

    def test_active_filter_value_is_kept_in_the_box(self):
        response = self.client.get("/teacher", {"country": "USA"})
        self.assertContains(response, 'value="USA"')

    def test_partially_typed_filter_value_still_matches(self):
        response = self.client.get("/teacher", {"country": "us"})
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_search_box_is_rendered_and_keeps_its_value(self):
        response = self.client.get("/teacher", {"q": "dan usa"})
        self.assertContains(response, 'name="q"')
        self.assertContains(response, 'value="dan usa"')
        self.assertContains(response, "dan usa")
        self.assertNotContains(response, "dan finland")

    def test_generated_table_has_tracking_columns(self):
        response = self.client.get("/teacher")
        self.assertContains(response, "Generated on")
        self.assertContains(response, "Template")

    def test_empty_state_distinguishes_no_requests_from_no_matches(self):
        # No filter and nothing pending -> the cheerful global message.
        Application.objects.filter(professor=self.prof).update(is_generated=True)
        response = self.client.get("/teacher")
        self.assertContains(response, "You have no request for now")

        # A filter that matches nothing must NOT claim there are no requests at all.
        Application.objects.filter(professor=self.prof).update(is_generated=False)
        response = self.client.get("/teacher", {"country": "Antarctica"})
        self.assertContains(response, "No pending requests match")
        self.assertNotContains(response, "You have no request for now")

    def test_generated_count_is_shown(self):
        response = self.client.get("/teacher")
        self.assertEqual(response.context["generated_count"], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: FAIL — the three new tests fail because `Teacher.html` contains no filter bar and no tracking columns.

- [ ] **Step 3: Write minimal implementation**

**3a.** In `templates/Teacher.html`, insert this filter bar immediately after the opening `<div class="container-fluid">` (currently line 9) and before the `{% if check_value %}` line:

```html
  <form method="get" action="/teacher" class="row g-2 align-items-end mb-4">
    <div class="col-auto">
      <label for="filter-q" class="form-label">Search student</label>
      <input class="form-control" id="filter-q" type="search" name="q"
             placeholder="Name, roll number or email"
             value="{{ active_filters.q }}">
    </div>
    <div class="col-auto">
      <label for="filter-department" class="form-label">Department</label>
      <input class="form-control" id="filter-department" name="department"
             list="department-options" placeholder="All departments"
             value="{{ active_filters.department }}">
      <datalist id="department-options">
        {% for option in filter_options.departments %}
        <option value="{{ option }}">
        {% endfor %}
      </datalist>
    </div>
    <div class="col-auto">
      <label for="filter-country" class="form-label">Country</label>
      <input class="form-control" id="filter-country" name="country"
             list="country-options" placeholder="All countries"
             value="{{ active_filters.country }}">
      <datalist id="country-options">
        {% for option in filter_options.countries %}
        <option value="{{ option }}">
        {% endfor %}
      </datalist>
    </div>
    <div class="col-auto">
      <label for="filter-college" class="form-label">College / University</label>
      <input class="form-control" id="filter-college" name="college"
             list="college-options" placeholder="All colleges"
             value="{{ active_filters.college }}">
      <datalist id="college-options">
        {% for option in filter_options.colleges %}
        <option value="{{ option }}">
        {% endfor %}
      </datalist>
    </div>
    <div class="col-auto">
      <button class="btn btn-primary" type="submit">Filter</button>
      {% if filters_active %}
      <a class="btn btn-secondary" href="/teacher">Clear</a>
      {% endif %}
    </div>
  </form>
```

`<datalist>` is deliberate over a JS combobox library (Select2, Tom Select, Choices.js): this project has no npm build step, so a library would mean a CDN `<script>` tag — which breaks offline demos and adds a dependency for behaviour the browser already provides. `<datalist>` gives type-to-filter *and* free typing with zero JavaScript.

Note the `<option>` tags inside a `<datalist>` are value-only and self-closing in practice — no text content and no `</option>`, which is what the tests assert.

**3a-bis.** Fix the now-misleading empty state. `check_value` reflects the *filtered* pending
list, so with a filter active it can be `True` while the professor still has pending requests
that simply don't match. The existing copy would then wrongly read "you have no request for
now". Replace the existing line:

```html
  <h5 style="text-align:center">Yeah! You have no request for now from students.</h5>
```

with:

```html
  {% if filters_active %}
  <h5 style="text-align:center">No pending requests match your search or filter. <a href="/teacher">Show all</a></h5>
  {% else %}
  <h5 style="text-align:center">Yeah! You have no request for now from students.</h5>
  {% endif %}
```

**3b.** Replace the header row of the generated table (currently lines 43–47, the `<tr>` holding `Name` / `Email` / `Letter`) with:

```html
        <tr>
          <th>Name</th>
          <th>Email</th>
          <th>Generated on</th>
          <th>Template</th>
          <th>Letter</th>
        </tr>
```

**3c.** In the `{% for item in all_students %}` row, insert these two cells between the email `<td>` and the `<td>` that holds the `/studentfinal` form:

```html
          <td class="fs-5">
            {% if item.generated_at %}{{ item.generated_at|date:"d M Y, H:i" }}{% else %}—{% endif %}
          </td>
          <td class="fs-5">
            {% if item.generated_template %}{{ item.generated_template.template_name }}{% else %}—{% endif %}
          </td>
```

The em-dash fallbacks matter: every existing row has `generated_at=NULL` until Phase 3 starts stamping it.

**3c-bis.** Surface `generated_count` so it isn't dead context. Change the heading:

```html
  <h1>Students You Have Recommended:</h1>
```

to:

```html
  <h1>Students You Have Recommended ({{ generated_count }}):</h1>
```

**3d.** The generated row's `</tr>` is currently missing (the loop closes with `{% endfor %}` right after the `</td>`). Add `</tr>` immediately before `{% endfor %}` so the new columns line up.

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.TeacherDashboardViewTests -v 2`

Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add templates/Teacher.html home/tests.py
git commit -m "feat(teacher): add search box, filter bar and letter tracking columns"
```

---

## Task 7: Re-download a stored generated letter

**Files:**
- Modify: `home/views.py` (add `download_generated` near `download_letter`, ~line 2106)
- Modify: `home/urls.py`
- Modify: `templates/Teacher.html`
- Test: `home/tests.py` (append class `DownloadGeneratedTests`)

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class DownloadGeneratedTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(dept_name="BCT")
        prog = Program.objects.create(program_name="BE-BCT", department=dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="T500", name="Prof Five", email="p5@example.com", department=dept,
        )
        self.other = TeacherInfo.objects.create(
            unique_id="T501", name="Prof Six", email="p6@example.com", department=dept,
        )
        stu = StudentLoginInfo.objects.create(
            username="eve", roll_number="080BCT040", department=dept,
            program=prog, password="x", dob="2000-01-01",
        )
        self.stored = Application.objects.create(
            name="eve stored", email="e@example.com", professor=self.prof,
            std=stu, is_generated=True,
        )
        self.stored.generated_letter.save(
            "eve.pdf", ContentFile(b"%PDF-1.4 fake letter"), save=True,
        )
        self.legacy = Application.objects.create(
            name="eve legacy", email="e@example.com", professor=self.prof,
            std=stu, is_generated=True,
        )
        self.client.cookies["unique"] = "T500"

    def tearDown(self):
        self.stored.generated_letter.delete(save=False)

    def test_returns_stored_file(self):
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 fake letter")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_missing_stored_file_redirects_with_message(self):
        response = self.client.get(f"/download_generated/?id={self.legacy.pk}")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/teacher")

    def test_other_professors_letter_is_not_served(self):
        self.client.cookies["unique"] = "T501"
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 404)

    def test_anonymous_request_is_not_served(self):
        del self.client.cookies["unique"]
        response = self.client.get(f"/download_generated/?id={self.stored.pk}")
        self.assertEqual(response.status_code, 404)
```

Add to the imports at the top of `home/tests.py`:

```python
from django.core.files.base import ContentFile
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test home.tests.DownloadGeneratedTests -v 2`

Expected: FAIL — all four tests 404 because the route does not exist.

- [ ] **Step 3: Write minimal implementation**

**3a.** Add to `home/views.py`, immediately above `def download_letter(request):`:

```python
def download_generated(request):
    """Re-serve the letter stored on an Application (FR-5).

    Scoped to the professor in the ``unique`` cookie so one professor cannot
    fetch another's letters by guessing an id. Rows generated before Phase 3
    started stamping ``generated_letter`` have no stored file, so we redirect
    back to the dashboard with an explanation instead of 500-ing.
    """
    unique = request.COOKIES.get("unique")
    application_id = request.GET.get("id")
    if not unique or not application_id:
        # A missing id would otherwise reach the ORM as pk=None and blow up.
        raise Http404("Not signed in as a professor, or no letter requested.")

    application = get_object_or_404(
        Application, pk=application_id, professor__unique_id=unique
    )

    if not application.generated_letter:
        messages.error(
            request,
            "No stored copy of this letter is available. Generate it again to save a copy.",
        )
        return redirect("/teacher")

    return FileResponse(
        application.generated_letter.open("rb"),
        as_attachment=True,
        filename=os.path.basename(application.generated_letter.name),
    )
```

**3b.** Ensure these names are imported at the top of `home/views.py`. Several already are — check before adding, and merge into the existing `from django.shortcuts import ...` line rather than duplicating it:

```python
import os
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
```

**3c.** Add to `home/urls.py`, next to the existing `download_letter` route:

```python
    path('download_generated/', views.download_generated, name='download_generated'),
```

**3d.** In `templates/Teacher.html`, inside the generated row's letter `<td>` (after the existing `</form>` that posts to `/studentfinal`), add:

```html
              {% if item.generated_letter %}
              <a class="btn btn-secondary" href="/download_generated/?id={{ item.id }}">Re-download</a>
              {% endif %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test home.tests.DownloadGeneratedTests -v 2`

Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/urls.py templates/Teacher.html home/tests.py
git commit -m "feat(tracking): re-download a professor's stored generated letter"
```

---

## Task 8: Full-suite verification and documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-07-20-phase2-filtering-tracking.md` (tick the boxes)

- [ ] **Step 1: Run the whole suite**

Run: `python manage.py test home -v 2`

Expected: PASS — the 19 Phase-1 tests plus all Phase-2 tests, 0 failures, 0 errors.

- [ ] **Step 2: Confirm no model drift**

Run: `python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`. Phase 2 adds no model fields; if this reports changes, a model was edited by mistake — revert it.

- [ ] **Step 3: System check**

Run: `python manage.py check`

Expected: `System check identified no issues`.

- [ ] **Step 4: Document the feature in the README**

In `README.md`, under **Using the app → Teacher / Professor**, replace step 2 with:

```markdown
2. **Log in** and view incoming requests and the students you have already recommended.
   Use the **filter bar** (Department / Country / College) to narrow both lists — for
   example, "everyone I have recommended who applied to a university in the USA". Each
   filter box suggests the values present in your own applications, but you can also
   type a partial value. Use
   the **search box** to find one student by name, roll number, or email. Search and
   filters combine.
   The recommended-students table shows when each letter was generated, which template
   produced it, and a **Re-download** link for letters whose file was stored.
```

- [ ] **Step 5: Commit**

```bash
git add README.md docs/superpowers/plans/2026-07-20-phase2-filtering-tracking.md
git commit -m "docs: document professor filtering and generated-letter tracking"
```

---

## Definition of done

- A professor sees Department / Country / College **typeable comboboxes** (`<input list>` + `<datalist>`) whose suggestions come only from their own applications, plus a search box. Typing a partial value (`us`, `delft`) matches; picking from the list also works.
- Searching by student name, roll number, or email narrows both lists; search ANDs with the dropdowns.
- Selecting filters narrows **both** the pending-requests list and the recommended-students table; filters AND together; "Clear" resets.
- The recommended-students table sorts newest-generated first and shows generation time + template, with `—` where Phase 3 has not yet stamped them.
- Re-download serves the stored file, 404s across professors, and redirects with a message when no file was stored.
- `loginTeacher` no longer crashes for professors with zero or multiple generated letters.
- `python manage.py test home` passes in full; no new migrations; no AI attribution in any commit.

## Explicitly out of scope (Phase 3)

- Writing `generated_at`, `generated_template`, and `generated_letter` at generation time — that lands with template selection in Phase 3. Phase 2 only *reads* them.
- System template library, template duplication, template selection UI.
