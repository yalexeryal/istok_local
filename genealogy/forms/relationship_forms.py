"""
Формы для работы с родственными связями.
"""

from django import forms
from django.core.exceptions import ValidationError

from genealogy.models import Person, Relationship


class RelationshipForm(forms.ModelForm):
    """Форма создания родственной связи между двумя персонами."""

    class Meta:
        model = Relationship
        fields = [
            "from_person",
            "to_person",
            "relationship_type",
            "start_date",
            "end_date",
            "is_current",
            "description",
        ]
        widgets = {
            "from_person": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tom-select"
                }
            ),
            "to_person": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tom-select"
                }
            ),
            "relationship_type": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                }
            ),
            "is_current": forms.CheckboxInput(
                attrs={"class": "w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"}
            ),
            "description": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Дополнительная информация о связи",
                }
            ),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user
        if tree:
            self.fields["from_person"].queryset = Person.objects.filter(tree=tree).order_by("last_name", "first_name")
            self.fields["to_person"].queryset = Person.objects.filter(tree=tree).order_by("last_name", "first_name")
        self.fields["from_person"].required = True
        self.fields["to_person"].required = True
        self.fields["relationship_type"].required = True

    def clean(self):
        cleaned_data = super().clean()
        from_person = cleaned_data.get("from_person")
        to_person = cleaned_data.get("to_person")
        relationship_type = cleaned_data.get("relationship_type")

        if from_person and to_person:
            # 1. Проверка на одно дерево
            if from_person.tree_id != to_person.tree_id:
                raise ValidationError("Обе персоны должны принадлежать одному и тому же дереву.")

            # 2. Проверка на связь с самим собой
            if from_person.pk == to_person.pk:
                raise ValidationError("Нельзя создать связь персоны с самой собой.")

            # 3. Проверка на дубликаты связей
            if relationship_type:
                queryset = Relationship.objects.filter(
                    from_person=from_person, to_person=to_person, relationship_type=relationship_type
                )
                if self.instance.pk:
                    queryset = queryset.exclude(pk=self.instance.pk)
                if queryset.exists():
                    raise ValidationError(
                        f'Такая связь уже существует между "{from_person.full_name_display}" и "{to_person.full_name_display}".'
                    )

            # 4. 🔥 НОВОЕ: Проверка на циклы (вызываем логику модели для консистентности)
            # Создаем временный экземпляр для проверки, чтобы не сохранять его
            temp_rel = Relationship(from_person=from_person, to_person=to_person, relationship_type=relationship_type)
            try:
                temp_rel.clean()  # Это вызовет проверку циклов, которую мы добавили в модель
            except ValidationError as e:
                # Перехватываем ошибку о цикле и передаем её в форму
                raise ValidationError(e.message) from None

        return cleaned_data

    def save(self, commit=True):
        relationship = super().save(commit=False)
        if self.user:
            relationship.created_by = self.user
        if relationship.pk:
            relationship.sync_version += 1
        if commit:
            relationship.save()
        return relationship
