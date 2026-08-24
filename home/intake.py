"""Testable helpers for the student intake flow (FR-2).

The large studentform views call these instead of duplicating logic.
"""


def compose_full_name(first, middle, last):
    """Join first/middle/last into a single display name, skipping blanks."""
    parts = [p.strip() for p in (first, middle, last) if p and p.strip()]
    return " ".join(parts)


def has_pending_application(student, professor):
    """True if a not-yet-generated application already links this pair.

    Implements the diagram's 'Check Duplicate Submission'. A generated
    letter (is_generated=True) does not block a fresh request.
    """
    from home.models import Application
    return Application.objects.filter(
        std=student, professor=professor, is_generated=False,
    ).exists()


def parse_universities(names, countries, deadlines, programs):
    """Turn the form's parallel lists into cleaned university row dicts.

    Rows whose university name is blank are dropped. A blank deadline
    becomes None so it is a valid value for University.uni_deadline
    (a nullable DateField). Ragged lists are tolerated via index guards.
    """
    def at(seq, i):
        return seq[i] if i < len(seq) else ""

    rows = []
    for i, raw_name in enumerate(names):
        name = (raw_name or "").strip()
        if not name:
            continue
        deadline = (at(deadlines, i) or "").strip()
        rows.append({
            "uni_name": name,
            "country": (at(countries, i) or "").strip(),
            "uni_deadline": deadline or None,
            "program_applied": (at(programs, i) or "").strip(),
        })
    return rows


def academics_present(gpa, final_percentage):
    """True if at least one of GPA / final percentage was supplied.

    The student (and the professor on the edit page) must give one or the
    other; requiring both is unnecessary. Whitespace-only counts as blank.
    """
    return bool((gpa or "").strip() or (final_percentage or "").strip())


def normalize_bs_year(value):
    """Normalize a Bikram Sambat year to a canonical 4-digit string.

    Students enter the same year many ways — ``2080``, ``080``, ``80`` — so
    the stored value drifts. Collapse them all to the 4-digit form (``2080``)
    so Enrollment Batch and Passed Year read consistently everywhere.

    Returns the 4-digit string, or ``None`` when the input is blank or cannot
    be read as a plausible BS year (kept in the 2000–2099 range).
    """
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) <= 2:
        digits = "20" + digits.zfill(2)
    elif len(digits) == 3:
        digits = "2" + digits
    elif len(digits) > 4:
        return None
    if not (2000 <= int(digits) <= 2099):
        return None
    return digits


def save_universities(application, rows):
    """Replace all University rows for an application with the given rows.

    Mirrors the existing create-or-replace pattern used elsewhere in the
    intake views. Returns the number of rows created.
    """
    from home.models import University
    University.objects.filter(application=application).delete()
    created = 0
    for row in rows:
        University.objects.create(
            uni_name=row["uni_name"],
            country=row.get("country", ""),
            uni_deadline=row.get("uni_deadline"),
            program_applied=row.get("program_applied", ""),
            application=application,
        )
        created += 1
    return created


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
        # name/email keep their old value when the field is blank (identity must
        # not be erased); every other scalar takes the posted value verbatim, so
        # clearing a field on the edit form clears it on the record.
        application.name = post.get("name") or application.name
        application.email = post.get("email") or application.email
        application.years_taught = post.get("yrs")
        # Only overwrite subjects when the edit form actually rendered the
        # subject picker (``subjects_editable``). A professor with no subjects on
        # their own profile submits none, which must NOT wipe the student's list.
        if post.get("subjects_editable"):
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
        # HTML type="number" is only a client-side guard; a direct/malformed
        # POST could send non-digits, which would 500 at save. Coerce safely.
        class_size = (post.get("class_size") or "").strip()
        application.class_size = int(class_size) if class_size.isdigit() else None
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
