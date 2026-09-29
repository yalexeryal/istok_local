"""
Custom template tags and filters для приложения genealogy.
"""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Template filter для доступа к элементу словаря по ключу.

    Использование: {{ my_dict|get_item:key }}
    """
    return dictionary.get(key)
