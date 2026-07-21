# Phase A — Teacher Dashboard & Template Management Cleanup

**Date:** 2026-07-21
**Status:** Design — awaiting review
**Scope:** Phase A of the larger "teacher template experience" effort. Phases B (Preview),
C (Chip editor), and D (Upload draft) are deliberately out of scope here and get their own specs.

## Problem

Two screens the teacher relies on are functionally present but so poorly surfaced that they
read as broken:

1. **Template editor (`/makeTemplate`, `customTemplate.html`, `views.template` / `getTemplate` /
   `duplicate_template`)**
   - A professor's own templates live only in an easy-to-miss **"Existing Templates" dropdown**.
     Duplicating a starter *works* (it sets a success message and creates a row) but nothing on the
     page visibly changes, so it feels like nothing happened. Evidence: teacher `id=3` has ~20 junk
     `(copy) N` rows from repeated clicks.
   - **Editing is matched by `template_name`** (`views.py:1621`). Renaming a template while editing
     therefore creates a *second* row instead of renaming — silent duplication.
   - There is **no Delete, no Rename, no Set-default** in the UI, so junk copies can never be cleaned
     up and defaults can only be changed by re-saving under the magic name "Default".
   - The insert-field palette in `customTemplate.html` is **stale** — it offers variables
     (`student.name`, `quality.recommend`, `student.is_pro`, …) that are not in the real render
     context, while the seeded templates use `app.name`, `pronoun_pos`, `subjects_sentence`,
     `strength_phrase`, etc. (authoritative context: `home/letters.py:build_letter_context`).

2. **Professor dashboard (`/teacher`, `Teacher.html`, `home/dashboard.py`)**
   - Pending vs. Recommended already exist as two sections and filters already apply to both
     (`dashboard.py:29-31`), but the page is visually cramped and the separation is unclear.
   - The **template management block is inlined at the bottom** of the dashboard
     (`Teacher.html:140-145`), mixing template concerns into the student list.

## Goals (Phase A)

- Make template management **discoverable and complete**: a visible list with Edit, Rename, Delete,
  and Set-default.
- **Fix the rename-duplicates bug** by editing by primary key, not by name.
- Give the dashboard **clean, clearly separated Pending and Recommended sections**, with the
  existing filter/search obviously usable on the Recommended list.
- **Move template management off the dashboard** to a single clean button; remove the inline block.
- **Clean up the ~20 existing junk copies** for teacher `id=3` (one-off).

## Non-goals (Phase A)

- The editor engine stays **TinyMCE** (key `8mp7ivw6…` already in `customTemplate.html:22`,
  domains approved by the user). No chip editor, no code-view swap here — that is Phase C.
- No **Preview letter** (Phase B) and no **file upload** (Phase D).
- No database schema change. `CustomTemplates` already has `template_name`, `professor`,
  `is_default`, `is_system` and the `template_system_xor_owned` check constraint
  (`models.py:248-275`). Delete is plain row deletion; set-default and rename are field updates.

## Design

### 1. Template management — backend

**Ownership + safety rules (apply to every new action):**
- Identity from `current_teacher(request)` only — never `request.COOKIES`.
- A professor may act **only on their own** templates: `CustomTemplates.objects.filter(professor=teacher, pk=...)`. A pk that is not theirs (including any `is_system` row) → `Http404`. System/starter templates are never editable, renamable, or deletable.
- All actions are **POST + `{% csrf_token %}`** (CSRF middleware is enabled; `CsrfProtectionTests` scans templates).

**a. Edit by id, not by name — fix the duplication bug (`getTemplate`, `views.py:1586`).**
- Add a hidden, ownership-validated `template_id` to the edit form.
- If `template_id` is present **and owned**: update *that* row — including `template_name` (real rename) and content. Renaming no longer spawns a second row.
- If `template_id` is absent/blank: create a new row (current behaviour for genuinely new templates).
- Keep the existing "name == 'default' ⇒ make default" legacy behaviour and the TinyMCE `<p><br>`
  cleanup (`views.py:1608-1614`) — TinyMCE stays in Phase A, so the cleanup is still needed.
- Name still required and non-blank. On rename, guard against colliding with another of the
  professor's own templates (surface a message rather than creating a confusing dupe).

**b. `deleteTemplate` — new view + URL (`path('deleteTemplate', ...)`).**
- POST, CSRF, `current_teacher`, own-only → 404 otherwise.
- Deletes the row. If the deleted row was the professor's default, leave them with **no default**
  (no auto-promotion, no crash) — the dashboard already handles "no default yet".
- Redirect back to `/makeTemplate` with a success message naming the deleted template.

**c. `setDefaultTemplate` — new view + URL (`path('setDefaultTemplate', ...)`).**
- POST, CSRF, `current_teacher`, own-only → 404.
- In one transaction: clear `is_default` on the professor's other templates, set it on this one
  (mirrors the existing clear-then-set logic at `views.py:1617-1618`).
- Redirect back with confirmation.

### 2. Template management — UI (`customTemplate.html`)

- Replace the **"Existing Templates" dropdown** with a **visible list** of the professor's own
  templates. Each row shows: name, a `(default)` badge, and inline actions **Edit** (loads it into
  the editor with its hidden `template_id`), **Rename**, **Set as default**, **Delete** (with a
  JS `confirm()` naming the template).
- Keep the **starter/Duplicate** buttons, but after a duplicate the new row is visible in the list
  (server already redirects with a success message; the row now simply shows up). No behaviour is
  hidden behind a collapsed control.
- **Fix the stale insert-field palette**: replace `placeholderItems` in `customTemplate.html` with
  the real variables from `build_letter_context`, grouped (Student, Academics & Quality, Teacher,
  Pronouns, Dates). This is a data-accuracy fix, not an engine change.

### 3. Dashboard (`Teacher.html`, `home/dashboard.py`)

- **No context/query changes required** — `build_teacher_dashboard_context` already returns
  `student_list` (pending), `all_students` / `generated_count` (recommended), `filter_options`,
  and `active_filters`. This is a template/layout change.
- Present **Pending** and **Recommended** as two clearly separated sections (headed cards with
  counts), not one dense column.
- Make the filter/search visibly available for the **Recommended** list (the filter already applies
  to it server-side; the UI just needs to make that obvious, e.g. the filter bar labelled as
  covering both, or a search affordance on the Recommended table).
- **Move "Manage Templates" to a single clean button near the top** linking to `/makeTemplate`.
- **Remove the inline template block** at `Teacher.html:140-145` (the "Current default template /
  Manage Templates" section). The default-template hint, if kept at all, moves to the template page;
  the dashboard is about students.

### 4. One-off data cleanup

- Delete the junk `(copy)` / `(copy) N` rows for teacher `id=3`, keeping the real `Default` and at
  most one clean copy of each starter. Present the exact list of rows to be deleted for confirmation
  **before** running it (reversible via the committed `db.sqlite3` in git history).

## Edge cases

- Deleting the **default** template → no default remains; dashboard shows "No default template yet".
- Deleting the **last** template → empty list state, no crash.
- Acting on a template **not owned** (or a system template) → `Http404`, no mutation.
- **Rename collision** with another own template → message, no silent duplicate.
- Concurrent duplicate spam → still creates rows, but Delete now makes them cleanable.

## Testing (`home/tests.py`, ~342 existing tests; use `login_as_teacher` helper)

- Edit-by-id **renames in place** (no second row created).
- Editing without an id **creates** a new template.
- `deleteTemplate`: deletes own; **404** on another teacher's / a system template; deleting the
  default leaves no default.
- `setDefaultTemplate`: sets this one, clears the previous default; **404** on non-owned.
- New forms include `{% csrf_token %}` (satisfies `CsrfProtectionTests`).
- Dashboard still renders Pending and Recommended and the filter still narrows the Recommended list.

## Rollout

Phase A is self-contained and shippable on its own. Phases B/C/D build on this foundation and each
get a separate spec when we reach them.
