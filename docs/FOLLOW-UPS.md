# Outstanding Follow-Ups

Everything found during Phases 3 and 4 that was deliberately **not** fixed, with enough
context to pick up cold. Ordered by priority within each section.

Status as of the Phase 4 merge (`a7ebd05`): 345 tests pass, `makemigrations --check` clean,
`manage.py check --deploy` reports 1 accepted warning.

---

## 1. Do these before the app is publicly reachable

### 1.1 Rotate the committed credentials — MANUAL, cannot be automated
The old `SECRET_KEY` and the Gmail app password are in git history and on GitHub. Moving them
into environment variables does **not** un-publish them.

- Revoke the Gmail app password in the Google account; issue a new one.
- Generate a new key:
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- Put both in `.env` (gitignored) or real environment variables.

**Rotating `SECRET_KEY` logs out every session and invalidates every signed student cookie.**
Do it at a quiet moment.

### 1.2 Student intake views accept an identity from POST data
`studentform1`, `studentform2`, `final`, `studentfinal`, `gallery` key off POST `naam` / `roll`
with no `current_student(request)` check. A logged-in student can submit or alter an
`Application` under **another student's** identity.

This is the same bug class Phase 4b fixed for professors, in the one area the phase did not
cover. Fix the same way: resolve the student with `current_student(request)`, redirect to
`/loginStudent` when `None`, and ignore any student identifier in the request body.

### 1.3 No rate limit on the OTP flow
The OTP is 5 digits and one-shot per submission, but `/otp` can be restarted indefinitely —
roughly 90k restarts brute-forces it. Add a per-session or per-username attempt counter with a
lockout, or lengthen the code. See `home/views.py` `otp` / `OTP_check`.

### 1.4 Student identity is keyed on a non-unique column
`StudentLoginInfo.username` has no unique constraint (the PK is `roll_number`), and
`current_student` resolves with `.first()`. Signing prevents forging a name but not a
**collision**: `registerStudent` permits a duplicate display name, and `loginStudent` then
raises `MultipleObjectsReturned` — a 500 for *both* students.

Two fixes, do both: add a uniqueness check to registration, and make the signed cookie carry
`roll_number` (the real PK) instead of `username`.

### 1.5 Unauthenticated enumeration / disclosure endpoints
`feedback`, `contact`, `checkEmail`, `getdetails` are reachable with no credential. `checkEmail`
and `getdetails` confirm whether an account exists; `feedback` and `contact` can be used to send
mail through the app. Low severity individually, worth a pass together.

---

## 2. Security hardening (defence in depth)

### 2.1 Retire the legacy name fallback in `current_teacher`
`home/identity.py` falls back to parsing `"Full Name/<unique_id>"` from `User.first_name` when
`TeacherInfo.user` is null. It is **not exploitable today** — no self-service view lets a user
set their own `first_name`, and both account-creation paths now set the FK — but it is
unauthenticated-data-driven by construction.

Blocked on 3.2 (the one orphaned row). Once every `TeacherInfo` has a linked `User`, delete the
fallback and the tests that cover it.

### 2.2 Signed student cookie has no expiry or revocation
It is tamper-evident but not a session: a leaked cookie stays valid until `SECRET_KEY` rotates,
and it survives the student changing their password. Either add `max_age` and rotate on password
change, or convert students to real Django sessions (larger, but removes the whole category).

### 2.3 `is_active` is not re-checked in teacher views
Self-registered professors are inactive and `authenticate()` refuses them, so this is not
currently reachable. But `current_teacher` only requires `is_authenticated`, so a session
obtained by other means would still pass. Cheap to add.

### 2.4 Raise HSTS once TLS is confirmed
`SECURE_HSTS_SECONDS` is deliberately 3600 (one hour) because a long max-age is hard to undo.
Once HTTPS is confirmed stable: raise to one year, then consider `SECURE_HSTS_PRELOAD`. This is
the `security.W021` warning `check --deploy` reports — accepted, not overlooked.

---

## 3. Correctness bugs

### 3.1 `deleteSubjects` 500s on an unknown subject
`Subject.objects.get(sub_name=...)` is unguarded — the same bug fixed in `addSubjects` during
Phase 4a, left in its sibling. Wrap in `try/except Subject.DoesNotExist`. No test covers it.

### 3.2 `TeacherInfo` 60775 (Ayush Adhikari) is orphaned
No linked `User` and **no `User` with that email exists at all** — this professor could not log
in before Phase 4 either. Decide whether to create an account or delete the row. Blocks 2.1.

### 3.3 `make_letter` returns `None` on GET
`home/views.py` — POST-only with no `else`, so a GET falls off the end and Django turns it into
a 500. Add a redirect.

### 3.4 `Files` and `Academics` delete-then-recreate are still non-atomic
`studentform2` wraps only the `Qualities` block in `transaction.atomic()` (fixed in Phase 4a
because it caused real data loss). The `Files` and `Academics` blocks immediately above have the
identical delete-then-save pattern with no transaction — a failure mid-way leaves the
application permanently without that row.

### 3.5 Three notification sends log nothing on failure
`home/views.py` letter-generated (~253), new-application (~899) and OTP (~1056) use
`fail_silently=True` directly, so an SMTP outage is invisible. Route them through
`send_mail_safely` like the other four sites, so failures reach the log.

---

## 4. UI bugs

### 4.1 The CV button opens the transcript modal
`templates/formTeacher.html` — the transcript and CV modals **share `id="exampleModal1"`**, and
both buttons target `#exampleModal1`. Give the CV modal its own id and point its button at it.

### 4.2 The CV modal header reads "Transcript"
Same file — a copy-paste artifact from the block it was cloned from.

### 4.3 Misleading auth-failure message
`addSubjects`' not-signed-in branch says "No such Subject exists." Sibling views say
"You are not signed in as a professor."

---

## 5. Infrastructure

### 5.1 SQLite is committed and unsuitable for production
Concurrent writes will fail under real load. `dj_database_url` is already imported in
`auth/settings.py` with a commented-out Postgres block — switching is mostly configuration plus
a data migration. The committed `db.sqlite3` also lags the migrations by convention; everyone
runs `migrate` after pulling.

### 5.2 Devanagari PDF export needs a different engine
Not a font problem. `fpdf` 1.7.2 performs no complex text shaping — it will not reorder matras
or form conjuncts — so a Devanagari TTF alone produces mis-rendered text, not readable output.
Needs `fpdf2`, WeasyPrint, or ReportLab. DOCX export has never had this limitation.

### 5.3 `requirements.txt` is UTF-16
Some `pip` versions choke on it. Converting to UTF-8 is a one-liner but touches a file every
contributor depends on, so do it deliberately.

---

## 6. Cleanup

- `templates/customTemplate.html:9,11` — prose design notes referencing `test.html`, deleted in
  Phase 4a.
- `home/views.py` — roughly a dozen pre-existing `print()` debug statements that write to stdout
  on every request (visible in the test output).
- `home/views.py` is ~2000 lines. `letters.py`, `identity.py`, `filters.py` and `dashboard.py`
  now hold the extracted logic; prefer adding to those.

---

## Verifying by hand

The test suite cannot prove these, because Django's test client exempts itself from CSRF and
cannot execute JavaScript:

1. **Duplicate a starter template → pick the copy from the dropdown → confirm the body loads
   with real line breaks (not `
`) → edit → save → confirm the editor reloads populated.**
   Two prefill bugs were fixed here in Phase 3; the TinyMCE init-ordering rewrite is the
   least-verified change on that branch.
2. **Generate a letter and download both PDF and DOCX**, then re-download from the dashboard.
3. Any POST form, to confirm CSRF tokens are working in a real browser.
