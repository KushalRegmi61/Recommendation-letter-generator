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
    country = (params.get("country") or "").strip()
    college = (params.get("college") or "").strip()

    # ``icontains`` rather than exact: the dashboard renders these as typeable
    # <datalist> comboboxes, so a professor may type a partial value ("United",
    # "Kath") instead of picking one. Exact matching would silently return
    # nothing and read as a broken filter.
    if department:
        queryset = queryset.filter(std__department__dept_name__icontains=department)
    if country:
        queryset = queryset.filter(university__country__icontains=country)
    if college:
        queryset = queryset.filter(university__uni_name__icontains=college)

    if country or college:
        # ``university`` is a to-many join: without distinct() an application
        # with two matching universities would appear twice.
        queryset = queryset.distinct()
    return queryset


def _distinct_values(queryset, field):
    """Sorted, de-duplicated, non-empty values of ``field`` in ``queryset``."""
    values = queryset.values_list(field, flat=True).distinct()
    return sorted({v for v in values if v not in (None, "")})


def filter_options(queryset):
    """Dropdown choices derived from the applications in ``queryset``.

    Scoping the options to the professor's own applications keeps other
    professors' students out of the filter bar and avoids offering
    combinations that can only ever return nothing.
    """
    return {
        "departments": _distinct_values(queryset, "std__department__dept_name"),
        "countries": _distinct_values(queryset, "university__country"),
        "colleges": _distinct_values(queryset, "university__uni_name"),
    }
