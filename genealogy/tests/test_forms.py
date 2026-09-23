"""
Тесты для форм приложения genealogy.

Проверяют:
- Валидацию форм
- Уникальность ФИО
- Корректность дат
- Сохранение с автоматическим заполнением полей
- Валидацию связей между персонами
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from genealogy.forms import PersonForm, RelationshipForm
from genealogy.models import (
    CollaboratorRoleEnum,
    GenderEnum,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)


class PersonFormTest(TestCase):
    """Тесты формы PersonForm."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='pass123'
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

    def test_valid_form(self) -> None:
        """Тест валидной формы."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'birth_date': '1990-01-01',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_required_fields(self) -> None:
        """Тест обязательных полей."""
        data = {
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)

    def test_unique_name_in_tree(self) -> None:
        """Тест уникальности ФИО в дереве."""
        # Создаём персону
        Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )

        # Пытаемся создать такую же
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_same_name_different_tree(self) -> None:
        """Тест: одинаковое ФИО в разных деревьях разрешено."""
        other_tree = Tree.objects.create(name='Другое дерево')

        Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=other_tree
        )

        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_edit_same_person_allowed(self) -> None:
        """Тест: редактирование той же персоны разрешено."""
        person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )

        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, instance=person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_death_before_birth_invalid(self) -> None:
        """Тест: дата смерти не может быть раньше даты рождения."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'birth_date': '1990-01-01',
            'death_date': '1980-01-01',  # Раньше рождения
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('death_date', form.errors)

    def test_maiden_name_only_for_female(self) -> None:
        """Тест: девичья фамилия только для женщин."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'maiden_name': 'Петрова',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('maiden_name', form.errors)

    def test_maiden_name_for_female_allowed(self) -> None:
        """Тест: девичья фамилия для женщины разрешена."""
        data = {
            'first_name': 'Мария',
            'last_name': 'Петрова',
            'gender': GenderEnum.FEMALE,
            'maiden_name': 'Сидорова',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_sets_updated_by(self) -> None:
        """Тест: при сохранении устанавливается updated_by."""
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

        person = form.save()
        self.assertEqual(person.updated_by, self.user)

    def test_save_increments_sync_version(self) -> None:
        """Тест: при обновлении sync_version увеличивается."""
        person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )
        initial_version = person.sync_version

        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'middle_name': 'Иванович',  # Добавляем отчество
        }
        form = PersonForm(data=data, instance=person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

        updated_person = form.save()
        self.assertEqual(updated_person.sync_version, initial_version + 1)


class RelationshipFormTest(TestCase):
    """Тесты формы RelationshipForm."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='pass123'
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

        self.father = Person.objects.create(
            first_name='Пётр',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )
        self.son = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )

    def test_valid_relationship_form(self) -> None:
        """Тест валидной формы связи."""
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_required_fields(self) -> None:
        """Тест обязательных полей."""
        data = {
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('from_person', form.errors)
        self.assertIn('to_person', form.errors)

    def test_same_tree_validation(self) -> None:
        """
        Тест: обе персоны должны быть из одного дерева.

        Форма ограничивает queryset поля to_person только персонами
        текущего дерева, поэтому ошибка появляется на поле to_person,
        а не в __all__.
        """
        other_tree = Tree.objects.create(name='Другое дерево')
        other_person = Person.objects.create(
            first_name='Мария',
            last_name='Петрова',
            gender=GenderEnum.FEMALE,
            tree=other_tree
        )

        data = {
            'from_person': self.father.pk,
            'to_person': other_person.pk,  # Из другого дерева
            'relationship_type': RelationshipTypeEnum.SPOUSE,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        # Ошибка на поле to_person, так как queryset отфильтрован
        self.assertIn('to_person', form.errors)

    def test_self_relationship_invalid(self) -> None:
        """Тест: нельзя создать связь с самим собой."""
        data = {
            'from_person': self.father.pk,
            'to_person': self.father.pk,  # Та же персона
            'relationship_type': RelationshipTypeEnum.SPOUSE,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_duplicate_relationship_invalid(self) -> None:
        """Тест: дубликаты связей запрещены."""
        # Создаём связь
        Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )

        # Пытаемся создать такую же
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_different_relationship_type_allowed(self) -> None:
        """Тест: разные типы связей между теми же персонами разрешены."""
        Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )

        # Другой тип связи — разрешено
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.GUARDIAN,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_sets_created_by(self) -> None:
        """Тест: при сохранении устанавливается created_by."""
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

        relationship = form.save()
        self.assertEqual(relationship.created_by, self.user)