"""
Формы для работы с событиями жизни.
"""

from django import forms
from django.core.exceptions import ValidationError

from genealogy.models import EventTypeEnum, LifeEvent, Person


class LifeEventForm(forms.ModelForm):
    """Форма создания/редактирования события жизни."""

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
        ]
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
