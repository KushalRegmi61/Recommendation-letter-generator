"""Who is acting on this request.

Identity used to come from client-controlled cookies (``unique`` for a professor,
``student`` for a student), which any visitor could set to impersonate anyone.
Professors have a real Django session, so they resolve from ``request.user``.
"""

from django.core import signing


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


# Namespaces the signature so a student cookie cannot be replayed elsewhere.
STUDENT_COOKIE_SALT = "home.student-identity"
STUDENT_COOKIE_NAME = "student"


def _student_signer():
    """The signer for the student cookie.

    Deliberately not ``HttpResponse.set_signed_cookie`` /
    ``HttpRequest.get_signed_cookie``: those derive the salt as ``key + salt``,
    so signing and verifying here would have to repeat that detail in two
    places. One signer keeps the setter and the reader symmetric by
    construction.
    """
    return signing.get_cookie_signer(salt=STUDENT_COOKIE_SALT)


def current_student(request):
    """The ``StudentLoginInfo`` acting on this request, or ``None``.

    The cookie is signed with ``SECRET_KEY``, so a tampered or hand-written
    value fails verification instead of impersonating another student.

    This is weaker than a session: students are not Django users, so there is
    no server-side record to revoke. A leaked cookie stays valid until
    ``SECRET_KEY`` rotates.
    """
    from home.models import StudentLoginInfo

    raw = request.COOKIES.get(STUDENT_COOKIE_NAME)
    if not raw:
        return None
    try:
        username = _student_signer().unsign(raw)
    except signing.BadSignature:
        return None
    return StudentLoginInfo.objects.filter(username=username).first()


def set_student_cookie(response, student):
    """Sign the student's identity into ``response``."""
    response.set_cookie(
        STUDENT_COOKIE_NAME,
        _student_signer().sign(str(student.username)),
        httponly=True,
        samesite="Lax",
    )
    return response
