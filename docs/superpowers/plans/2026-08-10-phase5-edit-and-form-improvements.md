# Phase 5 — Professor Edit/Regenerate + Student-Form Improvements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let professors reopen and fully edit a student's application after generation and regenerate the letter (with an optional template swap), and polish the student form (self-added subjects, Back button, "GPA or percentage", required deadlines) plus deadline filter/sort on the professor dashboard.

**Architecture:** Function-based views in `home/views.py`; pure helpers in `home/intake.py`/`home/filters.py`; dashboard context in `home/dashboard.py`; templates in top-level `/templates/`. Professor edits are persisted by extending the existing `renderCustom` preview step through a new `apply_professor_edits` helper — no new unauthenticated surface. Satellite writes use delete-then-recreate inside `transaction.atomic()`, matching the existing code.

**Tech Stack:** Django 5.1, SQLite, `home/tests.py` (`TestCase`, `login_as_teacher`/`login_as_student` helpers). Run tests with `source venv/bin/activate` first.

**Spec:** `docs/superpowers/specs/2026-08-10-phase5-edit-and-form-improvements-design.md`

**Implementation order:** Task 1 (A) → Task 2 (C) → Task 3 (E) → Task 4 (B) → Task 5 (D).

**Per-task test scope:** each task runs ONLY the tests it adds/touches (`python manage.py test home.tests.<ClassName>`). The full suite runs once, at the final review.

---

## Task 1 — Unit A: teacher self-adds subjects (free-text, shared pool)

**Files:**
- Modify: `home/views.py` — `addSubjects` (~1401-1433), `deleteSubjects` (~1435-1461)
- Modify: `templates/userDetails.html` — the `#subjects` management area
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing tests**

Add to `home/tests.py`:

```python
class SelfAddSubjectTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            unique_id="777", name="Dr Rana", email="rana@example.com",
            department=self.dept,
        )
        login_as_teacher(self.client, self.teacher)

    def test_a_novel_subject_is_created_and_linked(self):
        resp = self.client.post("/addSubjects", {"subject": "Compiler Design"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Subject.objects.filter(sub_name="Compiler Design").exists())
        self.assertIn(
            "Compiler Design",
            [s.sub_name for s in self.teacher.subjects.all()],
        )

    def test_an_existing_name_is_reused_case_insensitively(self):
        Subject.objects.create(sub_name="DBMS")
        self.client.post("/addSubjects", {"subject": "dbms"})
        # No second near-duplicate row was created.
        self.assertEqual(Subject.objects.filter(sub_name__iexact="dbms").count(), 1)
        self.assertEqual(self.teacher.subjects.count(), 1)

    def test_blank_subject_is_ignored(self):
        self.client.post("/addSubjects", {"subject": "   "})
        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(self.teacher.subjects.count(), 0)

    def test_delete_unknown_subject_does_not_500(self):
        resp = self.client.post("/deleteSubjects", {"subject": "Nonexistent"})
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python manage.py test home.tests.SelfAddSubjectTests -v 2`
Expected: FAIL — `test_a_novel_subject_is_created_and_linked` fails ("No such Subject exists." because `addSubjects` requires a pre-existing row); `test_delete_unknown_subject_does_not_500` errors with `Subject.DoesNotExist` (500).

- [ ] **Step 3: Rewrite `addSubjects`**

Replace `home/views.py` lines 1401-1433 with:

```python
def addSubjects(request):
    if request.method == "POST":
        # Identity comes from the session, not from a client-set cookie.
        teacher = current_teacher(request)
        if teacher is None:
            messages.error(request, "You are not signed in as a professor.")
            return redirect(userDetails)

        name = (request.POST.get("subject") or "").strip()
        if not name:
            messages.error(request, "Enter a subject name.")
            return redirect(userDetails)

        # Free-text, shared pool: reuse an existing row case-insensitively to
        # curb near-duplicates ("DBMS" vs "dbms"), otherwise create it.
        subject_obj = Subject.objects.filter(sub_name__iexact=name).first()
        if subject_obj is None:
            subject_obj = Subject.objects.create(sub_name=name)

        if teacher.subjects.filter(pk=subject_obj.pk).exists():
            messages.error(request, "Subject already exists.")
        else:
            teacher.subjects.add(subject_obj)
            messages.success(request, "Subject has been added successfully.")
        return redirect(userDetails)

    return redirect(userDetails)
```

- [ ] **Step 4: Guard `deleteSubjects`**

In `home/views.py` `deleteSubjects`, replace the unguarded lookup (line ~1441):

```python
            naya_subject=Subject.objects.get(sub_name=subject)
```

with:

```python
            try:
                naya_subject = Subject.objects.get(sub_name=subject)
            except Subject.DoesNotExist:
                messages.error(request, "Subject does not exists.")
                return redirect(userDetails)
```

- [ ] **Step 5: Add the free-text input to the template**

In `templates/userDetails.html`, inside the `#subjects` modal body (near the existing `<select name="subject">`, around lines 138-171), add a second form for free-text entry:

```html
<form action="/addSubjects" method="POST" style="margin-top:12px;">
  {% csrf_token %}
  <label>Add a subject you have taught</label>
  <input type="text" name="subject" placeholder="e.g. Compiler Design" required>
  <button type="submit">Add</button>
</form>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python manage.py test home.tests.SelfAddSubjectTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add home/views.py templates/userDetails.html home/tests.py
git commit -m "feat(subjects): let teachers add their own subjects (free-text, shared pool)"
```

---

## Task 2 — Unit C: GPA *or* percentage (at least one)

**Files:**
- Modify: `home/intake.py` — add `academics_present` helper
- Modify: `home/views.py` — `studentform2` (~773-865)
- Modify: `templates/Studentform2.html` — remove `required` on `gpa`/`final_percentage` (lines 43, 48)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test for the helper**

Add to `home/tests.py`:

```python
class AcademicsPresentTests(SimpleTestCase):
    def test_both_blank_is_false(self):
        from home.intake import academics_present
        self.assertFalse(academics_present("", "   "))

    def test_gpa_only_is_true(self):
        from home.intake import academics_present
        self.assertTrue(academics_present("3.8", ""))

    def test_percentage_only_is_true(self):
        from home.intake import academics_present
        self.assertTrue(academics_present(None, "82.5"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.AcademicsPresentTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'academics_present'`.

- [ ] **Step 3: Add the helper**

Append to `home/intake.py`:

```python
def academics_present(gpa, final_percentage):
    """True if at least one of GPA / final percentage was supplied.

    The student (and the professor on the edit page) must give one or the
    other; requiring both is unnecessary. Whitespace-only counts as blank.
    """
    return bool((gpa or "").strip() or (final_percentage or "").strip())
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python manage.py test home.tests.AcademicsPresentTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing view test**

Add to `home/tests.py`:

```python
class StudentForm2AcademicsTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice",
        )

    def _post(self, **overrides):
        data = {
            "roll": "075BCT001", "naam": "alice", "prof_name": "Dr Smith",
            "uni_name": "MIT", "uni_country": "USA", "uni_program": "MS",
            "uni_deadline": "2026-12-01",
            "gpa": "3.8", "final_percentage": "82.5",
            "tentative_ranking": "Top 5%", "eca": "Robotics club",
        }
        data.update(overrides)
        return self.client.post("/studentform2", data)

    def test_both_blank_is_rejected(self):
        self._post(gpa="", final_percentage="")
        self.assertFalse(Academics.objects.filter(application=self.app).exists())

    def test_gpa_only_saves(self):
        self._post(gpa="3.8", final_percentage="")
        self.assertTrue(Academics.objects.filter(application=self.app).exists())

    def test_percentage_only_saves(self):
        self._post(gpa="", final_percentage="82.5")
        self.assertTrue(Academics.objects.filter(application=self.app).exists())
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python manage.py test home.tests.StudentForm2AcademicsTests -v 2`
Expected: FAIL — `test_both_blank_is_rejected` fails (an Academics row is created even with both blank).

- [ ] **Step 7: Enforce the rule in `studentform2`**

In `home/views.py` `studentform2`, immediately after the three file-size checks and before `info = Application.objects.get(...)` (around line 813), add:

```python
        from home.intake import academics_present
        if not academics_present(aca_gpa, final_percentage):
            messages.error(request, "Enter a GPA or a final percentage — at least one is required.")
            return render(request, "student_success.html", {
                "roll": uroll, "letter": False, "naam": naam,
                "error": "Enter a GPA or a final percentage.",
            })
```

- [ ] **Step 8: Relax the HTML required flags**

In `templates/Studentform2.html`:
- Line 43: `<input type="text" name="gpa" required>` → `<input type="text" name="gpa">`
- Line 48: `<input type="text" name="final_percentage" placeholder="e.g. 82.5" required>` → `<input type="text" name="final_percentage" placeholder="e.g. 82.5">`
- Update the two labels (lines 42, 47) to note "GPA or percentage — at least one":

```html
          <div class="input-box">
            <span class="details">GPA (or percentage below):</span>
            <input type="text" name="gpa">
          </div>

          <div class="input-box">
            <span class="details">Final Percentage Score (or GPA above)</span>
            <input type="text" name="final_percentage" placeholder="e.g. 82.5">
          </div>
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python manage.py test home.tests.AcademicsPresentTests home.tests.StudentForm2AcademicsTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 10: Commit**

```bash
git add home/intake.py home/views.py templates/Studentform2.html home/tests.py
git commit -m "feat(intake): require GPA or percentage, not both"
```

---

## Task 3 — Unit E: deadline filter + sort on the dashboard (+ required student deadline)

**Files:**
- Modify: `home/filters.py` — `FILTER_PARAMS`, `apply_application_filters`
- Modify: `home/dashboard.py` — annotate nearest deadline, optional sort
- Modify: `templates/Teacher.html` — deadline filter input, sort control, show nearest deadline
- Modify: `templates/Studentform2.html` — make `uni_deadline` required
- Modify: `home/views.py` — `studentform2` reject blank deadlines
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing filter/sort tests**

Add to `home/tests.py`:

```python
class DeadlineFilterSortTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.early = self._app("early", "075BCT001", "2026-09-01")
        self.late = self._app("late", "075BCT002", "2026-12-31")
        self.none = self._app("none", "075BCT003", None)

    def _app(self, uname, roll, deadline):
        student = StudentLoginInfo.objects.create(
            username=uname, roll_number=roll,
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        app = Application.objects.create(std=student, professor=self.prof, name=uname)
        University.objects.create(
            uni_name="U", country="USA", uni_deadline=deadline, application=app,
        )
        return app

    def test_deadline_before_excludes_later_and_null(self):
        scoped = Application.objects.filter(professor=self.prof)
        result = apply_application_filters(scoped, {"deadline": "2026-10-01"})
        names = {a.name for a in result}
        self.assertEqual(names, {"early"})

    def test_sort_by_deadline_puts_nulls_last(self):
        ctx = build_teacher_dashboard_context("12345", {"sort": "deadline"})
        # All three are pending (not generated); check pending ordering.
        pending_names = [a.name for a in ctx["student_list"]]
        self.assertEqual(pending_names[:2], ["early", "late"])
        self.assertEqual(pending_names[-1], "none")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.DeadlineFilterSortTests -v 2`
Expected: FAIL — the `deadline` param is ignored (all three returned); `sort` is ignored so ordering is arbitrary.

- [ ] **Step 3: Add the deadline filter**

In `home/filters.py`:

Change line 11:

```python
FILTER_PARAMS = ("department", "country", "college", "q", "deadline")
```

In `apply_application_filters`, after the `college` block (line 45) add:

```python
    deadline = (params.get("deadline") or "").strip()
    if deadline:
        # "Show me who needs a letter before this date": match applications
        # with a university deadline on or before it. Null deadlines are
        # excluded (they carry no urgency signal).
        queryset = queryset.filter(university__uni_deadline__lte=deadline)
```

Change the distinct guard (line 58) to include deadline:

```python
    if country or college or deadline:
```

- [ ] **Step 4: Add the nearest-deadline annotation and sort**

In `home/dashboard.py`, replace the body from line 20 to the `return` with:

```python
    from home.models import Application, TeacherInfo
    from django.db.models import F, Min

    teacher_model = TeacherInfo.objects.get(unique_id=unique_id)
    scoped = Application.objects.filter(professor__unique_id=unique_id)

    options = filter_options(scoped)

    filtered = apply_application_filters(scoped, params)
    # The nearest (earliest) university deadline is the application's urgency;
    # deadlines live on the University satellite, so annotate the minimum.
    filtered = filtered.annotate(nearest_deadline=Min("university__uni_deadline"))

    pending = filtered.filter(is_generated=False)
    generated = filtered.filter(is_generated=True).order_by("-generated_at", "-id")

    if (params.get("sort") or "").strip() == "deadline":
        # Nulls last: an application with no deadline has no urgency and sorts
        # after every dated one.
        order = F("nearest_deadline").asc(nulls_last=True)
        pending = pending.order_by(order)
        generated = generated.order_by(order)

    active_filters = {key: (params.get(key) or "").strip() for key in FILTER_PARAMS}

    return {
        "all_students": generated,
        "student_list": pending,
        "check_value": not pending.exists(),
        "std_dataharu": serializers.serialize("json", generated),
        "teacher_model": teacher_model,
        "default_template": teacher_model.customtemplates_set.filter(
            is_default=True
        ).first(),
        "filter_options": options,
        "active_filters": active_filters,
        "filters_active": any(active_filters.values()),
        "generated_count": generated.count(),
        "sort": (params.get("sort") or "").strip(),
    }
```

- [ ] **Step 5: Run the filter/sort tests to verify they pass**

Run: `python manage.py test home.tests.DeadlineFilterSortTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Add the deadline UI to the dashboard**

In `templates/Teacher.html`, add a deadline filter column inside the filter `<form>` (after the college column, before the buttons at line 94):

```html
      <div class="col-12 col-sm-6 col-lg-3">
        <label for="filter-deadline" class="form-label">Deadline before</label>
        <input class="form-control" id="filter-deadline" type="date" name="deadline"
               value="{{ active_filters.deadline }}">
      </div>
      <div class="col-12 col-sm-6 col-lg-3">
        <label for="filter-sort" class="form-label">Sort</label>
        <select class="form-control" id="filter-sort" name="sort">
          <option value="" {% if not sort %}selected{% endif %}>Default</option>
          <option value="deadline" {% if sort == 'deadline' %}selected{% endif %}>Nearest deadline</option>
        </select>
      </div>
```

Add a "Deadline" column to the recommended table. In the `<thead>` (after the `Template` header, line 149) add `<th>Deadline</th>`, and in the row body (after the `generated_template` cell, line 159) add:

```html
            <td>{% if item.nearest_deadline %}{{ item.nearest_deadline|date:"d M Y" }}{% else %}—{% endif %}</td>
```

Update the empty-state `colspan="5"` (line 183) to `colspan="6"`.

- [ ] **Step 7: Write the failing "deadline required" student test**

Add to `home/tests.py` (reuses the `StudentForm2AcademicsTests` fixture shape):

```python
class StudentDeadlineRequiredTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice",
        )

    def test_blank_deadline_is_rejected(self):
        self.client.post("/studentform2", {
            "roll": "075BCT001", "naam": "alice", "prof_name": "Dr Smith",
            "uni_name": "MIT", "uni_country": "USA", "uni_program": "MS",
            "uni_deadline": "",
            "gpa": "3.8", "final_percentage": "", "tentative_ranking": "Top 5%",
            "eca": "Robotics",
        })
        self.assertFalse(University.objects.filter(application=self.app).exists())
```

- [ ] **Step 8: Run it to verify it fails**

Run: `python manage.py test home.tests.StudentDeadlineRequiredTests -v 2`
Expected: FAIL — the university is saved with a null deadline.

- [ ] **Step 9: Enforce the deadline server-side and in HTML**

In `home/views.py` `studentform2`, after `uni_rows = parse_universities(...)` (around line 785) add:

```python
        if any(r["uni_deadline"] is None for r in uni_rows) or not uni_rows:
            messages.error(request, "Each university needs a deadline.")
            return render(request, "student_success.html", {
                "roll": uroll, "letter": False, "naam": naam,
                "error": "Each university needs a deadline.",
            })
```

In `templates/Studentform2.html` line 18, add `required`:

```html
                <input type="date" name="uni_deadline" placeholder="Deadline" required style="flex:1;min-width:130px;">
```

- [ ] **Step 10: Run the deadline-required test to verify it passes**

Run: `python manage.py test home.tests.StudentDeadlineRequiredTests -v 2`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add home/filters.py home/dashboard.py home/views.py templates/Teacher.html templates/Studentform2.html home/tests.py
git commit -m "feat(dashboard): deadline filter + nearest-deadline sort; require student deadlines"
```

---

## Task 4 — Unit B: Back button on the student form (simple version)

**Files:**
- Modify: `home/views.py` — `studentform1` GET branch (~675-694)
- Modify: `templates/Studentform2.html` — add a Back button
- Modify: `templates/Studentform1.html` — pre-fill inputs from context
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `home/tests.py`:

```python
class StudentForm1PrefillTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.other = StudentLoginInfo.objects.create(
            username="bob", roll_number="075BCT002",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice",
            strong_points="Diligent", is_generated=False,
        )

    def test_get_prefills_from_own_inprogress_application(self):
        login_as_student(self.client, self.student)
        resp = self.client.get("/studentform1")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["application"].strong_points, "Diligent")

    def test_get_does_not_prefill_another_students_application(self):
        login_as_student(self.client, self.other)
        resp = self.client.get("/studentform1")
        self.assertIsNone(resp.context.get("application"))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.StudentForm1PrefillTests -v 2`
Expected: FAIL — `KeyError`/`None`: the GET branch does not put `application` in context.

- [ ] **Step 3: Pre-fill in the `studentform1` GET branch**

In `home/views.py`, replace the GET branch (lines 675-689) with:

```python
    if request.method == "GET":
        student = current_student(request)
        if student is not None:
            teachers = TeacherInfo.objects.filter(department=student.department)
            # Resume support (Back button from step 2): pre-fill from this
            # student's own most recent not-yet-generated application. Scoped
            # via ``current_student`` — never trust a roll/name from the query.
            application = (
                Application.objects.filter(std=student, is_generated=False)
                .order_by("-id")
                .first()
            )
            project = paper = None
            selected_subjects = []
            if application is not None:
                project = Project.objects.filter(application=application).first()
                paper = Paper.objects.filter(application=application).first()
                selected_subjects = [
                    s.strip() for s in (application.subjects or "").split(",") if s.strip()
                ]
            return render(
                request,
                "Studentform1.html",
                {
                    "naam": student.username,
                    "teachers": teachers,
                    "roll": student.roll_number,
                    "application": application,
                    "project": project,
                    "paper": paper,
                    "selected_subjects": selected_subjects,
                },
            )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python manage.py test home.tests.StudentForm1PrefillTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Add the Back button on step 2**

In `templates/Studentform2.html`, replace the submit block (lines 171-173) with a Back link plus submit:

```html
          <div class="button" style="display:flex; gap:10px;">
            <a href="/studentform1" class="btn"
               style="display:inline-block;padding:10px 18px;background:#888;color:#fff;border-radius:5px;text-decoration:none;">
               &larr; Back
            </a>
            <input type="submit" value="  Submit  " />
          </div>
```

- [ ] **Step 6: Pre-fill the step-1 inputs from context**

In `templates/Studentform1.html`, set `value=` / `selected` from the new context. For each existing input, add a Django-templated value. Apply this pattern to the intake fields (do NOT change field `name=` attributes):

```html
<!-- text inputs: add value from application -->
<input type="text" name="first_name" value="{{ application.first_name|default:'' }}">
<input type="text" name="middle_name" value="{{ application.middle_name|default:'' }}">
<input type="text" name="last_name" value="{{ application.last_name|default:'' }}">
<input type="text" name="contact_number" value="{{ application.contact_number|default:'' }}">
<input type="text" name="strong_points" value="{{ application.strong_points|default:'' }}">
<input type="text" name="weak_points" value="{{ application.weak_points|default:'' }}">
<input type="text" name="linkedIn" value="{{ application.linkedIn|default:'' }}">
<!-- textareas: body from application -->
<textarea name="personal_statement">{{ application.personal_statement|default:'' }}</textarea>
<textarea name="recommendation_purpose">{{ application.recommendation_purpose|default:'' }}</textarea>
<!-- project / paper satellites -->
<input type="text" name="sproject" value="{{ project.supervised_project|default:'' }}">
<input type="text" name="pro1" value="{{ project.final_project|default:'' }}">
<input type="text" name="paper_title" value="{{ paper.paper_title|default:'' }}">
<input type="text" name="paper_link" value="{{ paper.paper_link|default:'' }}">
```

For the professor `<select name="prof">` and the dynamically-loaded subject checkboxes, mark the previously-chosen ones. The subject checkboxes are rendered by the existing jQuery `change` handler; extend that handler to tick a box whose label is in the JS array `selectedSubjects`, seeded from context:

```html
<script>
  var selectedSubjects = [
    {% for s in selected_subjects %}"{{ s|escapejs }}"{% if not forloop.last %},{% endif %}{% endfor %}
  ];
</script>
```

In the existing subject-render loop (the AJAX `success` callback that builds `subject0..N` checkboxes), add `if (selectedSubjects.indexOf(name) !== -1) checkbox.checked = true;` when creating each checkbox.

- [ ] **Step 7: Re-run the prefill tests + smoke the page**

Run: `python manage.py test home.tests.StudentForm1PrefillTests -v 2`
Expected: PASS. (Template rendering is exercised by the `resp.status_code == 200` assertion.)

- [ ] **Step 8: Commit**

```bash
git add home/views.py templates/Studentform2.html templates/Studentform1.html home/tests.py
git commit -m "feat(intake): Back button on step 2 pre-fills step 1 from saved data"
```

---

## Task 5 — Unit D: professor inline edit → regenerate → change template

Split into 5a (persist helper), 5b (wire `renderCustom` + GPA rule), 5c (dashboard Edit button + `make_letter` opens generated), 5d (make `formTeacher.html` editable).

**Files:**
- Modify: `home/intake.py` — add `apply_professor_edits`
- Modify: `home/views.py` — `renderCustom` (~1491-1533)
- Modify: `templates/Teacher.html` — Edit button on recommended rows
- Modify: `templates/formTeacher.html` — convert student-data blocks to inputs
- Test: `home/tests.py`

### Task 5a — the persist helper

- [ ] **Step 1: Write the failing helper test**

Add to `home/tests.py`:

```python
class ApplyProfessorEditsTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice",
        )
        University.objects.create(uni_name="OLD", uni_deadline="2026-01-01", application=self.app)

    def test_it_rewrites_scalars_and_satellites(self):
        from django.http import QueryDict
        from home.intake import apply_professor_edits
        post = QueryDict(mutable=True)
        post.update({
            "name": "Alice Sharma", "strong_points": "Rigorous",
            "gpa": "3.9", "final_percentage": "", "tentative_ranking": "Top 5%",
        })
        post.setlist("uni_name", ["MIT", "Stanford"])
        post.setlist("uni_country", ["USA", "USA"])
        post.setlist("uni_program", ["MS", "MS"])
        post.setlist("uni_deadline", ["2026-12-01", "2026-11-01"])
        post.setlist("subject_names", ["DBMS", "OS"])
        apply_professor_edits(self.app, post)
        self.app.refresh_from_db()
        self.assertEqual(self.app.name, "Alice Sharma")
        self.assertEqual(self.app.subjects, "DBMS,OS")
        self.assertEqual(University.objects.filter(application=self.app).count(), 2)
        self.assertFalse(University.objects.filter(uni_name="OLD").exists())
        self.assertEqual(Academics.objects.get(application=self.app).gpa, "3.9")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.ApplyProfessorEditsTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'apply_professor_edits'`.

- [ ] **Step 3: Implement the helper**

Append to `home/intake.py`:

```python
def apply_professor_edits(application, post):
    """Persist professor edits to a student's application + satellites.

    ``post`` is a QueryDict from the (professor-authenticated, already-scoped)
    edit form. Scalar Application fields, universities, academics, and the
    single paper/project rows are rewritten to match it. Satellite rewrites
    run inside one transaction so a mid-way failure cannot strand a row. The
    caller is responsible for the GPA-or-percentage check and for the
    Qualities/anecdote/template handling (kept in ``renderCustom``).
    """
    from django.db import transaction
    from home.models import Academics, Paper, Project, University  # noqa: F401

    with transaction.atomic():
        application.name = post.get("name") or application.name
        application.email = post.get("email") or application.email
        application.years_taught = post.get("yrs")
        application.subjects = ",".join(post.getlist("subject_names"))
        application.relationship_type = post.get("relationship_type")
        application.applied_level = post.get("applied_level")
        application.recommendation_purpose = post.get("recommendation_purpose")
        application.personal_statement = post.get("personal_statement")
        application.linkedIn = post.get("linkedIn")
        application.strong_points = post.get("strong_points")
        application.weak_points = post.get("weak_points")
        application.intern_company = post.get("intern_company")
        application.intern_role = post.get("intern_role")
        application.intern_duration = post.get("intern_duration")
        application.intern_outcome = post.get("intern_outcome")
        application.scholarships = post.get("scholarships")
        application.competitions_won = post.get("competitions_won")
        application.class_size = post.get("class_size") or None
        application.ranking_percentile = post.get("ranking_percentile")
        application.language_instruction = post.get("language_instruction")
        application.save()

        rows = parse_universities(
            names=post.getlist("uni_name"),
            countries=post.getlist("uni_country"),
            deadlines=post.getlist("uni_deadline"),
            programs=post.getlist("uni_program"),
        )
        save_universities(application, rows)

        Academics.objects.filter(application=application).delete()
        Academics.objects.create(
            application=application,
            gpa=post.get("gpa"),
            tentative_ranking=post.get("tentative_ranking"),
            final_percentage=post.get("final_percentage"),
        )

        Paper.objects.filter(application=application).delete()
        if post.get("paper_title") or post.get("paper_link"):
            Paper.objects.create(
                application=application,
                paper_title=post.get("paper_title"),
                paper_link=post.get("paper_link"),
            )

        Project.objects.filter(application=application).delete()
        if post.get("sproject") or post.get("pro1"):
            Project.objects.create(
                application=application,
                supervised_project=post.get("sproject"),
                final_project=post.get("pro1"),
                deployed=post.get("deploy") == "on",
            )
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python manage.py test home.tests.ApplyProfessorEditsTests -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add home/intake.py home/tests.py
git commit -m "feat(edit): apply_professor_edits persists edited application + satellites"
```

### Task 5b — wire the edits + GPA rule into `renderCustom`

- [ ] **Step 1: Write the failing view tests**

Add to `home/tests.py`:

```python
class RenderCustomEditTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.other = TeacherInfo.objects.create(
            unique_id="99999", name="Dr Other", email="other@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice", is_generated=True,
        )
        CustomTemplates.objects.create(
            template_name="Sys", template="Dear Sir, {{ student.name }}.",
            is_system=True, is_default=False,
        )

    def _edit_post(self, **overrides):
        data = {
            "roll": "075BCT001", "name": "Alice Sharma",
            "gpa": "3.9", "final_percentage": "", "tentative_ranking": "Top 5%",
            "uni_name": "MIT", "uni_country": "USA", "uni_program": "MS",
            "uni_deadline": "2026-12-01", "template_id": "",
        }
        data.update(overrides)
        return self.client.post("/renderCustom", data)

    def test_edits_are_persisted_before_preview(self):
        login_as_teacher(self.client, self.prof)
        resp = self._edit_post()
        self.assertEqual(resp.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.name, "Alice Sharma")

    def test_both_academics_blank_is_rejected(self):
        login_as_teacher(self.client, self.prof)
        resp = self._edit_post(gpa="", final_percentage="")
        self.assertEqual(resp.status_code, 302)  # redirected with an error
        self.app.refresh_from_db()
        self.assertEqual(self.app.name, "Alice")  # nothing saved

    def test_a_professor_cannot_edit_anothers_application(self):
        login_as_teacher(self.client, self.other)
        resp = self._edit_post()
        self.assertEqual(resp.status_code, 404)
        self.app.refresh_from_db()
        self.assertEqual(self.app.name, "Alice")

    def test_get_redirects(self):
        login_as_teacher(self.client, self.prof)
        resp = self.client.get("/renderCustom")
        self.assertEqual(resp.status_code, 302)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.RenderCustomEditTests -v 2`
Expected: FAIL — `test_edits_are_persisted_before_preview` fails (name unchanged) and `test_both_academics_blank_is_rejected` fails (no rejection).

- [ ] **Step 3: Extend `renderCustom`**

In `home/views.py` `renderCustom`, after the application is fetched (line 1504) and before the anecdote block, insert the GPA-or-% guard and the edit persistence:

```python
    from home.intake import academics_present, apply_professor_edits

    # The professor edits the student's data inline before generating. Enforce
    # the same "GPA or percentage" rule the student form uses, then persist.
    if not academics_present(request.POST.get("gpa"), request.POST.get("final_percentage")):
        messages.error(request, "Enter a GPA or a final percentage — at least one is required.")
        return redirect("/teacher")
    apply_professor_edits(application, request.POST)
    application.refresh_from_db()
```

Then extend the existing `Qualities.objects.update_or_create` defaults (line 1515) to also persist ECA:

```python
            "extracirricular": request.POST.get("eca"),
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python manage.py test home.tests.RenderCustomEditTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "feat(edit): persist professor edits and enforce GPA-or-% in renderCustom"
```

### Task 5c — dashboard Edit button + `make_letter` opens generated applications

- [ ] **Step 1: Write the failing test**

Add to `home/tests.py`:

```python
class MakeLetterEditEntryTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="alice", roll_number="075BCT001",
            department=self.dept, program=self.program, dob="2000-01-01",
        )
        self.prof = TeacherInfo.objects.create(
            unique_id="12345", name="Dr Smith", email="smith@example.com",
            department=self.dept,
        )
        self.app = Application.objects.create(
            std=self.student, professor=self.prof, name="Alice", is_generated=True,
        )

    def test_make_letter_opens_a_generated_application(self):
        login_as_teacher(self.client, self.prof)
        resp = self.client.post("/makeLetter", {"roll": "075BCT001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["student"].pk, self.app.pk)

    def test_dashboard_shows_an_edit_button_for_recommended(self):
        login_as_teacher(self.client, self.prof)
        resp = self.client.get("/teacher")
        self.assertContains(resp, "makeLetter")
        self.assertContains(resp, "Edit")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python manage.py test home.tests.MakeLetterEditEntryTests -v 2`
Expected: FAIL — `test_make_letter_opens_a_generated_application` passes already (make_letter has no is_generated guard), but `test_dashboard_shows_an_edit_button_for_recommended` fails (no Edit button in the recommended table). If the first also fails for a fixture reason, fix the fixture; do not add an is_generated guard.

- [ ] **Step 3: Add the Edit button to the recommended table**

In `templates/Teacher.html`, inside the recommended row's `action-row` (after the `/studentfinal` form, before the `{% if item.generated_letter %}` block, around line 172), add:

```html
                <form action='/makeLetter' method='POST' target="_blank" class="action-row">
                  {% csrf_token %}
                  <button class="btn btn-sm btn-warning" type='submit'
                          value="{{ item.std.roll_number }}" name="roll">
                    <i class="bi bi-pencil-square"></i> Edit &amp; regenerate
                  </button>
                </form>
```

- [ ] **Step 4: Run it to verify it passes**

Run: `python manage.py test home.tests.MakeLetterEditEntryTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add templates/Teacher.html home/tests.py
git commit -m "feat(dashboard): Edit & regenerate button on recommended students"
```

### Task 5d — make `formTeacher.html` editable

This converts the student-data **display** blocks in `templates/formTeacher.html` into form **inputs** inside the form that already posts to `/renderCustom`, so the professor's edits reach `apply_professor_edits`. The input `name=` attributes below are the contract with Task 5a/5b — they must match exactly.

- [ ] **Step 1: Read the current `formTeacher.html`**

Run: open `templates/formTeacher.html`. Identify the single `<form action="/renderCustom" method="POST">` that wraps the anecdote/quality/template controls, and the read-only display blocks for universities, academics, subjects, strong/weak points, papers, projects, internship, ECA, and the scalar personal fields.

- [ ] **Step 2: Move the student-data blocks inside the `/renderCustom` form and convert to inputs**

Ensure every editable block sits **inside** the `<form action="/renderCustom" method="POST">`. Replace the read-only text with inputs pre-filled from the existing context vars (`student`, `universities`, `academics`, `paper`, `project`). Use exactly these `name=`s:

```html
<!-- scalar personal / context fields -->
<input type="text" name="name" value="{{ student.name|default:'' }}">
<input type="email" name="email" value="{{ student.email|default:'' }}">
<input type="text" name="yrs" value="{{ student.years_taught|default:'' }}">
<input type="text" name="relationship_type" value="{{ student.relationship_type|default:'' }}">
<input type="text" name="applied_level" value="{{ student.applied_level|default:'' }}">
<textarea name="recommendation_purpose">{{ student.recommendation_purpose|default:'' }}</textarea>
<textarea name="personal_statement">{{ student.personal_statement|default:'' }}</textarea>
<input type="text" name="linkedIn" value="{{ student.linkedIn|default:'' }}">
<input type="text" name="strong_points" value="{{ student.strong_points|default:'' }}">
<input type="text" name="weak_points" value="{{ student.weak_points|default:'' }}">
<input type="text" name="ranking_percentile" value="{{ student.ranking_percentile|default:'' }}">
<input type="number" name="class_size" value="{{ student.class_size|default:'' }}">
<input type="text" name="language_instruction" value="{{ student.language_instruction|default:'' }}">
<input type="text" name="intern_company" value="{{ student.intern_company|default:'' }}">
<input type="text" name="intern_role" value="{{ student.intern_role|default:'' }}">
<input type="text" name="intern_duration" value="{{ student.intern_duration|default:'' }}">
<input type="text" name="intern_outcome" value="{{ student.intern_outcome|default:'' }}">
<textarea name="scholarships">{{ student.scholarships|default:'' }}</textarea>
<textarea name="competitions_won">{{ student.competitions_won|default:'' }}</textarea>
<!-- academics (Task 5b enforces GPA-or-%) -->
<input type="text" name="gpa" value="{{ academics.gpa|default:'' }}">
<input type="text" name="final_percentage" value="{{ academics.final_percentage|default:'' }}">
<input type="text" name="tentative_ranking" value="{{ academics.tentative_ranking|default:'' }}">
<!-- paper / project satellites -->
<input type="text" name="paper_title" value="{{ paper.paper_title|default:'' }}">
<input type="text" name="paper_link" value="{{ paper.paper_link|default:'' }}">
<input type="text" name="sproject" value="{{ project.supervised_project|default:'' }}">
<input type="text" name="pro1" value="{{ project.final_project|default:'' }}">
<!-- ECA -> Qualities.extracirricular (Task 5b) -->
<textarea name="eca">{{ quality.extracirricular|default:'' }}</textarea>
```

- [ ] **Step 3: Make universities a repeatable, editable block**

Replace the universities display with editable rows seeded from `universities`, using the same parallel-list `name=`s the student form uses (`uni_name`, `uni_country`, `uni_program`, `uni_deadline`) so `parse_universities` reads them unchanged:

```html
<div id="prof-universities">
  {% for u in universities %}
  <div class="uni-row" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
    <input type="text" name="uni_name" value="{{ u.uni_name|default:'' }}" placeholder="University name" required>
    <input type="text" name="uni_country" value="{{ u.country|default:'' }}" placeholder="Country">
    <input type="text" name="uni_program" value="{{ u.program_applied|default:'' }}" placeholder="Program">
    <input type="date" name="uni_deadline" value="{{ u.uni_deadline|date:'Y-m-d' }}" required>
    <button type="button" class="remove-uni">Remove</button>
  </div>
  {% empty %}
  <div class="uni-row" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
    <input type="text" name="uni_name" placeholder="University name" required>
    <input type="text" name="uni_country" placeholder="Country">
    <input type="text" name="uni_program" placeholder="Program">
    <input type="date" name="uni_deadline" required>
    <button type="button" class="remove-uni">Remove</button>
  </div>
  {% endfor %}
</div>
<button type="button" id="prof-add-uni">+ Add another university</button>
<script>
  document.getElementById('prof-add-uni').addEventListener('click', function () {
    var c = document.getElementById('prof-universities');
    var clone = c.querySelector('.uni-row').cloneNode(true);
    clone.querySelectorAll('input').forEach(function (i) { i.value = ''; });
    c.appendChild(clone);
  });
  document.getElementById('prof-universities').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-uni')) {
      var rows = this.querySelectorAll('.uni-row');
      if (rows.length > 1) e.target.closest('.uni-row').remove();
    }
  });
</script>
```

- [ ] **Step 4: Make subjects editable as checkboxes**

Render this professor's subject list (`teacher_model.subjects.all`) as checkboxes named `subject_names`, pre-ticked from the student's current CSV. Add near the subjects block:

```html
{% for s in teacher_model.subjects.all %}
<label style="display:inline-block;margin-right:12px;">
  <input type="checkbox" name="subject_names" value="{{ s.sub_name }}"
         {% if s.sub_name in student.subjects %}checked{% endif %}>
  {{ s.sub_name }}
</label>
{% endfor %}
```

Note: `{% if s.sub_name in student.subjects %}` does a substring test against the CSV — acceptable here because the checkbox value equals the stored token.

- [ ] **Step 5: Verify the whole edit→regenerate loop with the existing suite**

Run: `python manage.py test home.tests.RenderCustomEditTests home.tests.MakeLetterEditEntryTests home.tests.ApplyProfessorEditsTests -v 2`
Expected: PASS. These assert the POSTed field names round-trip through `apply_professor_edits` and the preview.

- [ ] **Step 6: Manual browser check (documented, not automated)**

The test client can't run JS or the `contenteditable` preview. By hand: dashboard → Edit & regenerate on a recommended student → change a university deadline, the GPA, and the template in the picker → Generate → confirm the preview shows the edits → download PDF and DOCX → return to dashboard and confirm the new template name, timestamp, and nearest deadline show, and Re-download serves the new file.

- [ ] **Step 7: Commit**

```bash
git add templates/formTeacher.html home/tests.py
git commit -m "feat(edit): make the generation page a full editable application form"
```

---

## Final review

- [ ] Run the full suite once: `python manage.py test home` — expect all prior tests plus the ~20 new ones to pass.
- [ ] Run `python manage.py makemigrations --check --dry-run home` — expect "No changes detected" (this plan adds no model fields).
- [ ] Dispatch the final code review over the whole branch diff.
- [ ] Use superpowers:finishing-a-development-branch.
