"""
Формы для экспорта и импорта данных.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from genealogy.models import (
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ExportTypeEnum,
    Person,
    Tree,
)


class ExportForm(forms.Form):
    """Форма настройки экспорта дерева."""

    export_type = forms.ChoiceField(
        choices=ExportTypeEnum.choices,
        label="Тип экспорта",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )
    export_format = forms.ChoiceField(
        choices=ExportFormatEnum.choices,
        label="Формат файла",
        initial=ExportFormatEnum.JSON_ZIP,
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )
    target_person = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        label="Целевая персона (для экспорта родственников)",
        required=False,
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )

    def __init__(self, *args, tree=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        if tree:
            self.fields["target_person"].queryset = tree.persons.all().order_by("last_name", "first_name")

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("export_type") == ExportTypeEnum.RELATIVE and not cleaned_data.get("target_person"):
            raise ValidationError({"target_person": "Для экспорта родственников необходимо выбрать целевую персону."})
        return cleaned_data


class ImportForm(forms.Form):
    """Форма загрузки файла для импорта."""

    source_file = forms.FileField(
        label="Файл для импорта (.zip)",
        widget=forms.FileInput(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                "accept": ".zip",
            }
        ),
    )
    target_tree = forms.ModelChoiceField(
        queryset=Tree.objects.none(),
        label="Импортировать в существующее дерево (опционально)",
        required=False,
        help_text="Если не выбрано, будет создано новое дерево.",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["target_tree"].queryset = Tree.objects.filter(
                Q(
                    collaborators__user=user,
                    collaborators__role__in=[CollaboratorRoleEnum.OWNER, CollaboratorRoleEnum.EDITOR],
                )
                | Q(is_public=True)
            ).distinct()

    def clean_source_file(self):
        file = self.cleaned_data.get("source_file")
        if file:
            if not file.name.endswith(".zip"):
                raise ValidationError("Поддерживаются только файлы с расширением .zip")
            if file.size > 50 * 1024 * 1024:
                raise ValidationError("Размер файла не должен превышать 50 МБ")
        return file
