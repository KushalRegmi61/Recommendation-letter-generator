from django.apps import AppConfig


class HomeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'home'

    def ready(self):
        # Registers the deploy-time checks; importing for the side effect is
        # the documented way to hook django.core.checks up to an app.
        from . import checks  # noqa: F401
