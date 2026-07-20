# Phase 4b: Trustworthy Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop trusting client-controlled cookies for identity — derive the acting professor from the authenticated Django session, make the student cookie tamper-evident, and put an authorization check on the admin dashboard.

**Architecture:** Teachers already get a real Django session (`login()` at `views.py:909`), so the `unique` cookie is redundant identity sitting alongside a good session — it is replaced by a `current_teacher(request)` helper backed by a new `TeacherInfo.user` one-to-one FK. Students are not Django users and have no session, so their cookie stays a cookie but becomes a **signed** cookie, which is tamper-evident without a data-model change. The admin dashboard gets the superuser check it never had.

**Tech Stack:** Django 5.1, Python 3.12, SQLite, Django `TestCase`.

---

## The vulnerability, stated plainly

`home/views.py` reads `request.COOKIES.get("unique")` at **19 sites**. That value is the
professor's `TeacherInfo.unique_id`. Anyone can open devtools, set `unique=<someone's id>`, and
act as that professor: read their students' transcripts and CVs, generate letters in their name,
edit their templates. The Phase 2/3 views guard the value by checking the professor *exists* —
which proves nothing about who is asking.

Three separate problems, in descending severity:

1. **Teacher impersonation** — 19 cookie sites. Fixed by Tasks 1–3.
2. **`adminDashboard` has no decorator at all** (`views.py:1785`). It is publicly POST-able and
   creates `TeacherInfo` rows, i.e. mints professors. Fixed by Task 5.
3. **Student impersonation** — 7 sites reading `request.COOKIES.get("student")`. Students are
   not Django users, so there is no session to lean on. Fixed by Task 4 (signed cookies).

Also fixed in passing (Task 5): `studentPasswordChange` (`views.py:1264`) carries
`@login_required(login_url="/loginStudent")`, which tests the **teacher/admin** session. A
student can never satisfy it, and any authenticated teacher can.

---

## Environment notes for every task

- `python` is NOT on PATH. Use `venv/bin/python`.
- Run only the test classes your task touches. Full suite once, at the end.
- No AI attribution in commit messages. Never `git add CLAUDE.md` or `db.sqlite3`.
- Baseline: **~246 tests** after Phase 4a.

## The big risk in this plan

**Roughly 12 existing test classes authenticate by setting `self.client.cookies["unique"]`.**
Task 3 makes that stop working. Every one of them must switch to a real login. Task 2 provides
a shared helper so this is a mechanical change rather than 12 bespoke rewrites. Do Task 2
before Task 3 — the ordering matters.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `home/models.py` | `TeacherInfo.user` one-to-one FK | 1 |
| `home/migrations/0015_teacherinfo_user.py` | Schema | 1 |
| `home/migrations/0016_link_teacher_users.py` | Data: match existing rows by full-name suffix | 1 |
| `home/identity.py` (**new**) | `current_teacher(request)`, `require_teacher(view)`, `current_student(request)` | 2, 4 |
| `home/tests.py` | `login_as_teacher(client, teacher)` helper + migrated fixtures | 2, 3 |
| `home/views.py` | All 19 `unique` sites, 7 `student` sites, admin guard | 3, 4, 5 |

---

## Task 1: Give `TeacherInfo` a real link to `User`

**Files:**
- Modify: `home/models.py` (`TeacherInfo`)
- Create: `home/migrations/0015_teacherinfo_user.py`, `home/migrations/0016_link_teacher_users.py`
- Test: `home/tests.py`

**Why:** today the only link between a Django `User` and a `TeacherInfo` is a **string
convention** — the user's full name must be `"Full Name/<unique_id>"`, and `loginTeacher`
recovers the id with `get_full_name().split("/")[-1]` (`views.py:910-919`). That is fragile
(rename the user, break the link) and unusable as an authorization primitive. A real FK makes
`request.user -> TeacherInfo` a one-line lookup.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class TeacherUserLinkTests(TestCase):
    """TeacherInfo links to a Django User by FK, not by a name-string convention."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")

    def test_a_teacher_can_be_linked_to_a_user(self):
        user = User.objects.create_user(username="linked", password="pw")
        teacher = TeacherInfo.objects.create(
            name="Prof Linked", unique_id="T-LINK", email="l@example.com",
            department=self.dept, user=user,
        )
        self.assertEqual(teacher.user, user)
        self.assertEqual(user.teacherinfo, teacher)

    def test_the_link_is_optional(self):
        teacher = TeacherInfo.objects.create(
            name="Prof Unlinked", unique_id="T-UNLINK", email="u@example.com",
            department=self.dept,
        )
        self.assertIsNone(teacher.user)

    def test_one_user_cannot_be_two_teachers(self):
        from django.db.utils import IntegrityError
        user = User.objects.create_user(username="solo", password="pw")
        TeacherInfo.objects.create(
            name="A", unique_id="T-A1", email="a@example.com",
            department=self.dept, user=user,
        )
        with self.assertRaises(IntegrityError):
            TeacherInfo.objects.create(
                name="B", unique_id="T-B1", email="b@example.com",
                department=self.dept, user=user,
            )

    def test_deleting_the_user_does_not_delete_the_teacher(self):
        user = User.objects.create_user(username="doomed", password="pw")
        teacher = TeacherInfo.objects.create(
            name="Prof Doomed", unique_id="T-DOOM", email="d@example.com",
            department=self.dept, user=user,
        )
        user.delete()
        teacher.refresh_from_db()
        self.assertIsNone(teacher.user)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.TeacherUserLinkTests -v2`
Expected: FAIL — `TypeError: TeacherInfo() got unexpected keyword arguments: 'user'`.

- [ ] **Step 3: Add the field**

In `home/models.py`, add to `TeacherInfo`:

```python
    # The authoritative link to the login account. Historically this was encoded
    # in the User's full name as "Full Name/<unique_id>"; that string convention
    # is still honoured as a fallback for rows this FK could not be matched to.
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL,
    )
```

`User` must be imported in `home/models.py`. Check whether it already is — if not, add
`from django.contrib.auth.models import User` at the top. **Do not** use `settings.AUTH_USER_MODEL`
here unless the rest of the file already does; match the file's existing style.

- [ ] **Step 4: Generate the schema migration**

```bash
venv/bin/python manage.py makemigrations home --name teacherinfo_user
venv/bin/python manage.py migrate home
```
Expected: creates `0015_teacherinfo_user.py`; migrate reports `OK`.

- [ ] **Step 5: Write the data migration**

Create `home/migrations/0016_link_teacher_users.py`:

```python
from django.db import migrations


def link_by_full_name(apps, schema_editor):
    """Match each TeacherInfo to the User whose full name ends in /<unique_id>.

    This is the convention loginTeacher has relied on: a teacher's User has
    ``first_name`` (or full name) of the form "Full Name/<unique_id>".
    """
    TeacherInfo = apps.get_model("home", "TeacherInfo")
    User = apps.get_model("auth", "User")

    for teacher in TeacherInfo.objects.filter(user__isnull=True):
        if not teacher.unique_id:
            continue
        suffix = f"/{teacher.unique_id}"
        match = None
        for user in User.objects.all():
            full = f"{user.first_name} {user.last_name}".strip()
            if full.endswith(suffix) or user.first_name.endswith(suffix):
                match = user
                break
        if match and not TeacherInfo.objects.filter(user=match).exists():
            teacher.user = match
            teacher.save(update_fields=["user"])


def unlink(apps, schema_editor):
    TeacherInfo = apps.get_model("home", "TeacherInfo")
    TeacherInfo.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("home", "0015_teacherinfo_user"),
    ]

    operations = [
        migrations.RunPython(link_by_full_name, unlink),
    ]
```

- [ ] **Step 6: Apply and report the match rate**

```bash
venv/bin/python manage.py migrate home
venv/bin/python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','auth.settings')
django.setup()
from home.models import TeacherInfo
total = TeacherInfo.objects.count()
linked = TeacherInfo.objects.filter(user__isnull=False).count()
print(f'{linked}/{total} teachers linked to a User')
for t in TeacherInfo.objects.filter(user__isnull=True):
    print('  UNLINKED:', t.unique_id, t.name)
"
```

**Report the match rate.** Unlinked rows are expected — some `TeacherInfo` records may have no
login account at all. They keep working through the name-string fallback in Task 2. Do not
delete or invent users for them.

- [ ] **Step 7: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.TeacherUserLinkTests -v2`
Expected: `OK` (4 tests).

- [ ] **Step 8: Commit**

```bash
git add home/models.py home/migrations/0015_teacherinfo_user.py home/migrations/0016_link_teacher_users.py home/tests.py
git commit -m "feat(auth): link TeacherInfo to its login account by foreign key"
```

---

## Task 2: The identity helpers, and a test login helper

**Files:**
- Create: `home/identity.py`
- Modify: `home/tests.py` (add `login_as_teacher`)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class CurrentTeacherTests(TestCase):
    """current_teacher resolves the acting professor from the session, not a cookie."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.user = User.objects.create_user(username="ct", password="pw")
        self.teacher = TeacherInfo.objects.create(
            name="Prof CT", unique_id="T-CT", email="ct@example.com",
            department=self.dept, user=self.user,
        )
        self.factory = RequestFactory()

    def _request(self, user=None, cookies=None):
        request = self.factory.get("/")
        request.user = user or AnonymousUser()
        request.COOKIES.update(cookies or {})
        return request

    def test_an_authenticated_linked_user_resolves(self):
        from home.identity import current_teacher
        self.assertEqual(current_teacher(self._request(self.user)), self.teacher)

    def test_an_anonymous_request_resolves_to_none(self):
        from home.identity import current_teacher
        self.assertIsNone(current_teacher(self._request()))

    def test_a_forged_cookie_is_ignored(self):
        # The whole point of this phase.
        from home.identity import current_teacher
        victim_user = User.objects.create_user(username="victim", password="pw")
        TeacherInfo.objects.create(
            name="Victim", unique_id="T-VICTIM", email="v@example.com",
            department=self.dept, user=victim_user,
        )
        request = self._request(self.user, {"unique": "T-VICTIM"})
        self.assertEqual(current_teacher(request), self.teacher)

    def test_a_cookie_alone_grants_nothing(self):
        from home.identity import current_teacher
        self.assertIsNone(current_teacher(self._request(None, {"unique": "T-CT"})))

    def test_an_unlinked_teacher_resolves_by_the_name_convention(self):
        # Legacy rows the data migration could not match keep working.
        from home.identity import current_teacher
        legacy_user = User.objects.create_user(username="legacy", password="pw")
        legacy_user.first_name = "Prof Legacy/T-LEGACY"
        legacy_user.save()
        legacy = TeacherInfo.objects.create(
            name="Prof Legacy", unique_id="T-LEGACY", email="lg@example.com",
            department=self.dept,
        )
        self.assertEqual(current_teacher(self._request(legacy_user)), legacy)

    def test_an_authenticated_non_teacher_resolves_to_none(self):
        from home.identity import current_teacher
        plain = User.objects.create_user(username="plain", password="pw")
        self.assertIsNone(current_teacher(self._request(plain)))
```

Add to the imports at the top of `home/tests.py` if absent:
```python
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.CurrentTeacherTests -v2`
Expected: FAIL — `ModuleNotFoundError: No module named 'home.identity'`.

- [ ] **Step 3: Create `home/identity.py`**

```python
"""Who is acting on this request.

Identity used to come from client-controlled cookies (``unique`` for a professor,
``student`` for a student), which any visitor could set to impersonate anyone.
Professors have a real Django session, so they resolve from ``request.user``.
Students are not Django users, so their cookie remains a cookie -- but a signed
one, which is tamper-evident.
"""

def current_teacher(request):
    """The ``TeacherInfo`` acting on this request, or ``None``.

    Resolution order:
    1. the ``TeacherInfo.user`` one-to-one link (authoritative), then
    2. the legacy ``"Full Name/<unique_id>"`` convention, for rows the data
       migration could not match to an account.

    The ``unique`` cookie is never consulted.
    """
    from home.models import TeacherInfo

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    teacher = TeacherInfo.objects.filter(user=user).first()
    if teacher:
        return teacher

    # Legacy fallback: the login account encodes the id in its name.
    full_name = (user.get_full_name() or user.first_name or "").strip()
    if "/" not in full_name:
        return None
    unique_id = full_name.rsplit("/", 1)[-1].strip()
    if not unique_id:
        return None
    return TeacherInfo.objects.filter(unique_id=unique_id).first()
```

Note there is deliberately **no `require_teacher` decorator**. Task 3 converts 17 views that each
need the resolved `TeacherInfo` inside the body anyway, and a decorator that injects it as a
positional argument would change every signature for no gain. The three-line inline guard is the
smaller diff.

- [ ] **Step 4: Run test to verify it passes**

Run: `venv/bin/python manage.py test home.tests.CurrentTeacherTests -v2`
Expected: `OK` (6 tests).

- [ ] **Step 5: Add the shared test login helper**

Task 3 has to migrate ~12 test classes off cookie authentication. Add this near the top of
`home/tests.py`, after the imports and before the first test class:

```python
def login_as_teacher(client, teacher, password="test-pw"):
    """Sign ``client`` in as the Django user behind ``teacher``.

    Creates and links a User if the TeacherInfo does not have one. Replaces the
    old ``client.cookies["unique"] = ...`` idiom, which no longer authenticates.
    """
    user = teacher.user
    if user is None:
        user = User.objects.create_user(
            username=f"user-{teacher.unique_id}", password=password
        )
        user.first_name = f"{teacher.name}/{teacher.unique_id}"
        user.save()
        teacher.user = user
        teacher.save(update_fields=["user"])
    else:
        user.set_password(password)
        user.save()
    client.force_login(user)
    return user
```

- [ ] **Step 6: Test the helper**

Append to `home/tests.py`:

```python
class LoginHelperTests(TestCase):
    """The shared test helper really authenticates."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.teacher = TeacherInfo.objects.create(
            name="Prof LH", unique_id="T-LH", email="lh@example.com",
            department=self.dept,
        )

    def test_it_creates_and_links_a_user(self):
        login_as_teacher(self.client, self.teacher)
        self.teacher.refresh_from_db()
        self.assertIsNotNone(self.teacher.user)

    def test_the_client_is_authenticated_afterwards(self):
        login_as_teacher(self.client, self.teacher)
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)

    def test_it_reuses_an_existing_user(self):
        user = User.objects.create_user(username="existing", password="pw")
        self.teacher.user = user
        self.teacher.save()
        self.assertEqual(login_as_teacher(self.client, self.teacher), user)
```

`test_the_client_is_authenticated_afterwards` will only pass once Task 3 lands — until then
`/teacher` still reads the cookie. **Expect it to fail here and pass after Task 3**; note that
in your report rather than weakening it.

- [ ] **Step 7: Commit**

```bash
git add home/identity.py home/tests.py
git commit -m "feat(auth): resolve the acting professor from the session"
```

---

## Task 3: Move every teacher view onto `current_teacher`

**Files:**
- Modify: `home/views.py` — all 19 `request.COOKIES.get("unique")` sites
- Modify: `home/tests.py` — every class that authenticates by cookie
- Test: `home/tests.py`

**This is the largest and riskiest task in the plan.** Split it into two commits: views first,
then the test migration, so a bisect can tell them apart.

The 19 sites, from the survey:

| line | function | current guard |
|---|---|---|
| 95, 98 | `index` | `.exists()` check |
| 190 | `final` | **unguarded** |
| 264 | `registerStudent` | `.exists()` |
| 327 | `loginStudent` | `.exists()` |
| 424 | `make_letter` | **unguarded**, has `@login_required` |
| 887 | `loginTeacher` | gated on the `username` cookie |
| 1130 | `userDetails` | none |
| 1168 | `profileUpdate` | none |
| 1176 | `profileUpdateRequest` | none |
| 1412 | `deleteSubjects` | none |
| 1558 | `teacher` | guard-and-redirect |
| 1574 | `renderCustom` | guard-and-redirect |
| 1610 | `template` | guard-and-redirect |
| 1628 | `getTemplate` | guard-and-redirect |
| 1685 | `duplicate_template` | guard-and-redirect |
| 1867 | `download_generated` | guard-and-redirect |
| 1903 | `download_letter` | guard-and-redirect |

(`edit` at 1457 was deleted in Phase 4a.)

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class CookieImpersonationTests(TestCase):
    """A forged cookie must not act as anyone (the Phase 4b headline)."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.victim = TeacherInfo.objects.create(
            name="Victim Prof", unique_id="T-VIC", email="vic@example.com",
            department=self.dept,
        )
        self.student = StudentLoginInfo.objects.create(
            username="Victim Student", roll_number="080BCT950", department=self.dept,
            program=self.program, password="x", dob="2000-01-01",
        )
        self.application = Application.objects.create(
            name="Victim Student", std=self.student, professor=self.victim,
        )
        CustomTemplates.objects.create(
            template_name="Victim Template", template="secret",
            professor=self.victim, is_default=True,
        )

    def test_a_forged_cookie_cannot_reach_the_dashboard(self):
        self.client.cookies["unique"] = "T-VIC"
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/loginTeacher", response["Location"])

    def test_a_forged_cookie_cannot_list_templates(self):
        self.client.cookies["unique"] = "T-VIC"
        response = self.client.get("/makeTemplate")
        self.assertEqual(response.status_code, 302)

    def test_a_forged_cookie_cannot_preview_a_letter(self):
        self.client.cookies["unique"] = "T-VIC"
        response = self.client.post("/renderCustom", {"roll": "080BCT950"})
        self.assertEqual(response.status_code, 302)

    def test_a_forged_cookie_cannot_export_a_letter(self):
        self.client.cookies["unique"] = "T-VIC"
        response = self.client.post(
            "/download_letter/", {"roll": "080BCT950", "format": "pdf"}
        )
        self.assertEqual(response.status_code, 302)

    def test_a_forged_cookie_cannot_write_templates(self):
        self.client.cookies["unique"] = "T-VIC"
        self.client.post("/getTemplate", {"content": "x", "templateName": "Injected"})
        self.assertFalse(
            CustomTemplates.objects.filter(template_name="Injected").exists()
        )

    def test_a_forged_cookie_cannot_duplicate_templates(self):
        self.client.cookies["unique"] = "T-VIC"
        system = CustomTemplates.objects.filter(is_system=True).first()
        self.client.post("/duplicateTemplate", {"template_id": system.pk})
        self.assertEqual(
            CustomTemplates.objects.filter(professor=self.victim).count(), 1
        )

    def test_one_professor_cannot_act_as_another_by_cookie(self):
        # Signed in as a real professor, but forging someone else's cookie.
        attacker = TeacherInfo.objects.create(
            name="Attacker", unique_id="T-ATK", email="atk@example.com",
            department=self.dept,
        )
        login_as_teacher(self.client, attacker)
        self.client.cookies["unique"] = "T-VIC"
        response = self.client.get("/teacher")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Victim Template")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.CookieImpersonationTests -v2`
Expected: FAIL on most — the forged cookie currently works.

- [ ] **Step 3: Convert the guard-and-redirect views**

For each of `teacher`, `renderCustom`, `template`, `getTemplate`, `duplicate_template`,
`download_generated`, `download_letter`, replace:

```python
    unique = request.COOKIES.get("unique")
    if not unique or not TeacherInfo.objects.filter(unique_id=unique).exists():
        return redirect("/loginTeacher")
```

with:

```python
    teacher = current_teacher(request)
    if teacher is None:
        return redirect("/loginTeacher")
    unique = teacher.unique_id
```

Keeping a local `unique = teacher.unique_id` means the existing queries
(`professor__unique_id=unique`) need no further change — a deliberately small diff. Where a
view already resolves `TeacherInfo.objects.get(unique_id=unique)` afterwards, delete that
lookup and use `teacher` directly.

Add to the imports at the top of `home/views.py`:
```python
from home.identity import current_teacher
```

- [ ] **Step 4: Convert the unguarded views**

`final` (190), `make_letter` (424), `userDetails` (1130), `profileUpdate` (1168),
`profileUpdateRequest` (1176), `deleteSubjects` (1412) currently read the cookie with no check
at all. Give each the same treatment. `make_letter` already has `@login_required`; keep it and
add the resolution — `login_required` proves *someone* is logged in, not that they are the
professor whose data is being read.

For `index` (95), `registerStudent` (264), `loginStudent` (327): these use the cookie to decide
whether to show a logged-in teacher view. Replace the `.exists()` check with
`current_teacher(request) is not None` and use the returned object.

`loginTeacher` (887) is the login view itself — it runs *after* `login()`, so
`current_teacher(request)` works there too. Replace the `username`-cookie gate with it.

**Do not remove the `set_cookie("unique", ...)` call at `views.py:924` in this task.** Templates
may still read it, and Task 6 removes it deliberately once nothing depends on it.

- [ ] **Step 5: Run the impersonation tests**

Run: `venv/bin/python manage.py test home.tests.CookieImpersonationTests home.tests.CurrentTeacherTests -v2`
Expected: `OK`.

- [ ] **Step 6: Commit the view changes**

```bash
git add home/views.py home/tests.py
git commit -m "fix(security): resolve the acting professor from the session, not a cookie"
```

- [ ] **Step 7: Migrate the existing tests**

Find every class that authenticates by cookie:

```bash
grep -n 'cookies\["unique"\]' home/tests.py
```

For each, replace `self.client.cookies["unique"] = "T-X"` with
`login_as_teacher(self.client, self.teacher)`.

**Three cases need thought, not mechanical replacement:**
- Tests asserting a **stale/unknown cookie redirects** (e.g. `test_a_stale_cookie_redirects_to_login`)
  now test nothing meaningful, because no cookie authenticates. Rewrite them as
  "an unauthenticated request redirects" — drop the cookie line and assert the 302.
- Tests asserting **cross-professor 404s** must log in as the *other* professor rather than
  setting their cookie.
- `MakeLetterTemplateListTests` already does `force_login` with a `"Name/unique_id"` first name.
  It can move to `login_as_teacher` for consistency, or stay — your call, say which.

- [ ] **Step 8: Run the affected classes**

Run each class you touched. Then:
Run: `venv/bin/python manage.py test home -v2`
Expected: `OK`. This is the one mid-plan full-suite run, justified because Task 3 touches
every teacher-facing test.

- [ ] **Step 9: Commit the test migration**

```bash
git add home/tests.py
git commit -m "test: authenticate teachers by session instead of cookie"
```

---

## Task 4: Make the student cookie tamper-evident

**Files:**
- Modify: `home/identity.py` (add `current_student`, `set_student_cookie`)
- Modify: `home/views.py` — the 7 `request.COOKIES.get('student')` sites and the setter at `views.py:361`
- Test: `home/tests.py`

**Why signed cookies rather than sessions:** students are not Django `User`s
(`StudentLoginInfo` is a plain model with its own hashed password), so there is no session to
lean on and converting them is a much larger change than this plan should take on. Django's
`set_signed_cookie` / `get_signed_cookie` sign the value with `SECRET_KEY`, so a student cannot
forge another student's identity without the key. This is a real fix, not a cosmetic one —
but be honest in the README that it is weaker than a session (no server-side revocation).

The 7 read sites: `views.py:59` (`index`), `229` (`registerStudent`), `306` (`loginStudent`),
`662` (`studentform1`), `864` (`loginTeacher`), `1153` (`studentDetails`), `1272`
(`studentPasswordChange`). Set once at `views.py:361`; deleted at `945`, `1227`, `1284`.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class StudentCookieSigningTests(TestCase):
    """The student cookie must be tamper-evident."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="Real Student", roll_number="080BCT960", department=self.dept,
            program=self.program, password=make_password("pw"), dob="2000-01-01",
        )
        self.victim = StudentLoginInfo.objects.create(
            username="Other Student", roll_number="080BCT961", department=self.dept,
            program=self.program, password=make_password("pw"), dob="2000-01-01",
        )
        self.factory = RequestFactory()

    def _request(self, cookies):
        request = self.factory.get("/")
        request.COOKIES.update(cookies)
        return request

    def test_an_unsigned_cookie_is_rejected(self):
        from home.identity import current_student
        self.assertIsNone(current_student(self._request({"student": "Other Student"})))

    def test_a_signed_cookie_resolves(self):
        from django.core import signing
        from home.identity import STUDENT_COOKIE_SALT, current_student
        signed = signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT).sign("Real Student")
        self.assertEqual(
            current_student(self._request({"student": signed})), self.student
        )

    def test_a_tampered_signature_is_rejected(self):
        from django.core import signing
        from home.identity import STUDENT_COOKIE_SALT, current_student
        signed = signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT).sign("Real Student")
        tampered = signed.replace("Real Student", "Other Student", 1)
        self.assertIsNone(current_student(self._request({"student": tampered})))

    def test_a_missing_cookie_resolves_to_none(self):
        from home.identity import current_student
        self.assertIsNone(current_student(self._request({})))

    def test_a_signed_cookie_for_a_deleted_student_resolves_to_none(self):
        from django.core import signing
        from home.identity import STUDENT_COOKIE_SALT, current_student
        signed = signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT).sign("Ghost")
        self.assertIsNone(current_student(self._request({"student": signed})))

    def test_login_sets_a_signed_cookie(self):
        response = self.client.post("/loginStudent", {
            "username": "Real Student", "password": "pw",
        })
        raw = response.cookies.get("student")
        self.assertIsNotNone(raw)
        self.assertNotEqual(raw.value, "Real Student")
        self.assertIn(":", raw.value)
```

`make_password` must be imported in `home/tests.py` — check and add
`from django.contrib.auth.hashers import make_password` if absent.

**`test_login_sets_a_signed_cookie` posts to `/loginStudent` with field names I have guessed.**
Read the real view at `views.py:301` and use its actual POST field names and success path. If
login requires more fields, supply them. Tell me what you had to change.

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.StudentCookieSigningTests -v2`
Expected: FAIL — `ImportError: cannot import name 'current_student'`.

- [ ] **Step 3: Add the helpers to `home/identity.py`**

```python
from django.core import signing

# Namespaces the signature so a student cookie cannot be replayed elsewhere.
STUDENT_COOKIE_SALT = "home.student-identity"
STUDENT_COOKIE_NAME = "student"


def current_student(request):
    """The ``StudentLoginInfo`` acting on this request, or ``None``.

    The cookie is signed with ``SECRET_KEY``, so a tampered or hand-written
    value fails verification instead of impersonating another student.
    """
    from home.models import StudentLoginInfo

    raw = request.COOKIES.get(STUDENT_COOKIE_NAME)
    if not raw:
        return None
    try:
        username = signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT).unsign(raw)
    except signing.BadSignature:
        return None
    return StudentLoginInfo.objects.filter(username=username).first()


def set_student_cookie(response, student):
    """Sign the student's identity into ``response``."""
    response.set_signed_cookie(
        STUDENT_COOKIE_NAME,
        str(student.username),
        salt=STUDENT_COOKIE_SALT,
        httponly=True,
        samesite="Lax",
    )
    return response
```

- [ ] **Step 4: Convert the view sites**

Replace the setter at `views.py:361` (`response.set_cookie('student', student)`) with
`set_student_cookie(response, student)` — note the original stringifies the model via `__str__`,
so confirm `str(student)` and `student.username` are the same value before switching, and say
what you found.

Replace each of the 7 reads with `current_student(request)`, using the returned object rather
than re-querying by username.

Import both helpers in `home/views.py`.

**Deletion sites** (`views.py:945`, `1227`, `1284`) use `delete_cookie('student')`, which works
unchanged for signed cookies. Leave them.

- [ ] **Step 5: Run tests**

Run: `venv/bin/python manage.py test home.tests.StudentCookieSigningTests home.tests.Studentform1PostTests home.tests.Studentform2PostTests -v2`
Expected: `OK`.

**Any existing test that sets `client.cookies["student"] = "name"` directly will now fail.**
Find them with `grep -n 'cookies\["student"\]' home/tests.py` and switch them to
`self.client.cookies["student"] = signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT).sign(name)`,
or add a `login_as_student(client, student)` helper alongside `login_as_teacher`. Prefer the
helper if there is more than one call site.

- [ ] **Step 6: Commit**

```bash
git add home/identity.py home/views.py home/tests.py
git commit -m "fix(security): sign the student identity cookie"
```

---

## Task 5: Authorize the admin dashboard and fix the wrong decorator

**Files:**
- Modify: `home/views.py` (`adminDashboard`, `studentPasswordChange`)
- Test: `home/tests.py`

`adminDashboard` (`views.py:1785`) has **no decorator and no superuser check**, yet it POSTs to
create `TeacherInfo` rows — anyone can mint a professor. `studentPasswordChange`
(`views.py:1264`) carries `@login_required(login_url="/loginStudent")`, which tests the
teacher/admin session: a student can never satisfy it, and any authenticated teacher can.

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class AdminAuthorizationTests(TestCase):
    """The admin dashboard is superuser-only."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")

    def test_anonymous_cannot_reach_the_dashboard(self):
        response = self.client.get("/adminDashboard")
        self.assertEqual(response.status_code, 302)

    def test_anonymous_cannot_create_a_teacher(self):
        before = TeacherInfo.objects.count()
        self.client.post("/adminDashboard", {
            "name": "Injected Prof", "email": "inj@example.com",
            "department": self.dept.pk,
        })
        self.assertEqual(TeacherInfo.objects.count(), before)

    def test_a_plain_user_cannot_reach_the_dashboard(self):
        user = User.objects.create_user(username="plain", password="pw")
        self.client.force_login(user)
        response = self.client.get("/adminDashboard")
        self.assertEqual(response.status_code, 302)

    def test_a_superuser_can_reach_the_dashboard(self):
        admin = User.objects.create_superuser(
            username="root", password="pw", email="root@example.com"
        )
        self.client.force_login(admin)
        response = self.client.get("/adminDashboard")
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.AdminAuthorizationTests -v2`
Expected: FAIL — anonymous gets 200 and creates a teacher.

- [ ] **Step 3: Add the guard**

Add to the imports at the top of `home/views.py` (verify absent first):
```python
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
```

Decorate `adminDashboard`:
```python
@user_passes_test(lambda u: u.is_authenticated and u.is_superuser, login_url="/loginAdmin")
def adminDashboard(request):
```

Check whether other admin-only views in the file (anything reachable from `adminDashboard.html`)
need the same treatment, and **report the list rather than decorating them all silently** — I
want to see the blast radius before it widens.

- [ ] **Step 4: Fix `studentPasswordChange`'s decorator**

Remove `@login_required(login_url="/loginStudent")` from `studentPasswordChange`
(`views.py:1264`) and replace the identity check inside with `current_student(request)`:

```python
def studentPasswordChange(request):
    student = current_student(request)
    if student is None:
        return redirect("/loginStudent")
```

Read the existing body first and adapt — do not delete logic you do not understand.

Add a test:
```python
class StudentPasswordChangeAuthTests(TestCase):
    """The student password page authenticates students, not teachers."""

    def setUp(self):
        self.dept = Department.objects.create(dept_name="BCT")
        self.program = Program.objects.create(program_name="BE-BCT", department=self.dept)
        self.student = StudentLoginInfo.objects.create(
            username="Pw Student", roll_number="080BCT970", department=self.dept,
            program=self.program, password=make_password("pw"), dob="2000-01-01",
        )

    def test_anonymous_is_redirected(self):
        self.assertEqual(
            self.client.get("/studentPasswordChange").status_code, 302
        )

    def test_a_logged_in_teacher_is_not_treated_as_a_student(self):
        teacher = TeacherInfo.objects.create(
            name="Prof PW", unique_id="T-PW", email="pw@example.com",
            department=self.dept,
        )
        login_as_teacher(self.client, teacher)
        self.assertEqual(
            self.client.get("/studentPasswordChange").status_code, 302
        )
```

Confirm the URL path against `home/urls.py` before relying on it.

- [ ] **Step 5: Run tests**

Run: `venv/bin/python manage.py test home.tests.AdminAuthorizationTests home.tests.StudentPasswordChangeAuthTests -v2`
Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "fix(security): require a superuser for the admin dashboard"
```

---

## Task 6: Retire the `unique` cookie

**Files:**
- Modify: `home/views.py:924` (the `set_cookie`), `templates/` (any reader)
- Test: `home/tests.py`

Nothing should depend on the `unique` cookie once Task 3 lands. Remove it so it cannot be
mistaken for a credential again.

- [ ] **Step 1: Find every remaining reference**

```bash
grep -rn '"unique"\|COOKIES.get..unique\|set_cookie..unique\|delete_cookie..unique' home/ templates/ --include=*.py --include=*.html
```

Report everything you find. **If any template reads it, stop and tell me** — that is a view
context change, not a cookie removal.

- [ ] **Step 2: Write the failing test**

```python
class UniqueCookieRetiredTests(TestCase):
    """The unique cookie is no longer issued."""

    def test_login_does_not_set_a_unique_cookie(self):
        dept = Department.objects.create(dept_name="BCT")
        teacher = TeacherInfo.objects.create(
            name="Prof RC", unique_id="T-RC", email="rc@example.com", department=dept,
        )
        user = User.objects.create_user(
            username="rc", password="pw", email="rc@example.com"
        )
        user.first_name = "Prof RC/T-RC"
        user.save()
        teacher.user = user
        teacher.save()
        response = self.client.post("/loginTeacher", {
            "email": "rc@example.com", "password": "pw",
        })
        self.assertNotIn("unique", response.cookies)

    def test_views_no_longer_read_the_unique_cookie(self):
        import inspect
        from home import views
        self.assertNotIn('COOKIES.get("unique")', inspect.getsource(views))
        self.assertNotIn("COOKIES.get('unique')", inspect.getsource(views))
```

`test_login_does_not_set_a_unique_cookie` posts field names I have guessed. Read
`loginTeacher` at `views.py:862` and use its real ones.

- [ ] **Step 3: Remove the setter**

Delete `response.set_cookie("unique", unique)` at `views.py:924`. Keep the
`delete_cookie("unique")` in `logoutUser` (`views.py:937`) so existing browsers get the stale
cookie cleared — add a comment saying that is why it stays.

Decide what to do with the `username` cookie, which is read at 8 sites
(`1244`, `1251`, `1297`, `1322`, `1347`, `1375`, `1410`, and `885`). It is display data, not a
credential, but those views use it to *select rows*. **Report the list and your recommendation
rather than changing them in this task** — that is Phase 4b scope creep and I want to decide.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python manage.py test home -v2`
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add home/views.py home/tests.py
git commit -m "chore(auth): stop issuing the unique identity cookie"
```

---

## Task 7: Documentation and full-suite verification

- [ ] **Step 1: Full suite**

```bash
venv/bin/python manage.py test home -v2
venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: `OK` and `No changes detected`.

- [ ] **Step 2: Document the model in `README.md`**

Add under the "Teacher / Professor" section:

```markdown
> **How identity works.** Professors authenticate with a Django session; the acting professor is
> resolved from `request.user` via the `TeacherInfo.user` link (falling back to the legacy
> `"Full Name/<unique_id>"` naming for accounts predating that link). Students are not Django
> users — their identity travels in a cookie signed with `SECRET_KEY`, which is tamper-evident
> but, unlike a session, cannot be revoked server-side. Rotating `SECRET_KEY` logs every student out.
```

Update the "Important — teacher/superuser naming" note in the setup section to say the
`/<unique_id>` suffix is now a **fallback**, and that linking the `TeacherInfo.user` field in
the admin is the preferred way.

- [ ] **Step 3: Update the test count** in `README.md` from the Step 1 number.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document how professor and student identity resolve"
```

---

## Notes for the reviewer

1. **The headline claim: can you still impersonate a professor?** Try every route — forged
   `unique` cookie alone; forged cookie plus a valid session for a different professor; a
   session for a `User` with a hand-crafted `"X/T-VICTIM"` first name but no FK link; a
   `TeacherInfo` whose `user` FK points at a deleted account. Report anything that gets through.
2. **The legacy name fallback is the weak point.** `current_teacher` falls back to parsing
   `"Full Name/<unique_id>"`. Can a non-teacher user set their own first name to
   `"Whatever/T-VICTIM"` and become that professor? Check whether any self-service view lets a
   user edit their own `first_name` — if one does, that is a live escalation path and the
   fallback must be removed or gated.
3. **Signed cookies:** confirm a cookie signed for student A cannot be replayed as student B,
   and that changing `SECRET_KEY` invalidates all of them.
4. **Did the test migration weaken anything?** ~12 classes moved off cookie auth. Sample them
   and confirm the assertions still test what their names claim — particularly the
   cross-professor isolation tests, which are the ones that would silently become vacuous.
5. **`adminDashboard`:** confirm the guard covers POST as well as GET, and check whether any
   sibling admin view is still unguarded.
