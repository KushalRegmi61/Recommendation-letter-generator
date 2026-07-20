"""Queryset filtering for the professor dashboard (FR-4 / FR-5).

Pure ORM logic — no HTTP, no cookies. Callers pass an already-scoped
``Application`` queryset (normally scoped to one professor) plus the raw
GET parameters.
"""

#: GET parameter names the dashboard understands.
FILTER_PARAMS = ("department", "country", "college")


def apply_application_filters(queryset, params):
    """Narrow ``queryset`` by any of department / country / college.

    ``params`` is a dict-like (e.g. ``request.GET``). Missing or blank
    values are ignored, so an empty filter bar shows everything. Filters
    combine with AND.
    """
    department = (params.get("department") or "").strip()
    if department:
        # ``icontains``: the dashboard renders this as a typeable combobox, so
        # partial values must match. See Task 2 for the full rationale.
        queryset = queryset.filter(std__department__dept_name__icontains=department)
    return queryset
