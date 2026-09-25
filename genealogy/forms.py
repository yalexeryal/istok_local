"""
Django Forms для приложения genealogy.
"""

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CollaboratorRoleEnum,
    EventTypeEnum,
    ExportFormatEnum,
    ExportTypeEnum,
    GenderEnum,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
)


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


class PersonForm(forms.ModelForm):
    """Форма создания/редактирования персоны с полями отца/матери."""

    # Дополнительные поля для родителей (не в модели)
    father = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Отец",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )
    mother = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Мать",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )

    class Meta:
        model = Person
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "maiden_name",
            "gender",
            "birth_date",
            "is_birth_date_approx",
            "death_date",
            "is_death_date_approx",
            "birth_place",
            "death_place",
            "burial_place",
            "culture",
            "photo",
            "notes",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Иван",
                }
            ),
            "middle_name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Иванович",
                }
            ),
            "last_name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Иванов",
                }
            ),
            "maiden_name": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Только для женщин",
                }
            ),
            "gender": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "birth_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                }
            ),
            "death_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                }
            ),
            "birth_place": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Москва, Россия",
                }
            ),
            "death_place": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "burial_place": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "culture": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Русский",
                }
            ),
            "photo": forms.ClearableFileInput(attrs={"class": "w-full px-4 py-2 border border-gray-300 rounded-md"}),
            "notes": forms.Textarea(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "rows": 4,
                    "placeholder": "Дополнительная информация о персоне...",
                }
            ),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user
        self.duplicates_found = []  # Для хранения найденных дублей

        if tree and not self.instance.pk:
            self.instance.tree = tree

        # Ограничиваем выбор родителей только текущим деревом
        if tree:
            self.fields["father"].queryset = Person.objects.filter(tree=tree, gender=GenderEnum.MALE).order_by(
                "last_name", "first_name"
            )
            self.fields["mother"].queryset = Person.objects.filter(tree=tree, gender=GenderEnum.FEMALE).order_by(
                "last_name", "first_name"
            )

        # Если редактируем существующую персону — заполняем поля родителей
        if self.instance.pk:
            parents = self.instance.get_parents()
            for parent in parents:
                # Определяем тип связи
                rel = Relationship.objects.filter(
                    from_person=parent,
                    to_person=self.instance,
                    relationship_type__in=[
                        RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        RelationshipTypeEnum.ADOPTIVE_PARENT,
                        RelationshipTypeEnum.STEP_PARENT,
                    ],
                ).first()
                if rel:
                    if parent.gender == GenderEnum.MALE:
                        self.fields["father"].initial = parent.pk
                    elif parent.gender == GenderEnum.FEMALE:
                        self.fields["mother"].initial = parent.pk

        self.fields["first_name"].required = True
        self.fields["gender"].required = True
        if self.instance.gender and self.instance.gender != GenderEnum.FEMALE:
            self.fields["maiden_name"].help_text = "Доступно только для женщин"

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get("first_name")
        middle_name = cleaned_data.get("middle_name")
        last_name = cleaned_data.get("last_name")
        gender = cleaned_data.get("gender")
        maiden_name = cleaned_data.get("maiden_name")
        birth_date = cleaned_data.get("birth_date")
        birth_place = cleaned_data.get("birth_place")
        death_date = cleaned_data.get("death_date")

        if first_name and self.tree:
            # Проверка точного дубликата (ФИО + дерево)
            queryset = Person.objects.filter(first_name=first_name, last_name=last_name or "", tree=self.tree)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError(f'В этом дереве уже есть персона с именем "{first_name} {last_name or ""}".')

            # Нечеткая проверка дубликатов (для предупреждения)
            self.duplicates_found = self._find_duplicates(first_name, middle_name, last_name, birth_date, birth_place)

        if birth_date and death_date and death_date < birth_date:
            raise ValidationError({"death_date": "Дата смерти не может быть раньше даты рождения."})

        if maiden_name and gender != GenderEnum.FEMALE:
            raise ValidationError({"maiden_name": "Девичья фамилия указывается только для женщин."})

        return cleaned_data

    def _find_duplicates(self, first_name, middle_name, last_name, birth_date, birth_place):
        """
        Нечеткий поиск дубликатов по ФИО + дата рождения + место рождения.
        Возвращает список найденных персон.
        """
        if not self.tree or not first_name:
            return []

        candidates = Person.objects.filter(tree=self.tree).exclude(pk=self.instance.pk if self.instance.pk else None)

        duplicates = []
        for person in candidates:
            score = 0

            # Сравнение имени (нечеткое)
            if person.first_name:
                if person.first_name.lower() == first_name.lower():
                    score += 3
                elif person.first_name[0].lower() == first_name[0].lower():
                    score += 1  # Первая буква совпадает

            # Сравнение фамилии
            if person.last_name and last_name:
                if person.last_name.lower() == last_name.lower():
                    score += 3
                elif person.last_name[0].lower() == last_name[0].lower():
                    score += 1

            # Сравнение отчества
            if person.middle_name and middle_name:
                if person.middle_name.lower() == middle_name.lower():
                    score += 2
                elif person.middle_name[0].lower() == middle_name[0].lower():
                    score += 1

            # Сравнение даты рождения
            if person.birth_date and birth_date:
                if person.birth_date == birth_date:
                    score += 3
                elif person.birth_date.year == birth_date.year:
                    score += 1

            # Сравнение места рождения
            if person.birth_place and birth_place:
                if person.birth_place.lower() == birth_place.lower():
                    score += 2
                elif any(word.lower() in person.birth_place.lower() for word in birth_place.split() if len(word) > 3):
                    score += 1

            # Если score >= 6 — считаем возможным дублем
            if score >= 6:
                duplicates.append(person)

        return duplicates

    def save(self, commit=True):
        person = super().save(commit=False)
        if self.user:
            person.updated_by = self.user
        if person.pk:
            person.sync_version += 1
        if commit:
            person.save()
            # Обновляем связи с родителями
            self._update_parent_relationships(person)
        return person

    def _update_parent_relationships(self, person):
        """Обновляет связи с родителями после сохранения персоны."""
        father = self.cleaned_data.get("father")
        mother = self.cleaned_data.get("mother")

        # Удаляем старые связи родитель-ребенок
        Relationship.objects.filter(
            to_person=person,
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ],
        ).delete()

        # Создаем новые связи
        if father:
            Relationship.objects.get_or_create(
                from_person=father,
                to_person=person,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={"created_by": self.user},
            )

        if mother:
            Relationship.objects.get_or_create(
                from_person=mother,
                to_person=person,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
                defaults={"created_by": self.user},
            )


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
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "to_person": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
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
            self.fields["from_person"].queryset = Person.objects.filter(tree=tree)
            self.fields["to_person"].queryset = Person.objects.filter(tree=tree)
        self.fields["from_person"].required = True
        self.fields["to_person"].required = True
        self.fields["relationship_type"].required = True

    def clean(self):
        cleaned_data = super().clean()
        from_person = cleaned_data.get("from_person")
        to_person = cleaned_data.get("to_person")
        relationship_type = cleaned_data.get("relationship_type")

        if from_person and to_person:
            if from_person.tree != to_person.tree:
                raise ValidationError("Обе персоны должны принадлежать одному дереву.")
            if from_person == to_person:
                raise ValidationError("Нельзя создать связь персоны с самой собой.")
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


class LifeEventForm(forms.ModelForm):
    """Форма создания/редактирования события жизни."""

    class Meta:
        model = LifeEvent
        fields = ["event_type", "event_date", "end_date", "is_date_approx", "location", "description", "related_person"]
        widgets = {
            "event_type": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
            "event_date": forms.DateInput(
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
            "is_date_approx": forms.CheckboxInput(
                attrs={"class": "w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"}
            ),
            "location": forms.TextInput(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "placeholder": "Москва, Россия",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "rows": 3,
                    "placeholder": "Описание события...",
                }
            ),
            "related_person": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                }
            ),
        }

    def __init__(self, *args, person=None, tree=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.person = person
        self.tree = tree or (person.tree if person else None)
        self.user = user

        if self.tree:
            exclude_pk = person.pk if person else None
            self.fields["related_person"].queryset = (
                Person.objects.filter(tree=self.tree).exclude(pk=exclude_pk).order_by("last_name", "first_name")
            )
        else:
            self.fields["related_person"].queryset = Person.objects.none()

        self.fields["related_person"].required = False
        self.fields["event_type"].required = True

    def clean(self):
        cleaned_data = super().clean()
        event_date = cleaned_data.get("event_date")
        end_date = cleaned_data.get("end_date")
        related_person = cleaned_data.get("related_person")

        if event_date and end_date and end_date < event_date:
            raise ValidationError({"end_date": "Дата окончания не может быть раньше даты начала."})

        if related_person and self.person and related_person.tree != self.person.tree:
            raise ValidationError({"related_person": "Связанная персона должна быть из того же дерева."})

        if related_person and self.person and related_person == self.person:
            raise ValidationError({"related_person": "Нельзя связать персону саму с собой."})

        return cleaned_data

    def save(self, commit=True):
        event = super().save(commit=False)
        if self.person and not event.pk:
            event.person = self.person
        if self.user:
            event.created_by = self.user
        if event.pk:
            event.sync_version += 1

        if commit:
            event.save()
            # Автоматическое создание зеркального события для брака/развода
            if event.event_type in [EventTypeEnum.MARRIAGE, EventTypeEnum.DIVORCE] and event.related_person:
                reverse_exists = LifeEvent.objects.filter(
                    person=event.related_person,
                    event_type=event.event_type,
                    event_date=event.event_date,
                    related_person=event.person,
                ).exists()

                if not reverse_exists:
                    LifeEvent.objects.create(
                        person=event.related_person,
                        event_type=event.event_type,
                        event_date=event.event_date,
                        end_date=event.end_date,
                        is_date_approx=event.is_date_approx,
                        location=event.location,
                        description=event.description,
                        related_person=event.person,
                        created_by=event.created_by,
                    )
        return event


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
            from django.db.models import Q

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
