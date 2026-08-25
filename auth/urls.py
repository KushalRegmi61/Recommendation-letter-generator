from django.contrib import admin
from django.urls import path ,include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.views.static import serve as _serve_static


def serve_media(request, path):
    """Serve an uploaded file out of MEDIA_ROOT.

    MEDIA_ROOT is read per request rather than baked into the URL pattern at
    import time, so the route follows the setting rather than a stale copy of
    it. django.views.static.serve resolves ``path`` against the root and
    rejects anything climbing outside it.
    """
    return _serve_static(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),
    # Uploaded media (student photos, CVs, transcripts, generated letters).
    # Deliberately outside the DEBUG block below: static() returns nothing when
    # DEBUG is off, so with that alone every upload 404s in production, which is
    # where the app actually runs. Files are written to MEDIA_ROOT, which the
    # deployment mounts a persistent volume onto so they survive a redeploy.
    # This handler is single-threaded and not built for high traffic; it is
    # sized for this app, not for a CDN's job.
    re_path(r'^media/(?P<path>.*)$', serve_media, name='serve_media'),
]
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)