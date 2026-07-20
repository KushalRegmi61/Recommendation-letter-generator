# Phase 4c: Deployment Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the app safe to run outside a laptop — secrets out of the repository, `DEBUG` off by default, CSRF protection back on, and the cookie/transport security settings Django expects in production.

**Architecture:** `auth/settings.py` reads every environment-specific value from the environment with a development-friendly default, via a tiny `env()` helper (no new dependency). CSRF middleware is re-enabled — the survey found only 3 live forms missing a token and no JavaScript POSTs at all, so this is far cheaper than it looks. Security settings that would break local HTTP development are gated on `DEBUG`.

**Tech Stack:** Django 5.1, Python 3.12, `os.environ` (deliberately no `django-environ` — one helper is enough and adds no dependency to a UTF-16 `requirements.txt`).

---

## What is wrong today (from the survey of `auth/settings.py`)

| line | setting | value |
|---|---|---|
| 24 | `SECRET_KEY` | a hardcoded `django-insecure-...` literal, committed (value redacted here — it is in git history and must be rotated) |
| 27 | `DEBUG` | `True` |
| 30 | `ALLOWED_HOSTS` | `['*', 'recommendation-generator.bct.itclub.pp.ua']` |
| 64 | `CsrfViewMiddleware` | **commented out** |
| 172-173 | `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | live Gmail address and app password, committed |
| 177 | `X_FRAME_OPTIONS` | `'ALLOWALL'` |
| — | `SECURE_*`, `SESSION_COOKIE_*`, `CSRF_COOKIE_*` | **none present** |

`DEBUG=True` with `ALLOWED_HOSTS=['*']` means any unhandled exception returns a full traceback
including settings — which is how several bugs in earlier phases were found to leak the
`SECRET_KEY` and the mail password to an unauthenticated caller.

**The committed credentials must be treated as compromised.** This plan moves them out of the
file; it cannot un-publish them. Rotating them is a manual step for the repository owner and is
called out in Task 6.

---

## Environment notes for every task

- `python` is NOT on PATH. Use `venv/bin/python`.
- Run only the test classes your task touches. Full suite once, at the end.
- No AI attribution in commit messages. Never `git add CLAUDE.md`, `db.sqlite3`, or `.env`.
- **Never commit a real secret.** `.env` is gitignored in Task 1; `.env.example` carries
  placeholders only.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `auth/settings.py` | Read config from the environment | 1–4 |
| `.env.example` (**new**) | Documented placeholders, committed | 1 |
| `.env` (**new, gitignored**) | Real local values, never committed | 1 |
| `.gitignore` | Ignore `.env` | 1 |
| `templates/studentDetails.html`, `userDetails.html` | Missing CSRF tokens | 3 |
| `home/views.py` | Drop `@csrf_exempt` from `download_letter` | 3 |
| `home/tests.py` | Settings and CSRF tests | 1–4 |
| `README.md` | Deployment section | 6 |

---

## Task 1: Read configuration from the environment

**Files:**
- Modify: `auth/settings.py:24-34`
- Create: `.env.example`, `.env`
- Modify: `.gitignore`
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

Append to `home/tests.py`:

```python
class SettingsHygieneTests(TestCase):
    """Deployment-critical settings must not be hardcoded."""

    def test_no_insecure_secret_key_literal_in_settings(self):
        from pathlib import Path
        from django.conf import settings as dj
        source = (Path(dj.BASE_DIR) / "auth" / "settings.py").read_text()
        self.assertNotIn("django-insecure-", source)

    def test_no_email_password_literal_in_settings(self):
        from pathlib import Path
        from django.conf import settings as dj
        source = (Path(dj.BASE_DIR) / "auth" / "settings.py").read_text()
        # The committed app password, which must no longer appear in the file.
        self.assertNotIn("nxdrmhpnsahduvax", source)

    def test_allowed_hosts_is_not_a_wildcard_when_debug_is_off(self):
        from pathlib import Path
        from django.conf import settings as dj
        source = (Path(dj.BASE_DIR) / "auth" / "settings.py").read_text()
        # A bare '*' must not be hardcoded; it may only arrive from the environment.
        self.assertNotIn("ALLOWED_HOSTS = ['*'", source)

    def test_an_env_example_file_documents_every_key(self):
        from pathlib import Path
        from django.conf import settings as dj
        example = (Path(dj.BASE_DIR) / ".env.example")
        self.assertTrue(example.exists())
        text = example.read_text()
        for key in (
            "DJANGO_SECRET_KEY", "DJANGO_DEBUG", "DJANGO_ALLOWED_HOSTS",
            "EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD",
        ):
            with self.subTest(key=key):
                self.assertIn(key, text)

    def test_the_real_env_file_is_gitignored(self):
        from pathlib import Path
        from django.conf import settings as dj
        ignored = (Path(dj.BASE_DIR) / ".gitignore").read_text()
        self.assertIn(".env", ignored)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.SettingsHygieneTests -v2`
Expected: FAIL on all five.

- [ ] **Step 3: Add the `env` helper and convert the settings**

Near the top of `auth/settings.py`, after the existing `import os` / `from pathlib import Path`:

```python
def env(name, default=None):
    """Read a setting from the environment, falling back to a dev-safe default."""
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# Load a local .env if present. Deliberately hand-rolled: adding python-dotenv
# would mean editing requirements.txt, which is UTF-16 encoded and fragile.
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _value = _line.partition("=")
        os.environ.setdefault(_key.strip(), _value.strip())
```

Then replace lines 24-34:

```python
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    # Development-only fallback. Production MUST set DJANGO_SECRET_KEY.
    "dev-only-insecure-key-do-not-use-in-production",
)

DEBUG = env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost:8000,http://127.0.0.1:8000",
)
```

And lines 172-173:

```python
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
```

**Note the `DEBUG` default is `True`, not `False`.** That is deliberate: this is a student
project run mostly from `manage.py runserver`, and defaulting to `False` would make a fresh
clone serve no static files and return opaque 500s. Production sets `DJANGO_DEBUG=false`
explicitly, and Task 5 adds a check that refuses to start with an insecure key when `DEBUG` is
off. **If you disagree with this default, say so rather than silently changing it.**

- [ ] **Step 4: Create `.env.example` (committed, placeholders only)**

```
# Copy to .env and fill in. .env is gitignored and must never be committed.

# Generate with:
#   python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
DJANGO_SECRET_KEY=replace-me

# "true" for local development, "false" in production.
DJANGO_DEBUG=true

# Comma-separated. Must list every hostname the app is served on.
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# Comma-separated, scheme included.
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

# Gmail account and app password used for OTP and notification mail.
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

- [ ] **Step 5: Create a local `.env` and gitignore it**

Add to `.gitignore`, under the `CLAUDE.md` block at the top:
```
# Local environment configuration - never commit
.env
```

Then create `.env` with a freshly generated key and the existing values, so local development
keeps working:

```bash
venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print('DJANGO_SECRET_KEY=' + get_random_secret_key())" > .env
cat >> .env <<'EOF'
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,recommendation-generator.bct.itclub.pp.ua
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://recommendation-generator.bct.itclub.pp.ua
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EOF
git check-ignore -v .env
```

`git check-ignore` must confirm `.env` is ignored. **Leave `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`
empty** — the committed credentials are compromised and should not be carried forward. Mail will
fail silently in development, which is the correct outcome; `send_mail` calls in this codebase
already pass `fail_silently=True` in places, but verify that and report where they do not.

**Rotating `SECRET_KEY` invalidates all existing sessions and signed student cookies. Say so in
your report** — anyone logged in will be logged out on next deploy.

- [ ] **Step 6: Run tests**

Run: `venv/bin/python manage.py test home.tests.SettingsHygieneTests -v2`
Expected: `OK` (5 tests).

Then confirm the app still starts:
```bash
venv/bin/python manage.py check
```
Expected: `System check identified no issues`.

- [ ] **Step 7: Commit**

```bash
git add auth/settings.py .env.example .gitignore home/tests.py
git commit -m "chore(config): read secrets and host configuration from the environment"
```

Verify `.env` is **not** in the commit: `git show --stat HEAD | grep -c "^ .env$"` must print `0`.

---

## Task 2: Security settings gated on `DEBUG`

**Files:**
- Modify: `auth/settings.py` (append a security block; fix `X_FRAME_OPTIONS` at :177)
- Test: `home/tests.py`

- [ ] **Step 1: Write the failing test**

```python
class SecuritySettingsTests(TestCase):
    """Production-grade cookie and transport settings are configured."""

    def test_clickjacking_protection_is_not_disabled(self):
        from django.conf import settings as dj
        self.assertNotEqual(dj.X_FRAME_OPTIONS, "ALLOWALL")
        self.assertIn(dj.X_FRAME_OPTIONS, ("DENY", "SAMEORIGIN"))

    def test_session_cookies_are_httponly(self):
        from django.conf import settings as dj
        self.assertTrue(dj.SESSION_COOKIE_HTTPONLY)

    def test_content_type_sniffing_is_disabled(self):
        from django.conf import settings as dj
        self.assertTrue(dj.SECURE_CONTENT_TYPE_NOSNIFF)

    def test_samesite_is_set_on_session_and_csrf_cookies(self):
        from django.conf import settings as dj
        self.assertEqual(dj.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertEqual(dj.CSRF_COOKIE_SAMESITE, "Lax")

    def test_secure_cookies_follow_debug(self):
        # In DEBUG (local HTTP) secure cookies must be off or nothing works;
        # with DEBUG off they must be on.
        from django.conf import settings as dj
        self.assertEqual(dj.SESSION_COOKIE_SECURE, not dj.DEBUG)
        self.assertEqual(dj.CSRF_COOKIE_SECURE, not dj.DEBUG)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.SecuritySettingsTests -v2`
Expected: FAIL — `X_FRAME_OPTIONS` is `'ALLOWALL'` and the rest are undefined
(`AttributeError`).

- [ ] **Step 3: Replace `X_FRAME_OPTIONS` and append the block**

Change line 177 from `X_FRAME_OPTIONS = 'ALLOWALL'` to:

```python
X_FRAME_OPTIONS = "SAMEORIGIN"
```

**Check first whether anything relies on framing this app** — grep the templates for `<iframe`.
TinyMCE uses an iframe for its own editor body, which is same-origin and unaffected, but confirm
rather than assume, and report what you find.

Append at the end of `auth/settings.py`:

```python
# --- Security -------------------------------------------------------------
# Settings that would break plain-HTTP local development are tied to DEBUG.

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

if not DEBUG:
    # Behind a TLS-terminating proxy, tell Django how to detect HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(env("DJANGO_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
```

`SECURE_HSTS_SECONDS` defaults to one hour rather than a year deliberately — a long HSTS
max-age is hard to undo if the deployment turns out not to have working TLS. Raise it once
HTTPS is confirmed stable.

**`CSRF_COOKIE_HTTPONLY` is deliberately not set.** Django's docs advise against it, because
AJAX code needs to read the cookie. This app has no POSTing JavaScript today, but leaving it
off avoids a trap for whoever adds some.

- [ ] **Step 4: Run tests**

Run: `venv/bin/python manage.py test home.tests.SecuritySettingsTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 5: Commit**

```bash
git add auth/settings.py home/tests.py
git commit -m "chore(config): add cookie and transport security settings"
```

---

## Task 3: Turn CSRF protection back on

**Files:**
- Modify: `auth/settings.py:64` (uncomment the middleware)
- Modify: `templates/studentDetails.html:56,94`, `templates/userDetails.html:147`
- Modify: `home/views.py` (`download_letter`'s `@csrf_exempt`)
- Test: `home/tests.py`

The survey found **30 POST forms, 28 of which already carry `{% csrf_token %}`**, and **no
JavaScript POSTs at all** (the only two AJAX calls are GETs). So re-enabling costs three token
insertions.

- [ ] **Step 1: Write the failing test**

```python
class CsrfProtectionTests(TestCase):
    """CSRF middleware is active and every POST form carries a token."""

    def test_the_middleware_is_enabled(self):
        from django.conf import settings as dj
        self.assertIn(
            "django.middleware.csrf.CsrfViewMiddleware", dj.MIDDLEWARE
        )

    def test_every_post_form_template_has_a_token(self):
        import re
        from pathlib import Path
        from django.conf import settings as dj
        offenders = []
        for path in (Path(dj.BASE_DIR) / "templates").rglob("*.html"):
            text = path.read_text(errors="replace")
            for match in re.finditer(r"<form[^>]*method=[\"']post[\"'][^>]*>", text, re.I):
                tail = text[match.end():match.end() + 400]
                if "csrf_token" not in tail:
                    offenders.append(f"{path.name}:{text[:match.start()].count(chr(10)) + 1}")
        self.assertEqual(offenders, [], f"POST forms without a CSRF token: {offenders}")

    def test_a_post_without_a_token_is_rejected(self):
        from django.test import Client
        enforcing = Client(enforce_csrf_checks=True)
        response = enforcing.post("/loginAdmin", {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.CsrfProtectionTests -v2`
Expected: FAIL — the middleware is commented out and three templates lack tokens.

- [ ] **Step 3: Add the three missing tokens**

Insert `{% csrf_token %}` on the line after each of these opening `<form>` tags:
- `templates/studentDetails.html:56` — `action="changeStudentName"`
- `templates/studentDetails.html:94` — `action="studentPasswordChange"`
- `templates/userDetails.html:147` — `<form id="my-form" method="POST">` (no action, JS-driven)

Read each first — match the surrounding indentation.

`templates/test.html` also lacked one, but Phase 4a deleted that file. If it is still present,
**stop and report** — Phase 4a did not complete.

- [ ] **Step 4: Enable the middleware**

In `auth/settings.py`, uncomment line 64 so `MIDDLEWARE` contains:
```python
    'django.middleware.csrf.CsrfViewMiddleware',
```
It must sit after `SessionMiddleware` and before `AuthenticationMiddleware` — verify the
ordering against the existing list rather than assuming.

- [ ] **Step 5: Remove the `@csrf_exempt` from `download_letter`**

`download_letter` carries `@csrf_exempt` even though both its forms
(`templates/test2.html:15,23`) supply tokens. With the middleware back on, the exemption is a
deliberate hole in a state-changing view that also writes files. Remove the decorator.

**Then check whether `csrf_exempt` is still used anywhere.** If not, remove the now-unused
import too.

- [ ] **Step 6: Run the full suite**

Run: `venv/bin/python manage.py test home -v2`

This is a justified mid-plan full-suite run: re-enabling CSRF affects every POST test in the
codebase. Django's test client exempts itself from CSRF checks by default, so most tests should
pass unchanged — but any test using `Client(enforce_csrf_checks=True)` will now behave
differently.

**If tests fail, do not weaken the middleware.** Fix the template or the test. Report every
failure and what you did about it.

- [ ] **Step 7: Manual verification**

```bash
venv/bin/python manage.py runserver
```
Log in as a professor and exercise: save a template, duplicate a starter template, generate and
download a letter, and change a profile field. Each is a POST that must still work. **Report
which of these you actually performed** — if you cannot run a browser, say so plainly rather
than implying you did.

- [ ] **Step 8: Commit**

```bash
git add auth/settings.py templates/ home/views.py home/tests.py
git commit -m "fix(security): re-enable csrf protection"
```

---

## Task 4: Refuse to start insecurely

**Files:**
- Modify: `auth/settings.py`
- Test: `home/tests.py`

A settings file that *can* be configured securely still ships insecurely if someone forgets an
environment variable. Make that impossible to miss.

- [ ] **Step 1: Write the failing test**

```python
class ProductionGuardTests(TestCase):
    """Running with DEBUG off and a default secret must fail loudly."""

    def test_the_guard_function_exists(self):
        from auth.settings import check_production_config
        self.assertTrue(callable(check_production_config))

    def test_it_rejects_the_dev_secret_key_when_debug_is_off(self):
        from auth.settings import check_production_config
        with self.assertRaises(Exception) as ctx:
            check_production_config(
                debug=False,
                secret_key="dev-only-insecure-key-do-not-use-in-production",
                allowed_hosts=["example.com"],
            )
        self.assertIn("DJANGO_SECRET_KEY", str(ctx.exception))

    def test_it_rejects_a_wildcard_host_when_debug_is_off(self):
        from auth.settings import check_production_config
        with self.assertRaises(Exception) as ctx:
            check_production_config(
                debug=False, secret_key="a-real-key", allowed_hosts=["*"],
            )
        self.assertIn("ALLOWED_HOSTS", str(ctx.exception))

    def test_it_permits_a_correct_production_configuration(self):
        from auth.settings import check_production_config
        check_production_config(
            debug=False, secret_key="a-real-key", allowed_hosts=["example.com"],
        )

    def test_it_permits_anything_in_development(self):
        from auth.settings import check_production_config
        check_production_config(
            debug=True,
            secret_key="dev-only-insecure-key-do-not-use-in-production",
            allowed_hosts=["*"],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `venv/bin/python manage.py test home.tests.ProductionGuardTests -v2`
Expected: FAIL — `ImportError: cannot import name 'check_production_config'`.

- [ ] **Step 3: Add the guard**

In `auth/settings.py`, after `ALLOWED_HOSTS` is defined:

```python
DEV_SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"


def check_production_config(debug, secret_key, allowed_hosts):
    """Refuse to run with development defaults once DEBUG is off."""
    if debug:
        return
    if secret_key == DEV_SECRET_KEY or not secret_key:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set to a real value when DJANGO_DEBUG is false. "
            "Generate one with: python -c "
            "\"from django.core.management.utils import get_random_secret_key; "
            "print(get_random_secret_key())\""
        )
    if "*" in allowed_hosts:
        raise ImproperlyConfigured(
            "ALLOWED_HOSTS must not contain '*' when DJANGO_DEBUG is false. "
            "Set DJANGO_ALLOWED_HOSTS to the hostnames you actually serve."
        )


check_production_config(DEBUG, SECRET_KEY, ALLOWED_HOSTS)
```

Use `DEV_SECRET_KEY` as the fallback in the `SECRET_KEY = env(...)` call from Task 1, so the
constant is defined once.

Add near the top of `auth/settings.py`:
```python
from django.core.exceptions import ImproperlyConfigured
```

**Verify this import at module scope does not create a circular import** — `django.core.exceptions`
is dependency-free, so it should be fine, but confirm `manage.py check` still passes rather than
assuming.

- [ ] **Step 4: Verify the guard actually fires**

```bash
DJANGO_DEBUG=false venv/bin/python manage.py check
```
Expected: `ImproperlyConfigured` mentioning `DJANGO_SECRET_KEY`.

```bash
DJANGO_DEBUG=false DJANGO_SECRET_KEY=test-key-not-real DJANGO_ALLOWED_HOSTS=example.com venv/bin/python manage.py check
```
Expected: `System check identified no issues`.

- [ ] **Step 5: Run tests**

Run: `venv/bin/python manage.py test home.tests.ProductionGuardTests -v2`
Expected: `OK` (5 tests).

- [ ] **Step 6: Commit**

```bash
git add auth/settings.py home/tests.py
git commit -m "chore(config): refuse to start with development defaults in production"
```

---

## Task 5: Django's own deployment checklist

**Files:** none necessarily — this is a verification task that may surface fixes.

- [ ] **Step 1: Run the check**

```bash
DJANGO_DEBUG=false DJANGO_SECRET_KEY=test-key-not-real DJANGO_ALLOWED_HOSTS=example.com \
  venv/bin/python manage.py check --deploy
```

- [ ] **Step 2: Report and triage every warning**

Expected remaining warnings and their status:
- `security.W004` (HSTS seconds low) — expected, deliberate; 3600 until TLS is confirmed.
- `security.W008` (SSL redirect) — should be resolved by `SECURE_SSL_REDIRECT` from Task 2.

**Report the full output.** For each warning, say whether it is resolved, deliberately accepted
(with the reason), or genuinely outstanding. Do not silence a warning you have not understood.

- [ ] **Step 3: Fix anything genuinely outstanding**

If a warning identifies a real gap not covered by Tasks 1-4, fix it and add a test to
`SecuritySettingsTests`. If it needs a judgment call, **stop and ask** rather than guessing.

- [ ] **Step 4: Commit (only if you changed something)**

```bash
git add auth/settings.py home/tests.py
git commit -m "chore(config): resolve django deployment check warnings"
```

---

## Task 6: Deployment documentation and full-suite verification

- [ ] **Step 1: Full suite**

```bash
venv/bin/python manage.py test home -v2
venv/bin/python manage.py makemigrations --check --dry-run
```
Expected: `OK` and `No changes detected`.

- [ ] **Step 2: Add a Deployment section to `README.md`**

Insert before the existing "Project layout" section:

```markdown
## Deployment

Configuration comes from the environment. Copy `.env.example` to `.env` for local development;
in production set real environment variables rather than shipping a `.env` file.

| Variable | Required in production | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | **yes** | The app refuses to start with the dev default when `DJANGO_DEBUG=false`. |
| `DJANGO_DEBUG` | **yes** (`false`) | Defaults to `true` so a fresh clone runs. |
| `DJANGO_ALLOWED_HOSTS` | **yes** | Comma-separated. `*` is rejected when `DEBUG` is off. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | yes, if behind a proxy | Comma-separated, scheme included. |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | for OTP and notification mail | A Gmail **app password**, not the account password. |

Before deploying:

```bash
DJANGO_DEBUG=false DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=your.host \
  python manage.py check --deploy
```

> **The credentials previously committed to this repository are compromised and must be rotated.**
> The old `SECRET_KEY` and the Gmail app password are in the git history and cannot be removed by
> deleting them from the current files. Generate a new secret key, revoke the old Gmail app
> password and issue a new one. Note that rotating `SECRET_KEY` invalidates every active session
> and every signed student cookie — all users will be logged out.

> **Still not addressed:** the database is SQLite committed to the repository, which is unsuitable
> for concurrent production use. `dj_database_url` is already imported in `auth/settings.py` with a
> commented-out Postgres block; switching is a separate piece of work.
```

- [ ] **Step 3: Update the test count** in `README.md` from Step 1.

- [ ] **Step 4: Verify no secret is committed**

```bash
git log --all -p -- auth/settings.py | grep -c "nxdrmhpnsahduvax" || true
git show --stat HEAD | grep -c "^ .env$"
git check-ignore -v .env
```
The first will be **non-zero** — the credential is in history and that is exactly why rotation is
required. The second must be `0`. The third must confirm `.env` is ignored.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: document deployment configuration and required rotation"
```

---

## Notes for the reviewer

1. **Is any secret still reachable?** Grep the working tree for the old key and mail password.
   Confirm `.env` is ignored and absent from every commit on the branch. Confirm `.env.example`
   contains only placeholders.
2. **Does the production guard actually fire?** Try `DJANGO_DEBUG=false` with each combination of
   missing/default `SECRET_KEY` and wildcard hosts. Confirm it cannot be bypassed by, say,
   `DJANGO_ALLOWED_HOSTS="*,example.com"`.
3. **CSRF:** confirm the middleware is in the right position, that a POST without a token is
   rejected with `Client(enforce_csrf_checks=True)`, and that no template still lacks a token.
   Check specifically that letter download and template save still work.
4. **Did `DEBUG=False` break anything?** Static files, error pages, and `ALLOWED_HOSTS`
   enforcement all change behaviour. Run the suite with `DJANGO_DEBUG=false` and report.
5. **Is `SESSION_COOKIE_SECURE = not DEBUG` right?** It means a production deployment without
   TLS silently breaks login. Judge whether that is the correct failure mode.
