"""
Формы для работы с событиями жизни.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from genealogy.models import EventTypeEnum, LifeEvent, Person, Relationship, RelationshipTypeEnum


class LifeEventForm(forms.ModelForm):
    """Форма создания/редактирования события жизни."""

    # Новое поле для выбора брака (только для развода)
    marriage_relationship = forms.ModelChoiceField(
        queryset=Relationship.objects.none(),
        required=False,
        label="Завершить брак",
        help_text="Выберите брак, который завершается этим разводом",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            }
        ),
    )

    class Meta:
        model = LifeEvent
        fields = [
            "event_type",
            "event_date",
            "end_date",
            "is_date_approx",
            "location",
            "description",
            "related_person",
            "marriage_relationship",
        ]
        widgets = {
            "event_type": forms.Select(
                attrs={
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                    "id": "id_event_type",
                }
            ),
            "event_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                },
                format="%Y-%m-%d",
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500",
                },
                format="%Y-%m-%d",
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
                    "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tom-select"
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

        # === УМНЫЙ РАЗВОД: заполняем queryset активных браков ===
        if self.person:
            # Находим все активные браки (без даты окончания)
            active_marriages = Relationship.objects.filter(
                Q(from_person=self.person) | Q(to_person=self.person),
                relationship_type=RelationshipTypeEnum.SPOUSE,
                end_date__isnull=True,
            ).select_related("from_person", "to_person")

            # Устанавливаем queryset для корректной валидации
            self.fields["marriage_relationship"].queryset = active_marriages

            # Кастомизируем отображение меток в выпадающем списке
            def label_from_instance(rel):
                spouse = rel.to_person if rel.from_person == self.person else rel.from_person
                start_date_str = rel.start_date.strftime("%d.%m.%Y") if rel.start_date else "дата неизвестна"
                return f"Брак с {spouse.full_name_display} (с {start_date_str})"

            self.fields["marriage_relationship"].label_from_instance = label_from_instance

            # Если редактируем существующее событие развода, пытаемся найти связанный брак
            if self.instance.pk and self.instance.event_type == EventTypeEnum.DIVORCE and self.instance.related_person:
                related_marriage = Relationship.objects.filter(
                    Q(from_person=self.person, to_person=self.instance.related_person)
                    | Q(from_person=self.instance.related_person, to_person=self.person),
                    relationship_type=RelationshipTypeEnum.SPOUSE,
                ).first()
                if related_marriage:
                    self.fields["marriage_relationship"].initial = related_marriage.pk
        else:
            # Если персоны нет — queryset пустой
            self.fields["marriage_relationship"].queryset = Relationship.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        event_type = cleaned_data.get("event_type")
        event_date = cleaned_data.get("event_date")
        end_date = cleaned_data.get("end_date")
        related_person = cleaned_data.get("related_person")
        marriage_relationship = cleaned_data.get("marriage_relationship")

        if event_date and end_date and end_date < event_date:
            raise ValidationError({"end_date": "Дата окончания не может быть раньше даты начала."})

        if related_person and self.person and related_person.tree != self.person.tree:
            raise ValidationError({"related_person": "Связанная персона должна быть из того же дерева."})

        if related_person and self.person and related_person == self.person:
            raise ValidationError({"related_person": "Нельзя связать персону саму с собой."})

        # Для развода требуем выбора брака
        if event_type == EventTypeEnum.DIVORCE and not marriage_relationship:
            raise ValidationError({"marriage_relationship": "Для развода необходимо выбрать завершаемый брак."})

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

            # Если это развод и выбран брак — обновляем связь
            marriage_rel = self.cleaned_data.get("marriage_relationship")
            if event.event_type == EventTypeEnum.DIVORCE and marriage_rel:
                # Устанавливаем дату окончания брака
                marriage_rel.end_date = event.event_date
                marriage_rel.is_current = False
                marriage_rel.save()

                # Автоматически заполняем related_person из брака, если не указан
                if not event.related_person:
                    spouse = (
                        marriage_rel.to_person if marriage_rel.from_person == event.person else marriage_rel.from_person
                    )
                    event.related_person = spouse
                    event.save(update_fields=["related_person"])

            # Создаём зеркальное событие для связанной персоны
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
