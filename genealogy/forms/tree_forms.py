"""
Формы для работы с деревьями.
"""

from django import forms

from genealogy.models import Tree


class TreeCreateForm(forms.ModelForm):
    """Форма создания нового дерева."""

    class Meta:
        model = Tree
        fields = ["name", "description", "is_public"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Например: Семья Ивановых",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "rows": 3,
                    "placeholder": "Краткое описание дерева",
                }
            ),
            "is_public": forms.CheckboxInput(
                attrs={"class": "w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"}
            ),
        }
