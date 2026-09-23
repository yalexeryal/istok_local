"""
Django Forms для приложения genealogy.

Включает:
- PersonForm — форма создания/редактирования персоны
- RelationshipForm — форма создания родственной связи
"""
from django import forms
from django.core.exceptions import ValidationError

from .models import GenderEnum, Person, Relationship, RelationshipTypeEnum


class PersonForm(forms.ModelForm):
    """
    Форма создания/редактирования персоны.

    Валидация:
    - Уникальность ФИО в рамках дерева
    - Дата смерти не раньше даты рождения
    - Приблизительные даты не могут быть точными
    """

    class Meta:
        model = Person
        fields = [
            'first_name',
            'middle_name',
            'last_name',
            'maiden_name',
            'gender',
            'birth_date',
            'is_birth_date_approx',
            'death_date',
            'is_death_date_approx',
            'birth_place',
            'death_place',
            'burial_place',
            'culture',
            'photo',
            'notes',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иван',
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иванович',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иванов',
            }),
            'maiden_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Только для женщин',
            }),
            'gender': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'birth_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'death_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'birth_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Москва, Россия',
            }),
            'death_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'burial_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'culture': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Русский',
            }),
            'photo': forms.ClearableFileInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'rows': 4,
                'placeholder': 'Дополнительная информация о персоне...',
            }),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        """
        Инициализация формы.

        Args:
            tree: Дерево, к которому принадлежит персона (обязательно для создания)
            user: Текущий пользователь (для заполнения updated_by)
        """
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user

        # Для новой персоны устанавливаем дерево
        if tree and not self.instance.pk:
            self.instance.tree = tree

        # Помечаем обязательные поля
        self.fields['first_name'].required = True
        self.fields['gender'].required = True

        # Девичья фамилия имеет смысл только для женщин
        if self.instance.gender and self.instance.gender != GenderEnum.FEMALE:
            self.fields['maiden_name'].help_text = 'Доступно только для женщин'

    def clean(self):
        """
        Общая валидация формы.

        Проверяет:
        1. Уникальность ФИО в дереве
        2. Дата смерти не раньше даты рождения
        3. Девичья фамилия только для женщин
        """
        cleaned_data = super().clean()

        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        gender = cleaned_data.get('gender')
        maiden_name = cleaned_data.get('maiden_name')
        birth_date = cleaned_data.get('birth_date')
        death_date = cleaned_data.get('death_date')

        # 1. Проверка уникальности ФИО в дереве
        if first_name and self.tree:
            queryset = Person.objects.filter(
                first_name=first_name,
                last_name=last_name or '',
                tree=self.tree
            )

            # При редактировании исключаем текущую персону
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)

            if queryset.exists():
                raise ValidationError(
                    f'В этом дереве уже есть персона с именем '
                    f'"{first_name} {last_name or ""}". '
                    f'Используйте другое имя или найдите существующую персону.'
                )

        # 2. Дата смерти не раньше даты рождения
        if birth_date and death_date:
            if death_date < birth_date:
                raise ValidationError({
                    'death_date': 'Дата смерти не может быть раньше даты рождения.'
                })

        # 3. Девичья фамилия только для женщин
        if maiden_name and gender != GenderEnum.FEMALE:
            raise ValidationError({
                'maiden_name': 'Девичья фамилия указывается только для женщин.'
            })

        return cleaned_data

    def save(self, commit=True):
        """
        Сохраняем персону с автоматическим заполнением полей.

        - updated_by: текущий пользователь
        - sync_version: увеличиваем при изменении
        """
        person = super().save(commit=False)

        # Устанавливаем пользователя, который внёс изменения
        if self.user:
            person.updated_by = self.user

        # Увеличиваем версию синхронизации при обновлении
        if person.pk:
            person.sync_version += 1

        if commit:
            person.save()

        return person


class RelationshipForm(forms.ModelForm):
    """
    Форма создания родственной связи между двумя персонами.

    Валидация:
    - Обе персоны должны быть из одного дерева
    - Нельзя создать связь с самим собой
    - Проверка уникальности связи
    """

    class Meta:
        model = Relationship
        fields = [
            'from_person',
            'to_person',
            'relationship_type',
            'start_date',
            'end_date',
            'is_current',
            'description',
        ]
        widgets = {
            'from_person': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'to_person': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'relationship_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'start_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            }),
            'is_current': forms.CheckboxInput(attrs={
                'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500',
            }),
            'description': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Дополнительная информация о связи',
            }),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        """
        Инициализация формы.

        Args:
            tree: Дерево, из которого выбираем персон (обязательно)
            user: Текущий пользователь (для заполнения created_by)
        """
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user

        # Ограничиваем выбор персон только текущим деревом
        if tree:
            self.fields['from_person'].queryset = Person.objects.filter(tree=tree)
            self.fields['to_person'].queryset = Person.objects.filter(tree=tree)

        # Помечаем обязательные поля
        self.fields['from_person'].required = True
        self.fields['to_person'].required = True
        self.fields['relationship_type'].required = True

    def clean(self):
        """
        Общая валидация формы.

        Проверяет:
        1. Обе персоны из одного дерева
        2. Нельзя создать связь с самим собой
        3. Уникальность связи
        """
        cleaned_data = super().clean()

        from_person = cleaned_data.get('from_person')
        to_person = cleaned_data.get('to_person')
        relationship_type = cleaned_data.get('relationship_type')

        # 1. Проверка, что обе персоны из одного дерева
        if from_person and to_person:
            if from_person.tree != to_person.tree:
                raise ValidationError(
                    'Обе персоны должны принадлежать одному дереву.'
                )

            # 2. Нельзя создать связь с самим собой
            if from_person == to_person:
                raise ValidationError(
                    'Нельзя создать связь персоны с самой собой.'
                )

            # 3. Проверка уникальности связи
            if from_person and to_person and relationship_type:
                queryset = Relationship.objects.filter(
                    from_person=from_person,
                    to_person=to_person,
                    relationship_type=relationship_type
                )

                # При редактировании исключаем текущую связь
                if self.instance.pk:
                    queryset = queryset.exclude(pk=self.instance.pk)

                if queryset.exists():
                    raise ValidationError(
                        f'Такая связь уже существует между '
                        f'"{from_person.full_name_display}" и '
                        f'"{to_person.full_name_display}".'
                    )

        return cleaned_data

    def save(self, commit=True):
        """
        Сохраняем связь с автоматическим заполнением полей.

        - created_by: текущий пользователь
        - sync_version: увеличиваем при изменении
        """
        relationship = super().save(commit=False)

        # Устанавливаем пользователя, который создал связь
        if self.user:
            relationship.created_by = self.user

        # Увеличиваем версию синхронизации при обновлении
        if relationship.pk:
            relationship.sync_version += 1

        if commit:
            relationship.save()

        return relationship