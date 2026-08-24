# Phase C — Guided Template Editor (Design)

**Backlog item:** #4 — "Make Template Editing Easier for Professors" (`LOR_Request_Form_Backlog.md`).

**Goal:** Let a professor edit a recommendation-letter template by inserting friendly-named
fields from a menu instead of hand-typing Jinja variable names, with the template validated
on save and previewable before use — all on the existing Django stack, no framework change and
no front-end build step.

## Direction (decided)

- **Guided *source* editor**, not a WYSIWYG chip editor. Braces stay visible but colour-coded.
  This is the `docs/mockups/guided-source-editor-mockup.html` approach — its own note: "cannot
  silently corrupt a template, and it ships fast." The `chip-editor-mockup.html` (hidden-brace
  WYSIWYG) is rejected because a contentEditable→Jinja round-trip can corrupt logic, and doing it
  safely would need a bundled library (TipTap/CKEditor) and a build step this repo avoids.
- **Editor widget:** CodeMirror **5** (UMD build via CDN, e.g. cdnjs), using its built-in
  `jinja2` mode for brace colouring and bracket matching. CodeMirror 5 is chosen over 6 solely
  to keep **zero build step** (CM6 needs a prebuilt ESM bundle). It replaces the current TinyMCE
  editor on this page — TinyMCE is an HTML rich-text editor and is a mismatch for editing a Jinja
  *source* template (it wraps content in `<p>`, escapes/mangles `{% %}`).
- **No `{{`-autocomplete in v1.** The toolbar dropdown fully satisfies backlog #4; autocomplete is
  a possible fast-follow.

## Non-goals (v1)

- No autocomplete-on-type.
- No loops/`{% for %}` or `{% else %}` helper — the "insert optional section" helper emits only a
  balanced `{% if field %}…{% endif %}`. (Loops still work if typed; they're just not a helper.)
- No storage-model change. Templates remain a Jinja string in `CustomTemplates.template`. The
  fully-structured "JSON blocks compiled to Jinja" idea is noted as a future direction only.
- No change to the letter-generation / edit flow (`renderCustom`, `make_letter`) or to
  duplicate/delete/set-default actions.

## Existing surface (integration points)

- Model `CustomTemplates(template_name, template: TextField, professor FK, is_default, is_system)`.
- Views: `template` (renders the editor page, GET `makeTemplate`), `getTemplate` (the **save** handler, POST `getTemplate`), `renderCustom`
  (generate-page render), `duplicate_template`, `delete_template`, `set_default_template`.
- Rendering: `home/letters.py` — `SandboxedEnvironment().from_string(tpl).render(ctx)`;
  `build_letter_context(application)` returns the render context. Its top-level keys are the
  allowed variable set: `student`, `app`, `subjects`, `subject`, `value`, `subjects_sentence`,
  `firstname`, `paper`, `project`, `university`, `quality`, `academics`, `files`, `teacher`,
  `pronoun`, `pronoun_obj`, `pronoun_pos`, `rel_desc`, `strength_phrase`, `deadline`, `today`.
- Editor page: `templates/customTemplate.html` (currently TinyMCE on `textarea#editor name="content"`).
- Identity: `current_teacher(request)`; own-templates-only via
  `get_object_or_404(CustomTemplates, ..., professor=teacher)`. POSTs are CSRF-protected.

## Components

### 1. Field registry — `home/letters.py`

Single source of truth for the friendly-name↔expression mapping:

```python
# (label, expr, group). `expr` is inserted verbatim inside {{ }}.
FIELDS = [
    ("Student name",        "app.name",                    "Student"),
    ("First name",          "firstname",                   "Student"),
    ("Program",             "app.std.program.program_name","Student"),
    ("Relationship",        "rel_desc",                    "Student"),
    ("GPA",                 "academics.gpa",               "Academics & Quality"),
    ("Subjects (sentence)", "subjects_sentence",           "Academics & Quality"),
    ("Recommendation strength", "strength_phrase",         "Academics & Quality"),
    ("Teacher name",        "teacher.name",                "Teacher"),
    ("Teacher email",       "teacher.email",               "Teacher"),
    ("Teacher title",       "teacher.title",               "Teacher"),
    ("Pronoun he/she",      "pronoun",                     "Pronouns & Dates"),
    ("Pronoun him/her",     "pronoun_obj",                 "Pronouns & Dates"),
    ("Pronoun his/her",     "pronoun_pos",                 "Pronouns & Dates"),
    ("Today's date",        "today",                       "Pronouns & Dates"),
    ("Deadline",            "deadline",                    "Pronouns & Dates"),
]
```

The exact rows are finalised in the plan; the invariant is: **every row's top-level name (the part
before the first `.` or `|`) must be a key returned by `build_letter_context`.** A test enforces this so
the palette can never offer a variable that doesn't exist. A helper `grouped_fields()` returns the
rows grouped by `group` (ordered) for the template to render the dropdown.

### 2. Validation — `home/letters.py`

```python
def validate_template(source: str) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Non-empty errors must block the save."""
```

- Compile `SandboxedEnvironment().parse(source)` / `from_string(source)`; a `TemplateSyntaxError`
  (unbalanced or invalid tag) → one **error** carrying the message. Errors block the save.
- `jinja2.meta.find_undeclared_variables(ast)` minus the allowed top-level set (build_letter_context keys)
  → each remaining name is a **warning** ("Unknown field: `nmae` — it will render empty"). Warnings
  do **not** block the save (Jinja renders unknown vars as empty by default).

### 3. Sample context — `home/letters.py`

```python
def sample_context() -> dict:
    """A dummy render context mirroring build_letter_context's shape for previews."""
```

Built from `types.SimpleNamespace` (and small stand-ins) so attribute access used in templates
resolves — `app.name`, `app.std.program.program_name`, `academics.gpa`, `teacher.name`, etc. — with
realistic placeholder values (e.g. "Asmita Sharma", GPA "3.82"). Shares the same key set as
`build_letter_context`. Never touches the database and never exposes a real student.

### 4. Preview view — `home/views.py` + `home/urls.py`

New `preview_template` (POST `previewTemplate`):

- Inputs: `content` (unsaved editor text), `mode` (`"sample"` | `"application"`),
  optional `application_id`.
- `current_teacher` required; otherwise redirect to login.
- `validate_template(content)`; on error, return the error text (no render).
- `mode == "sample"`: render `content` against `sample_context()`.
- `mode == "application"`: load the application via
  `get_object_or_404(Application, pk=application_id, professor=teacher)` (own-only), build its
  context with the existing `build_letter_context`, render. A malformed/foreign id is a 404, never
  another professor's data.
- Returns the rendered letter HTML (shown in a modal on the page). `renderCustom` is untouched.

### 5. Save flow — `home/views.py` (`template`)

On save (`getTemplate`), call `validate_template(content)` before writing. Also drop the TinyMCE HTML-artifact cleanup (`<p>&nbsp;</p>` → `<br>` replacements) — CodeMirror edits plain text, so those replacements are inert at best and corrupt literal markup at worst:

- Any **error** → re-render `customTemplate.html` with the error message and the submitted content
  preserved; **no database write**.
- No errors → save as today; re-render with any **warnings** surfaced (non-blocking banner).
- Unchanged: POST+CSRF, `current_teacher`, own-templates-only, `is_default`/`is_system` handling.

### 6. Editor page — `templates/customTemplate.html`

- Remove the TinyMCE script/init; initialise CodeMirror 5 (`mode: "jinja2"`,
  `matchBrackets: true`, `lineNumbers: true`) on `#editor`, syncing to the `content` textarea on
  submit and on preview.
- Toolbar buttons:
  - **Insert field ▾** — a dropdown built server-side from `grouped_fields()`; clicking a field
    inserts `{{ expr }}` at the cursor via `cm.replaceSelection`.
  - **Insert optional section** — choose a field, then insert
    `{% if <expr> %}` + selected text + `{% endif %}` (balanced, around any current selection).
  - **Preview letter** — POST content (+ mode/application_id) to `previewTemplate`; show result in
    a modal. A "Preview with" selector chooses Sample (default) or one of the professor's own
    applications.
  - **Save template** — normal form submit.
- **Warnings/errors banner** area for the values returned by the save flow.

## Data flow

1. **GET** editor page → Django injects `grouped_fields()` → renders Insert-field dropdown and the
   CodeMirror-backed textarea seeded with the template body.
2. **Insert field / optional section** → client-side text insertion at the cursor (no request).
3. **Preview** → POST `content` (+ `mode`, `application_id`) → `previewTemplate` validates + renders
   sample or own-application context → HTML shown in modal.
4. **Save** → POST `makeTemplate` → `validate_template` → errors block (re-render with message),
   otherwise write + re-render with any warnings.

## Testing

- `validate_template` (SimpleTestCase, no DB): unbalanced `{% if %}` → one error; unknown var
  `{{ app.nmae }}` → one warning, no error; clean template → `([], [])`.
- `FIELDS` integrity: every row's top-level name ∈ `build_letter_context` key set (guards drift).
- `sample_context()`: renders the shipped default/system template without raising.
- `preview_template` view: `mode=sample` → 200 with rendered marker; `mode=application` for a
  foreign/unknown id → 404; logged-out → redirected/blocked, nothing rendered.
- `template` save: unbalanced content → not written + error surfaced; unknown-var content → written
  + warning surfaced; a template that isn't the professor's own cannot be overwritten.
- Existing `CsrfProtectionTests` template scan still passes (the editor form keeps `{% csrf_token %}`).

## Files

- `home/letters.py` — add `FIELDS`, `grouped_fields()`, `validate_template()`, `sample_context()`.
- `home/views.py` — add validation to `getTemplate` (the save handler); DRY the editor-page context (shared helper used by `template` + `getTemplate` re-renders) to also pass `grouped_fields()` and the professor's own applications; add `preview_template`.
- `home/urls.py` — add `path('previewTemplate', views.preview_template, name='previewTemplate')`.
- `templates/customTemplate.html` — TinyMCE → CodeMirror 5, toolbar (Insert field / Insert optional
  section / Preview with sample|application), warnings/errors banner.
- `home/tests.py` — the tests above.

## Risks / notes

- **CodeMirror 5 CDN availability.** Load from a pinned cdnjs URL (matches the repo's existing
  CDN pattern for Bootstrap/jQuery/TinyMCE). If offline use matters later, the assets can be
  vendored under `static/`; out of scope for v1.
- **`find_undeclared_variables` granularity** is top-level only (`app`, not `app.nmae`), so a typo
  in a *nested* attribute (`{{ app.nmae }}`) is not caught as unknown — it renders empty. This is
  acceptable for a warn-only policy; the preview is the professor's real check.
- **`docs/mockups/` is gitignored** (local-only research); do not `git add` it. Do not `git add`
  `db.sqlite3` or `CLAUDE.md`.
