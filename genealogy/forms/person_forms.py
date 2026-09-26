"""
Формы для работы с персонами.
"""

from django import forms
from django.core.exceptions import ValidationError

from genealogy.models import GenderEnum, Person, Relationship, RelationshipTypeEnum


class PersonForm(forms.ModelForm):
    """Форма создания/редактирования персоны с полями отца/матери."""

    father = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Отец",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tom-select"
            }
        ),
    )
    mother = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        required=False,
        label="Мать",
        widget=forms.Select(
            attrs={
                "class": "w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tom-select"
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
        self.duplicates_found = []
        self.exact_duplicate = None

        if tree and not self.instance.pk:
            self.instance.tree = tree

        if tree:
            self.fields["father"].queryset = Person.objects.filter(tree=tree, gender=GenderEnum.MALE).order_by(
                "last_name", "first_name"
            )
            self.fields["mother"].queryset = Person.objects.filter(tree=tree, gender=GenderEnum.FEMALE).order_by(
                "last_name", "first_name"
            )

        if self.instance.pk:
            parents = self.instance.get_parents()
            for parent in parents:
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
            queryset = Person.objects.filter(first_name=first_name, last_name=last_name or "", tree=self.tree)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            exact_dup = queryset.first()
            if exact_dup:
                self.exact_duplicate = exact_dup

            self.duplicates_found = self._find_duplicates(first_name, middle_name, last_name, birth_date, birth_place)

        if birth_date and death_date and death_date < birth_date:
            raise ValidationError({"death_date": "Дата смерти не может быть раньше даты рождения."})

        if maiden_name and gender != GenderEnum.FEMALE:
            raise ValidationError({"maiden_name": "Девичья фамилия указывается только для женщин."})

        return cleaned_data

    def _find_duplicates(self, first_name, middle_name, last_name, birth_date, birth_place):
        if not self.tree or not first_name:
            return []

        candidates = Person.objects.filter(tree=self.tree).exclude(pk=self.instance.pk if self.instance.pk else None)
        duplicates = []

        for person in candidates:
            score = 0
            if person.first_name:
                if person.first_name.lower() == first_name.lower():
                    score += 3
                elif person.first_name[0].lower() == first_name[0].lower():
                    score += 1

            if person.last_name and last_name:
                if person.last_name.lower() == last_name.lower():
                    score += 3
                elif person.last_name[0].lower() == last_name[0].lower():
                    score += 1

            if person.middle_name and middle_name:
                if person.middle_name.lower() == middle_name.lower():
                    score += 2
                elif person.middle_name[0].lower() == middle_name[0].lower():
                    score += 1

            if person.birth_date and birth_date:
                if person.birth_date == birth_date:
                    score += 4
                elif person.birth_date.year == birth_date.year:
                    score += 1
                else:
                    score -= 5
            elif not person.birth_date and not birth_date:
                score += 1

            if person.birth_place and birth_place:
                if person.birth_place.lower() == birth_place.lower():
                    score += 2
                elif any(word.lower() in person.birth_place.lower() for word in birth_place.split() if len(word) > 3):
                    score += 1

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
            self._update_parent_relationships(person)
        return person

    def _update_parent_relationships(self, person):
        father = self.cleaned_data.get("father")
        mother = self.cleaned_data.get("mother")

        Relationship.objects.filter(
            to_person=person,
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ],
        ).delete()

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
