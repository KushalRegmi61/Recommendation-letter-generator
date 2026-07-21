"""Template helpers for letter-related pages."""
from django import template

register = template.Library()


@register.filter
def safe_external_url(value):
    """Return ``value`` only when it is an http(s) URL, else ``''``.

    Student-supplied link fields (``linkedIn``, ``paper_link``) are rendered
    into ``href`` attributes. Django autoescaping stops attribute breakout but
    NOT dangerous schemes, so ``javascript:``/``data:`` payloads would execute
    in the professor's session on click. Callers linkify only when this returns
    a non-empty string and otherwise render the raw value as inert text.
    """
    if value and str(value).strip().lower().startswith(("http://", "https://")):
        return value
    return ""
