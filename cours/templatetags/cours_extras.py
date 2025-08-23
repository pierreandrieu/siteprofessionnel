from __future__ import annotations
from django import template
from cours.docindex import prettify as _prettify  # import ABSOLU

register = template.Library()


@register.filter(name="prettify")
def prettify_filter(value):
    if not isinstance(value, str):
        return value
    return _prettify(value)