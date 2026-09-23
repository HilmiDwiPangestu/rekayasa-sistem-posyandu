# laporan/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def index(indexable, i):
    """Ambil item dari list berdasarkan index. Contoh: {{ mylist|index:0 }}"""
    try:
        return indexable[i]
    except (IndexError, TypeError):
        return None