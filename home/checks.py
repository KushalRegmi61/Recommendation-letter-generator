"""Deploy-time checks for things Django itself will not notice.

These run with every management command, so ``manage.py migrate`` at container
start surfaces them in the deployment log rather than leaving the problem to be
discovered as a broken page.
"""
import os

from django.conf import settings
from django.core.checks import Warning, register


@register()
def media_root_is_usable(app_configs, **kwargs):
    """MEDIA_ROOT must exist and be writable wherever the app actually runs.

    Uploads and generated letters are written straight to the filesystem, and
    ``/media/`` is served back out of that same directory. In a container the
    directory comes from the image, so a build that drops it turns every photo,
    CV and transcript into a 404 while the database rows still look perfectly
    fine -- which is exactly the failure this app shipped with once already.

    Only reported with DEBUG off: in development MEDIA_ROOT is the working copy
    and is not interesting.
    """
    if settings.DEBUG:
        return []

    root = settings.MEDIA_ROOT
    if not root:
        return [Warning(
            "MEDIA_ROOT is empty, so uploads have nowhere to live.",
            hint="Set MEDIA_ROOT to a directory the process can write to.",
            id="home.W001",
        )]

    if not os.path.isdir(root):
        return [Warning(
            f"MEDIA_ROOT ({root}) does not exist, so every uploaded photo, CV, "
            f"transcript and generated letter will 404.",
            hint="The container image must ship this directory (or mount one "
                 "onto it). Check that .dockerignore does not exclude media/.",
            id="home.W002",
        )]

    if not os.access(root, os.W_OK):
        return [Warning(
            f"MEDIA_ROOT ({root}) is not writable, so uploads and generated "
            f"letters will fail at save time.",
            hint="Grant the running user write access to the directory.",
            id="home.W003",
        )]

    return []
