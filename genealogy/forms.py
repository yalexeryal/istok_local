"""
Django Forms для приложения genealogy.

Включает:
- PersonForm — форма создания/редактирования персоны
- RelationshipForm — форма создания родственной связи
- ExportForm — форма настройки экспорта
- ImportForm — форма загрузки файла для импорта
"""
from django import forms
from django.core.exceptions import ValidationError

from .models import (
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ExportTypeEnum,
    GenderEnum,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
)


class PersonForm(forms.ModelForm):
    """
    Форма создания/редактирования персоны.
    """

    class Meta:
        model = Person
        fields = [
            'first_name', 'middle_name', 'last_name', 'maiden_name', 'gender',
            'birth_date', 'is_birth_date_approx', 'death_date', 'is_death_date_approx',
            'birth_place', 'death_place', 'burial_place', 'culture', 'photo', 'notes',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иван'}),
            'middle_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иванович'}),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Иванов'}),
            'maiden_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Только для женщин'}),
            'gender': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'birth_date': forms.DateInput(attrs={'type': 'date',
                                                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'death_date': forms.DateInput(attrs={'type': 'date',
                                                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'birth_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Москва, Россия'}),
            'death_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'burial_place': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'culture': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Русский'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'w-full px-4 py-2 border border-gray-300 rounded-md'}),
            'notes': forms.Textarea(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'rows': 4, 'placeholder': 'Дополнительная информация о персоне...'}),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user
        if tree and not self.instance.pk:
            self.instance.tree = tree
        self.fields['first_name'].required = True
        self.fields['gender'].required = True
        if self.instance.gender and self.instance.gender != GenderEnum.FEMALE:
            self.fields['maiden_name'].help_text = 'Доступно только для женщин'

    def clean(self):
        cleaned_data = super().clean()
        first_name = cleaned_data.get('first_name')
        last_name = cleaned_data.get('last_name')
        gender = cleaned_data.get('gender')
        maiden_name = cleaned_data.get('maiden_name')
        birth_date = cleaned_data.get('birth_date')
        death_date = cleaned_data.get('death_date')

        if first_name and self.tree:
            queryset = Person.objects.filter(
                first_name=first_name,
                last_name=last_name or '',
                tree=self.tree
            )
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError(
                    f'В этом дереве уже есть персона с именем '
                    f'"{first_name} {last_name or ""}".'
                )

        if birth_date and death_date and death_date < birth_date:
            raise ValidationError({'death_date': 'Дата смерти не может быть раньше даты рождения.'})

        if maiden_name and gender != GenderEnum.FEMALE:
            raise ValidationError({'maiden_name': 'Девичья фамилия указывается только для женщин.'})

        return cleaned_data

    def save(self, commit=True):
        person = super().save(commit=False)
        if self.user:
            person.updated_by = self.user
        if person.pk:
            person.sync_version += 1
        if commit:
            person.save()
        return person


class RelationshipForm(forms.ModelForm):
    """Форма создания родственной связи между двумя персонами."""

    class Meta:
        model = Relationship
        fields = ['from_person', 'to_person', 'relationship_type', 'start_date', 'end_date', 'is_current',
                  'description']
        widgets = {
            'from_person': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'to_person': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'relationship_type': forms.Select(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'start_date': forms.DateInput(attrs={'type': 'date',
                                                 'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'end_date': forms.DateInput(attrs={'type': 'date',
                                               'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'is_current': forms.CheckboxInput(
                attrs={'class': 'w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'}),
            'description': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Дополнительная информация о связи'}),
        }

    def __init__(self, *args, tree=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        self.user = user
        if tree:
            self.fields['from_person'].queryset = Person.objects.filter(tree=tree)
            self.fields['to_person'].queryset = Person.objects.filter(tree=tree)
        self.fields['from_person'].required = True
        self.fields['to_person'].required = True
        self.fields['relationship_type'].required = True

    def clean(self):
        cleaned_data = super().clean()
        from_person = cleaned_data.get('from_person')
        to_person = cleaned_data.get('to_person')
        relationship_type = cleaned_data.get('relationship_type')

        if from_person and to_person:
            if from_person.tree != to_person.tree:
                raise ValidationError('Обе персоны должны принадлежать одному дереву.')
            if from_person == to_person:
                raise ValidationError('Нельзя создать связь персоны с самой собой.')
            if relationship_type:
                queryset = Relationship.objects.filter(
                    from_person=from_person,
                    to_person=to_person,
                    relationship_type=relationship_type
                )
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
        relationship = super().save(commit=False)
        if self.user:
            relationship.created_by = self.user
        if relationship.pk:
            relationship.sync_version += 1
        if commit:
            relationship.save()
        return relationship


class ExportForm(forms.Form):
    """Форма настройки экспорта дерева."""
    export_type = forms.ChoiceField(
        choices=ExportTypeEnum.choices,
        label='Тип экспорта',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'})
    )
    export_format = forms.ChoiceField(
        choices=ExportFormatEnum.choices,
        label='Формат файла',
        initial=ExportFormatEnum.JSON_ZIP,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'})
    )
    target_person = forms.ModelChoiceField(
        queryset=Person.objects.none(),
        label='Целевая персона (для экспорта родственников)',
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'})
    )

    def __init__(self, *args, tree=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = tree
        if tree:
            self.fields['target_person'].queryset = tree.persons.all().order_by('last_name', 'first_name')

    def clean(self):
        cleaned_data = super().clean()
        export_type = cleaned_data.get('export_type')
        target_person = cleaned_data.get('target_person')

        if export_type == ExportTypeEnum.RELATIVE and not target_person:
            raise ValidationError({
                'target_person': 'Для экспорта родственников необходимо выбрать целевую персону.'
            })

        return cleaned_data


class ImportForm(forms.Form):
    """Форма загрузки файла для импорта."""
    source_file = forms.FileField(
        label='Файл для импорта (.zip)',
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            'accept': '.zip'
        })
    )
    target_tree = forms.ModelChoiceField(
        queryset=Tree.objects.none(),
        label='Импортировать в существующее дерево (опционально)',
        required=False,
        help_text='Если не выбрано, будет создано новое дерево.',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500'})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            from django.db.models import Q
            self.fields['target_tree'].queryset = Tree.objects.filter(
                Q(collaborators__user=user, collaborators__role__in=[
                    CollaboratorRoleEnum.OWNER,
                    CollaboratorRoleEnum.EDITOR
                ]) | Q(is_public=True)
            ).distinct()

    def clean_source_file(self):
        file = self.cleaned_data.get('source_file')
        if file:
            if not file.name.endswith('.zip'):
                raise ValidationError('Поддерживаются только файлы с расширением .zip')
            if file.size > 50 * 1024 * 1024:  # 50 MB
                raise ValidationError('Размер файла не должен превышать 50 МБ')
        return file