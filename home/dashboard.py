"""Render context for the professor dashboard (``Teacher.html``).

Both ``views.teacher`` and the GET branch of ``views.loginTeacher`` render
the same template; this module is the single source of truth for what that
template receives.
"""

from django.core import serializers

from home.filters import FILTER_PARAMS, apply_application_filters, filter_options


def build_teacher_dashboard_context(unique_id, params):
    """Build the ``Teacher.html`` context for the professor ``unique_id``.

    ``params`` is a dict-like of GET filter values (see
    ``home.filters.FILTER_PARAMS``). Filters apply to both the pending and
    the generated list so the two views of the dashboard stay consistent.
    """
    from home.models import Application, TeacherInfo

    teacher_model = TeacherInfo.objects.get(unique_id=unique_id)
    scoped = Application.objects.filter(professor__unique_id=unique_id)

    # Options come from the UNFILTERED set, so selecting one filter never
    # empties the other dropdowns.
    options = filter_options(scoped)

    filtered = apply_application_filters(scoped, params)
    pending = filtered.filter(is_generated=False)
    generated = filtered.filter(is_generated=True).order_by("-generated_at", "-id")

    active_filters = {key: (params.get(key) or "").strip() for key in FILTER_PARAMS}

    return {
        "all_students": generated,
        "student_list": pending,
        "check_value": not pending.exists(),
        "teacher_number": scoped.count(),
        "std_dataharu": serializers.serialize("json", generated),
        "teacher_model": teacher_model,
        "default_template": teacher_model.customtemplates_set.filter(
            is_default=True
        ).first(),
        "filter_options": options,
        "active_filters": active_filters,
        "filters_active": any(active_filters.values()),
        "generated_count": generated.count(),
    }
