# LOR Generator — Template Management, In-App Intake, Filtering (FR-1 to FR-4)

**Date:** 2026-07-17
**Status:** Approved design — ready for implementation planning
**Scope:** One spec, phased implementation. All four FRs revolve around the `Application` model, so they are treated as one coupled change set rather than independent subsystems.

## 1. Goals

Implement four functional requirements on the existing Django LOR Generator:

- **FR-1 Template Management** — provide multiple recommendation-letter templates; auto-generate a letter from the selected template + application data.
- **FR-2 "Google Form" Intake** — replace sir's external Google Form with a *native in-app form* that captures **all** the Google Form's fields. No live Google integration (no webhook / Sheets API / CSV). The diagram's pipeline (Validate → Map Form Data → Check Duplicate → Create Pending Application) becomes ordinary Django form handling.
- **FR-3 Professor Template Editing** — professors create, edit, customize, and save templates for reuse.
- **FR-4 Student Filtering** — professors filter incoming applications by **Department**, **Country**, and **College/University**.
- **FR-5 Generated-Letter Tracking** — professors track the letters they have already generated: the same FR-4 filters apply to the *generated* list, each carries a **generation timestamp**, and the professor can **re-download** a previously generated letter (and see which template was used).

## 2. Guiding decisions (approved)

1. **FR-4 data → structured, repeatable universities.** Reuse the existing `University` model (one `Application` → many target universities). Add a `country` field. Freetext "Universities applied along with deadlines" becomes repeatable rows: *University name + Country + Deadline*. Filtering then falls out of existing structured data.
2. **FR-1 templates → system library + per-professor custom.** Seed 3–4 ready-made **system templates** any professor can pick, alongside the existing per-professor `CustomTemplates`. Professor selects the template **at generation time**.
3. **Intake → extend the existing logged-in student flow.** Keep student accounts, professor-by-department selection, `Application` creation, file uploads, and email notifications. Extend `studentform1`/`studentform2` with the missing Google-Form fields. Do **not** build a login-less public form or rebuild the flow.
4. **Build order → Intake → Filter → Templates**, phased (see §8).
5. **Professor targeting gap.** The Google Form never asks *which* professor. The app already solves this (student picks a professor filtered by department); keep that mechanism and wire new fields through it.

## 3. Data model changes (`home/models.py`)

Most Google-Form fields already have a home in existing models. Changes are largely **additive migrations**. Full field mapping:

| Google Form field | Target model.field | Action |
|---|---|---|
| Email | `Application.email` | exists |
| First / Middle / Last Name | `Application.first_name` / `middle_name` / `last_name` | **add** (keep `Application.name` as composed full name) |
| Contact number | `Application.contact_number` | **add** |
| Gender | `StudentLoginInfo.gender` | exists |
| Programs applied (Masters/PhD/Both/Other) | `Application.applied_level` (choices) | **add** |
| Universities applied + deadlines | `University.uni_name` + `uni_deadline` + `program_applied` | exists (make repeatable in form) |
| — country of each university | `University.country` | **add** |
| In what role do I know you? (multi) | `Application.known_roles` (CSV/Text) | **add** (distinct from existing `relationship_type`) |
| How long have I known you (years) | `Application.years_known` | **add** (existing `years_taught` is separate) |
| Which courses have I taught you? | `Application.subjects` | exists |
| BE Enrollment Batch in BS | `Application.enrollment_batch` | **add** |
| Program – pick recent | `StudentLoginInfo.program` (FK) | exists |
| BE Passed Year in BS | `Application.passed_year` | **add** |
| Final Percentage Score | `Academics.final_percentage` | **add** (keep `gpa`) |
| Tentative ranking (Top 5/10/20/30/40/Other) | `Academics.tentative_ranking` | exists |
| Final year project / MSc thesis | `Project.final_project` | exists |
| Other notable research/project | `Project.supervised_project` | exists |
| Published papers | `Paper.paper_title` / `paper_link` | exists |
| Notable extracurriculars & awards | `Qualities.extracirricular` | exists |
| Professional experience | `Application.professional_experience` | **add** |
| Strong Points | `Application.strong_points` | **add** |
| Weak Points | `Application.weak_points` | **add** |
| Transcript (file) | `Files.transcript` | exists |
| Recent CV (file) | `Files.CV` | exists |
| Your photo (file) | `Files.Photo` | exists |

Pending/generated status for the intake pipeline:

- **Decision:** reuse the existing `Application.is_generated` boolean — a freshly submitted application is `is_generated=False` (= "pending"), a produced letter sets `is_generated=True` (= "generated"). Do **not** add a parallel `status` field; the many views that already branch on `is_generated` make a second representation a consistency hazard.

Generated-letter tracking (FR-5) fields on `Application`:

- `generated_at` — `DateTimeField(null=True, blank=True)`, set when a letter is produced. Enables dated, newest-first history.
- `generated_template` — `ForeignKey(CustomTemplates, null=True, blank=True, on_delete=SET_NULL)`, records which template produced the letter.
- `generated_letter` — `FileField(upload_to='generated_letters/', blank=True)`, stores the produced output so re-download returns the exact file (rather than re-rendering, which could drift if data/template changed).

All new fields are `null=True, blank=True` except where the form marks them required (enforce "required" at the **form** layer, not the DB, to avoid breaking existing rows). One migration per logical group; run only `python manage.py test home` for touched areas during development.

## 4. FR-2 — Extended in-app intake

**Flow (maps to the use-case diagram):**

1. Student logs in (existing) and selects a professor (existing, filtered by department).
2. Multi-step form (extend `studentform1` → `studentform2`, or add a step) collects **all** fields in §3, including a **repeatable universities section** (add/remove rows: Name + Country + Deadline) and the three file uploads (Transcript, CV, Photo).
3. **Validate Response** — server-side validation of required fields, file size/type (existing size checks: CV/Transcript ≤ 5 MB, Photo ≤ 3 MB), and at least one university row.
4. **Check Duplicate Submission** — reject/notify if a **pending** `Application` already exists for `(std, professor)`. On duplicate: message the student (diagram's "Notify Student (Duplicate Found)"); do not create a second pending application.
5. **Map Form Data / Create Pending Application** — create/refresh the `Application` (status = pending) and its related `University` (many), `Academics`, `Project`, `Paper`, `Qualities`, `Files` rows (follow the existing create-or-replace pattern in `studentform2`).
6. Email the professor (existing `send_mail`) that a new request awaits.

**Non-goals:** no Google API, no anonymous submissions, no changes to teacher/admin auth.

## 5. FR-4 — Professor dashboard filtering

On the professor view (`Teacher.html` / the `teacher`/`loginTeacher` render path), add a filter bar with three controls over that professor's applications:

- **Department** → `Application.std__department`
- **Country** → `Application.university__country` (reverse FK; use `.distinct()`)
- **College/University** → `Application.university__uni_name`

Implementation: read filter values from `request.GET`, build a `Q`/chained-filter queryset scoped to `professor__unique_id=<current>`, populate dropdown options from the distinct values present in that professor's applications. Filters are combinable (AND). Empty filter = show all. Preserve the existing pending/generated split in the dashboard.

## 5b. FR-5 — Generated-letter tracking

Extend the professor dashboard's existing *generated* list (`Application.filter(professor=..., is_generated=True)`) into a searchable history:

- **Same filters as FR-4** apply to the generated list (Department / Country / College), so a professor can answer "whom have I recommended, for which country/school". Reuse the FR-4 queryset builder against the `is_generated=True` set.
- **Timestamp:** display `generated_at`; default sort newest-first.
- **Re-download:** a link serves the stored `generated_letter` file; show the `generated_template` name alongside. At generation time the letter view must (a) stamp `generated_at`, (b) save the produced file to `generated_letter`, and (c) record `generated_template`.

This is dashboard/view work built directly on the FR-4 machinery plus the three §3 fields; no new intake or model beyond those fields.

## 6. FR-1 / FR-3 — Template library, editing, and selection

**Model:** extend `CustomTemplates` to support **system (shared) templates** in addition to per-professor ones — e.g. make `professor` nullable and add `is_system` (a system template has `professor=NULL, is_system=True`), or a dedicated flag. Keep `is_default` semantics per professor.

**Seed data:** a data migration inserts 3–4 ready-made Jinja templates (e.g. *Formal/Academic*, *Research / Grad-school*, *General*). These render against the same context the current `renderCustom` / `download_letter` builds, extended with the new fields from §3.

**FR-3 editing (mostly exists):** keep `template()` + `getTemplate()` + `customTemplate.html`. A professor can start from a system template ("duplicate to my templates"), edit, and save as their own custom template. Saving/naming/default-marking already works.

**FR-1 generation:** at letter-generation time the professor **selects** which template (system or custom) to use; the system fills it with the application's data and produces PDF/DOCX via the existing `fpdf` / `python-docx` path. "Generate multiple versions" = generate against more than one selected template. Preview before export uses the existing render path.

## 7. Non-goals / out of scope

- Live Google Forms/Sheets integration of any kind.
- Reworking the three hand-rolled auth systems or the cookie-based session model.
- Public/anonymous request submission.
- Rewriting the large `views.py` beyond the functions these FRs touch.
- Rotating the committed secrets (tracked separately; not part of these FRs).

## 8. Implementation phases

1. **Phase 1 — Data model + intake (FR-2).** Add fields/migrations (§3), `University.country`, extend the intake form incl. repeatable universities + dedup + pending status. *Foundation for everything else.*
2. **Phase 2 — Filtering + tracking (FR-4, FR-5).** Professor dashboard filter bar over Phase-1 data; apply the same filters to the generated list; show `generated_at` and re-download of the stored letter. (The generation view's stamping of `generated_at` / `generated_template` / `generated_letter` lands with Phase 3 when template selection exists; until then, re-download degrades gracefully for pre-existing rows with no stored file.)
3. **Phase 3 — Templates (FR-1/FR-3).** System-template model change + seed migration + template selection at generation + "duplicate to edit". Consumes the richer §3 data in the render context, and writes the FR-5 tracking fields (`generated_at`, `generated_template`, `generated_letter`) when a letter is produced.

## 9. Testing approach

`home/tests.py` is currently a stub. Add focused Django `TestCase`s, and per project rule run only the relevant test module during development (`python manage.py test home.tests.<Class>`), full suite once at final review.

- **Form/intake:** required-field validation, file-size limits, repeatable-university parsing, duplicate-submission detection, correct creation of `Application` + related rows.
- **Filtering:** querysets return the right applications for each single filter and combinations; dropdowns list only that professor's values.
- **Templates:** system templates seed correctly; render fills all new context fields; "duplicate to my templates" produces an editable per-professor copy; generation selects the chosen template.
- **Tracking (FR-5):** generating a letter stamps `generated_at`, stores `generated_letter`, and records `generated_template`; the generated list is filterable and sorts newest-first; re-download returns the stored file.

## 10. Risks & mitigations

- **CSRF is disabled globally** (commented middleware). New POST forms inherit this; note it, don't rely on CSRF protection, and flag re-enabling as a follow-up.
- **Repeatable university UI** is the main net-new front-end work; keep it minimal (JS add/remove rows posting parallel lists, matching the commented `getlist` pattern already in `studentform2`).
- **`is_generated` reuse** — §3 commits to the existing boolean rather than a new `status` field; verify every dashboard/query that branches on `is_generated` still reads correctly once pending applications flow in.
- **Field-name drift** — several existing fields (`relationship_type`, `years_taught`, `gpa`) are near-duplicates of new ones; the mapping table in §3 is authoritative to prevent collisions.
