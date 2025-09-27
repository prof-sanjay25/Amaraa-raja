# admin_panel/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def replace(value, args):
    """
    Replace all occurrences of the first argument with the second in the given string.
    Usage: {{ value|replace:"_, " " }}
    Example: "Engine_Details"|replace:"_, " " → "Engine Details"
    """
    try:
        old, new = args.split(',')
        return value.replace(old.strip(), new.strip())
    except Exception:
        return value

@register.filter
def titlecase(value):
    """
    Convert a string into Title Case.
    Example: "engine details" → "Engine Details"
    """
    if isinstance(value, str):
        return value.replace("_", " ").title()
    return value
