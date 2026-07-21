# Phase B — Full Student Details on the Letter-Generation Page

**Date:** 2026-07-21
**Status:** Design — awaiting review
**Scope:** Phase B. Independent of the deferred Phases C (chip editor) and D (upload draft).

## Problem

When a professor generates a recommendation letter (`/makeLetter` → `formTeacher.html`), they see
only a **subset** of what the student submitted. The student's application (`Application` plus the
`Paper`, `Project`, `University`, `Qualities`, `Academics`, `Files` satellites) carries far more than
the page shows. Fields the professor currently cannot see include:

- **Academic:** `class_size`, `ranking_percentile`, `academics.final_percentage`,
  `language_instruction`, `enrollment_batch`, `passed_year`
- **Relationship:** `years_known`, `known_roles`, `professional_experience`
- **Internship:** `intern` flag, `intern_company`, `intern_role`, `intern_duration`, `intern_outcome`
- **Awards:** `scholarships`, `competitions_won`
- **Qualities:** `leadership`, `hardworking`, `social`, `teamwork`, `friendly`, `presentation`,
  `recommend`, `recommendation_strength`
- **Statements:** `personal_statement` and `recommendation_purpose` are shown, but `strong_points`
  and `weak_points` are not
- **Other:** `contact_number`, `applied_level`, `university.country`, `project.deployed`, all
  universities/papers/projects beyond the first

There is also a **latent 500**: `make_letter` (`home/views.py:480-490`) fetches satellites with
`.get()`. A student who skipped a section (no `Paper`/`Project`/`University`/`Academics` row) raises
`DoesNotExist`; a student with two universities raises `MultipleObjectsReturned`. Existing tests pass
only because their fixtures create exactly one of every satellite.

## Goals

- The professor sees **all** of the student's submitted details on the generation page, in an
  always-visible, read-only, well-organized panel at the top — polished UX consistent with the new
  dashboard.
- `make_letter` never 500s on an incomplete or multi-entry application.
- The professor's existing editable "generate" form (quality checkboxes, presentation, recommend,
  anecdote, template picker → `/renderCustom`) keeps working unchanged.

## Non-goals

- No change to letter generation itself (`renderCustom`, `render_letter`, `build_letter_context`).
- No template-preview-with-sample-data feature (that was an earlier Phase B idea; deferred).
- No database schema change.
- Phases C and D remain out of scope.

## Design

### 1. Backend — `make_letter` (`home/views.py:468`)

Make the satellite lookups resilient and expose the multi-row collections for display:

- Replace each `Model.objects.get(application=appli)` with `.filter(application=appli).first()` for
  `Paper`, `Project`, `University`, `Qualities`, `Academics`, `Files`. `Qualities` is a
  `OneToOneField` so `.first()` is exact; the others may legitimately have 0 or many rows.
- Additionally pass the full collections for the panel:
  `universities = University.objects.filter(application=appli)`,
  `papers = Paper.objects.filter(application=appli)`,
  `projects = Project.objects.filter(application=appli)`.
- Keep passing the existing single `paper`/`project`/`university`/`quality`/`academics`/`files`
  and the `student` (the `Application`, which already exposes every scalar field) so nothing that
  the professor's form or the file modals rely on breaks.
- `StudentLoginInfo.objects.get(roll_number=roll)` and the `Application` lookup stay as-is
  (identity already scoped to `professor__unique_id=teacher_id`).

### 2. Template — `formTeacher.html`

Replace the ad-hoc `<span class="details">` list at the top (lines 4-137, **excluding** the photo
and the transcript/CV modal blocks, which are kept) with a **read-only "Student's submitted
application" panel**: a titled section containing labelled cards, one per group:

- **Student** — full name (first/middle/last or `student.name`), email, contact number, applied level
- **Academic** — GPA, tentative ranking, final percentage, class size, ranking percentile,
  enrollment batch, passed year, language of instruction
- **Relationship with you** — years known/taught, relationship type, known roles, subjects taught,
  professional experience
- **Universities applied** — loop `universities`: name, country, program applied, deadline
- **Research / Papers** — loop `papers`: title (linked to `paper_link`)
- **Projects** — loop `projects`: supervised project, final/other projects, deployed (yes/no)
- **Internship** — company, role, duration, outcome (shown when `student.intern` or any field set)
- **Awards & scholarships** — scholarships, competitions won
- **Personal qualities (self-reported)** — the five booleans as badges when true, plus presentation,
  recommend, recommendation strength, extracurricular
- **Statements** — personal statement, recommendation purpose, strong points, weak points
- **Documents** — keep the existing photo, and the transcript/CV "Show" buttons/modals verbatim,
  plus a LinkedIn link

Presentation rules:
- Empty values render as an em dash "—"; whole cards may be omitted only if the group has no data,
  but never crash on a missing satellite (guard with `{% if %}`).
- Keep every file dereference guarded (`{% if files.Photo %}`, `{% if files.transcript %}`,
  `{% if files.CV %}`) — the template already does this and the test fixtures rely on it.
- Use the same card/"surface" visual system introduced on the dashboard for consistency.

Keep the professor's editable form (lines 142-324) intact and working — same field names
(`presentation`, `qual`, `recommend`, `prof_anecdote`, `quality1..5`, `template_id`, `roll`), same
`action="/renderCustom"`, same `{% csrf_token %}`. Wrap it in a titled "Generate the letter" card so
the page reads as two clear sections (review details → generate).

### 3. Fix the duplicate modal id

The transcript and CV modals both use `id="exampleModal1"` (lines 64 & 107). Duplicate ids are
invalid and make the CV button open the transcript modal. Give the CV modal a distinct id
(`exampleModalCV`) and point its trigger at it. (Small correctness fix within the page we're editing.)

## Edge cases

- Student with **no** `Paper`/`Project`/`University`/`Academics`/`Files` row → page renders (200),
  those cards show "—" or are omitted, no 500.
- Student with **multiple** universities/papers/projects → all are listed.
- All-blank optional fields → "—", no empty-attribute or `.url`-on-missing-file crash.

## Testing (`home/tests.py`; `login_as_teacher` / force-login pattern as in `MakeLetterTemplateListTests`)

- `make_letter` returns **200** for an application with **no** satellite rows at all (regression for
  the `.get()` 500).
- The details panel renders a representative set of the newly-exposed fields when present — e.g.
  create an application with `intern_company`, `scholarships`, `leadership=True`, a second
  `University`, and assert those values/labels appear in the response.
- Existing `MakeLetterTemplateListTests` still pass (template picker offers system templates and
  posts `name="template_id"`).
- The two file-modal ids are distinct (`assertContains` both `exampleModal1` and `exampleModalCV`).

## Rollout

Self-contained and shippable on its own branch, following the same subagent-driven flow as Phase A.
