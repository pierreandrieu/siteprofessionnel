# sitepro/templatetags/importmap_tags.py
import json
from django import template
from sitepro.importmap import _build_scope

register = template.Library()


@register.simple_tag
def importmap_json():
    scope = _build_scope("plandeclasse/js")
    data = {
        "imports": {},
        "scopes": {"/static/plandeclasse/js/": scope},
    }
    # sortie compacte, idéale à inliner
    return json.dumps(data, separators=(",", ":"))
