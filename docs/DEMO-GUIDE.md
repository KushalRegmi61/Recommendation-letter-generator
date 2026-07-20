# Demo Guide

Everything you need to run the app and demo it. Written for the demo on **21 July 2026**.

---

## Part 1 — Start the app (do this the night before, not 10 minutes prior)

### 1. Activate the virtualenv

```bash
cd ~/clz/6th_sem_labs/software_eng/Recommendation-letter-generator
source venv/bin/activate
```

### 2. Run migrations — DO NOT SKIP THIS

**This is the #1 thing that will break your demo.** The `db.sqlite3` committed to the repo is
deliberately behind the migrations. If you pull, switch branches, or clone fresh, the app
crashes on the first page with `no such column: TeacherInfo.user_id`.

```bash
python manage.py migrate
```

You should see `0011` through `0018` apply. If it says "No migrations to apply", you're already good.

### 3. Confirm the environment file exists

```bash
cat .env
```

You should see `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=true`, `DJANGO_ALLOWED_HOSTS`, and two empty
`EMAIL_*` lines. If `.env` is missing, create it:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print('DJANGO_SECRET_KEY=' + get_random_secret_key())" > .env
cat >> .env <<'EOF'
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EOF
```

`.env` is gitignored — it will never be committed.

### 4. Sanity check

```bash
python manage.py check
python manage.py test home
```

Expect `System check identified no issues` and `Ran 345 tests ... OK` (about 15 seconds).

### 5. Set a password you'll remember for the demo account

You need to know the password for the professor you demo with. Set one:

```bash
python manage.py changepassword binichand_59574
```

Use something you can type under pressure. Do the same for `amanshakya_59574` if you want a
second professor, and note the admin: `python manage.py changepassword admin`.

### 6. Run it

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/**. Admin is at **/admin/**.

---

## Part 2 — Your demo accounts

These already exist in the database.

| Role | Login at | Username / email | Notes |
|---|---|---|---|
| **Professor (main demo)** | `/loginTeacher` | `beanie.0412@gmail.com` | Bini Chand. **Has 1 pending request** — use this one |
| Professor (second) | `/loginTeacher` | `aman.shakya@ioe.edu.np` | Aman Shakya. Has 2 already-recommended students |
| Admin | `/loginAdmin` | `admin` | Superuser; also works at `/admin/` |
| Student | `/loginStudent` | `Bini Chand` | Roll `079BCT033` |

**The professor login form asks for your email, not a username.** The field is labelled
"Enter email" — that's correct, it's the email that identifies the account.

**Ayush Adhikari (60775) cannot log in** — that `TeacherInfo` row has no user account attached.
It's known orphaned data. Don't pick that one.

---

## Part 3 — The demo script

Roughly 8–10 minutes. The order matters: it builds from "a student asks" to "a letter comes out"
to "and here's how we know it's safe".

### Act 1 — The professor's dashboard (2 min)

1. Go to `/loginTeacher`, log in as **beanie.0412@gmail.com**.
2. You land on the dashboard. Point out the two lists: **pending requests** and
   **students you have recommended**.
3. **Search.** Type `bini` in the search box — it matches name, roll number *or* email. Then
   show that multiple words all have to match: `bini 079` narrows further. Say: *"this is an
   AND search, so adding words narrows rather than widens."*
4. **Filter.** Use the Department / Country / College dropdowns. Point out they're typeable —
   type `us` and it matches `USA` — and that they only suggest values from *your own*
   applications. Filters and search combine, and both apply to the pending *and* recommended
   lists, so you can answer *"whom have I recommended who applied to the USA."*
5. Hit **Clear** to reset.

### Act 2 — The template library (2 min)

6. Click **Create / Edit Templates** (`/makeTemplate`).
7. Point out the **Starter templates** section — three ship with the app: *Formal / Academic*,
   *Research / Graduate School*, *General Purpose*.
8. Click **Duplicate** on *Formal / Academic*. It appears in your own list as
   "Formal / Academic (copy)".
9. Pick the copy from the existing-templates dropdown. The body loads into the editor. Change a
   sentence — e.g. add a line to the closing paragraph.
10. Tick **Make this my default template** and save. Say: *"the default is what's pre-selected
    for every new letter."*

### Act 3 — Generate a letter (3 min) — the centrepiece

11. Back to the dashboard (`/teacher`). Find the **pending** request from Bini Chand and click
    through to generate.
12. On the letter form, show the **template picker** — it lists your own templates *and* the
    system ones, with your default pre-selected. Pick the copy you just edited.
13. Tick a few of the quality checkboxes and add an anecdote.
14. Submit — you get a **live preview** of the rendered letter with the student's real data
    filled in.
15. **Edit the text directly in the preview** — click into it and change a word. Say: *"this is
    editable, and the edit is what gets exported."*
16. Download as **PDF**. Then go back and try **DOCX** to show both.

### Act 4 — Tracking (1 min) — the payoff

17. Return to the dashboard. The student has moved into **"Students You Have Recommended"**,
    and the row now shows a **real timestamp**, the **template name** you used, and a working
    **Re-download** link.
18. **Contrast:** Aman Shakya's older records show `—` in those columns. Say: *"those were
    generated before we added tracking; anything generated now records what was used and stores
    the file."*
19. Click **Re-download** — it serves back the exact file that was downloaded.

### Act 5 — Security, if you have time or get asked (2 min)

20. Open devtools → Application → Cookies. Show there is **no `unique` or `username` cookie**
    carrying your identity — only a `sessionid`.
21. Say: *"identity used to come from a cookie you could edit by hand. Setting `unique` to
    another professor's ID let you read their students' transcripts and generate letters in
    their name. Forging the `username` cookie let you reset any professor's password outright.
    All of that now resolves from the Django session."*
22. If pushed for evidence: `python manage.py test home` — 345 tests, and the security ones are
    mutation-tested (break the fix, a test fails).

---

## Part 4 — Things that will NOT work — avoid these on stage

**Email is not configured.** `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` are deliberately empty
because the old credentials were committed to git and are compromised.

- **Do not demo forgot-password / OTP** — the OTP is generated and stored, but the email never
  arrives, so you cannot complete the flow.
- The "notify professor of a new request" email won't send either. Nothing crashes — the failure
  is logged, not raised — but no mail arrives.
- If you *want* mail for the demo, put a Gmail **app password** into `.env` first and restart.

**Do not demo professor self-registration.** A self-registered professor is created **inactive**
and cannot log in until a superuser approves them in `/admin/` (tick `is_active` on the user).
That's the intended security behaviour, but it looks like a bug if you're not expecting it. If
you *do* want to show it, show the approval step too — it's a good story: *"anyone could
previously mint a professor account."*

**Don't type a Devanagari name into a letter and export PDF.** It renders as blank boxes. The
PDF engine can't do Devanagari text shaping. DOCX handles it fine, so use DOCX if it comes up.

**If a form silently does nothing**, it's almost certainly a missing CSRF token — CSRF
protection was turned back on. Everything shipped has been checked, but if you add a form
tonight, it needs `{% csrf_token %}` inside it.

---

## Part 5 — What you've shipped (for the "what did you build" question)

### Phase 1 — Data model and intake
Extended the application model and the student request form: personal details, programs applied
for, **repeatable universities** (name + country + deadline), relationship with the professor,
academics, strong/weak points, file uploads. Duplicate pending requests to the same professor
are prevented.

### Phase 2 — Filtering, search and tracking
- Professor dashboard **search** across name, roll number and email, multi-word AND matching.
- **Filters** by Department / Country / College, as typeable comboboxes suggesting only your own
  values, combining with search, applied to both lists.
- Groundwork for **letter tracking**: when generated, which template, and a stored copy.

### Phase 3 — Template library
- **Three system templates** ship with the app, shared by every professor.
- **Duplicate to my templates** → edit → save → mark as default.
- **Template selection at generation time**, threaded end-to-end from the picker through the
  preview to the export.
- Generation now **records** `generated_at`, the template used, and stores the file — which is
  what makes the Phase 2 dashboard show real data instead of dashes.
- Letters render through a **sandboxed** template engine; a broken template is refused rather
  than producing an empty file.
- Unicode PDF export (accented Latin, Greek, Cyrillic, em dashes, curly quotes).

### Phase 4 — Hardening
- **Identity comes from the Django session**, never a client-set cookie. Closed: professor
  impersonation, professor account takeover via password reset (two separate routes), and
  unauthenticated rename endpoints.
- **Password-reset OTP moved server-side** into the session — it used to live in a cookie the
  attacker controlled on both sides.
- **Student identity is a signed cookie**; tampering is detected.
- **Admin dashboard requires a superuser**; self-registered professors need approval.
- **CSRF protection re-enabled** across all 30 forms.
- **Secrets, DEBUG and allowed hosts read from the environment**; the app refuses to start with
  development defaults when `DEBUG=false`.
- Removed `/edit` — a routed, unauthenticated, database-writing endpoint.
- **345 automated tests**, up from a stub file at the start.

### If asked "what's left?"
Point at `docs/FOLLOW-UPS.md`. The honest headline: the student-side intake views still accept
an identity from POST data, so a student could submit under another student's name — same bug
class we fixed for professors, in the one area that phase didn't cover. It's documented and
first on the list.

---

## Part 6 — Emergency fixes

| Symptom | Fix |
|---|---|
| `no such column: TeacherInfo.user_id` | `python manage.py migrate` |
| `ImproperlyConfigured: DJANGO_SECRET_KEY...` | `.env` is missing or `DJANGO_DEBUG` is `false`. Recreate `.env` (Part 1 step 3) |
| Can't log in as a professor | You're typing a username — the field wants the **email** |
| Login rejected with correct password | The account may be inactive. `/admin/` → Users → tick `is_active` |
| A form does nothing when submitted | Missing `{% csrf_token %}` in that form |
| `DisallowedHost` | Add the hostname to `DJANGO_ALLOWED_HOSTS` in `.env` and restart |
| Port already in use | `python manage.py runserver 8001` |

**Full reset to a known-good state** (destroys local data — only if desperate):
```bash
git checkout -- db.sqlite3 && python manage.py migrate
```
