"""Who is acting on this request.

Identity used to come from client-controlled cookies (``unique`` for a professor,
``student`` for a student), which any visitor could set to impersonate anyone.
Professors have a real Django session, so they resolve from ``request.user``.
"""


def current_teacher(request):
    """The ``TeacherInfo`` acting on this request, or ``None``.

    Resolution order:
    1. the ``TeacherInfo.user`` one-to-one link (authoritative), then
    2. the legacy ``"Full Name/<unique_id>"`` convention, for rows the data
       migration could not match to an account.

    The ``unique`` cookie is never consulted.
    """
    from home.models import TeacherInfo

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return None

    teacher = TeacherInfo.objects.filter(user=user).first()
    if teacher:
        return teacher

    # Legacy fallback: the login account encodes the id in its name.
    full_name = (user.get_full_name() or user.first_name or "").strip()
    if "/" not in full_name:
        return None
    unique_id = full_name.rsplit("/", 1)[-1].strip()
    if not unique_id:
        return None
    return TeacherInfo.objects.filter(unique_id=unique_id).first()
