"""
Тесты для форм приложения genealogy.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from genealogy.forms import (
    LifeEventForm,
    PersonForm,
    RelationshipForm,
)
from genealogy.models import (
    CollaboratorRoleEnum,
    EventTypeEnum,
    GenderEnum,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)


class PersonFormTest(TestCase):
    """Тесты формы PersonForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )

    def test_valid_form(self) -> None:
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'birth_date': '1990-01-01',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_required_fields(self) -> None:
        data = {'last_name': 'Иванов', 'gender': GenderEnum.MALE}
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)

    def test_unique_name_in_tree(self) -> None:
        Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_same_name_different_tree(self) -> None:
        other_tree = Tree.objects.create(name='Другое дерево')
        Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=other_tree
        )
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_edit_same_person_allowed(self) -> None:
        person = Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, instance=person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_death_before_birth_invalid(self) -> None:
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
            'birth_date': '1990-01-01',
            'death_date': '1980-01-01',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('death_date', form.errors)

    def test_maiden_name_only_for_female(self) -> None:
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE, 'maiden_name': 'Петрова',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('maiden_name', form.errors)

    def test_maiden_name_for_female_allowed(self) -> None:
        data = {
            'first_name': 'Мария', 'last_name': 'Петрова',
            'gender': GenderEnum.FEMALE, 'maiden_name': 'Сидорова',
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_sets_updated_by(self) -> None:
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        person = form.save()
        self.assertEqual(person.updated_by, self.user)

    def test_save_increments_sync_version(self) -> None:
        person = Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )
        initial_version = person.sync_version
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': GenderEnum.MALE, 'middle_name': 'Иванович',
        }
        form = PersonForm(data=data, instance=person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        updated_person = form.save()
        self.assertEqual(updated_person.sync_version, initial_version + 1)


class RelationshipFormTest(TestCase):
    """Тесты формы RelationshipForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )
        self.father = Person.objects.create(
            first_name='Пётр', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )
        self.son = Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )

    def test_valid_relationship_form(self) -> None:
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_required_fields(self) -> None:
        data = {'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT}
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('from_person', form.errors)
        self.assertIn('to_person', form.errors)

    def test_same_tree_validation(self) -> None:
        other_tree = Tree.objects.create(name='Другое дерево')
        other_person = Person.objects.create(
            first_name='Мария', last_name='Петрова',
            gender=GenderEnum.FEMALE, tree=other_tree
        )
        data = {
            'from_person': self.father.pk,
            'to_person': other_person.pk,
            'relationship_type': RelationshipTypeEnum.SPOUSE,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('to_person', form.errors)

    def test_self_relationship_invalid(self) -> None:
        data = {
            'from_person': self.father.pk,
            'to_person': self.father.pk,
            'relationship_type': RelationshipTypeEnum.SPOUSE,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_duplicate_relationship_invalid(self) -> None:
        Relationship.objects.create(
            from_person=self.father, to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_different_relationship_type_allowed(self) -> None:
        Relationship.objects.create(
            from_person=self.father, to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.GUARDIAN,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_sets_created_by(self) -> None:
        data = {
            'from_person': self.father.pk,
            'to_person': self.son.pk,
            'relationship_type': RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        relationship = form.save()
        self.assertEqual(relationship.created_by, self.user)


class LifeEventFormTest(TestCase):
    """Тесты формы LifeEventForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='testuser', password='pass123')
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )
        self.person = Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender=GenderEnum.MALE, tree=self.tree
        )
        self.related_person = Person.objects.create(
            first_name='Мария', last_name='Иванова',
            gender=GenderEnum.FEMALE, tree=self.tree
        )

    def test_valid_event_form(self) -> None:
        data = {
            'event_type': EventTypeEnum.EDUCATION,
            'event_date': '2010-09-01',
            'location': 'МГУ',
            'description': 'Бакалавриат',
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertTrue(form.is_valid())

    def test_required_event_type(self) -> None:
        data = {
            'event_date': '2010-09-01',
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('event_type', form.errors)

    def test_end_date_before_event_date_invalid(self) -> None:
        data = {
            'event_type': EventTypeEnum.WORK,
            'event_date': '2020-01-01',
            'end_date': '2019-01-01',  # Раньше начала
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_related_person_from_same_tree(self) -> None:
        data = {
            'event_type': EventTypeEnum.MARRIAGE,
            'event_date': '2015-06-15',
            'related_person': self.related_person.pk,
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertTrue(form.is_valid())

    def test_related_person_from_different_tree_invalid(self) -> None:
        other_tree = Tree.objects.create(name='Другое дерево')
        other_person = Person.objects.create(
            first_name='Пётр', last_name='Сидоров',
            gender=GenderEnum.MALE, tree=other_tree
        )
        data = {
            'event_type': EventTypeEnum.MARRIAGE,
            'event_date': '2015-06-15',
            'related_person': other_person.pk,
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('related_person', form.errors)

    def test_related_person_self_invalid(self) -> None:
        data = {
            'event_type': EventTypeEnum.MARRIAGE,
            'event_date': '2015-06-15',
            'related_person': self.person.pk,  # Та же персона
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertFalse(form.is_valid())
        self.assertIn('related_person', form.errors)

    def test_save_sets_person(self) -> None:
        data = {
            'event_type': EventTypeEnum.BIRTH,
            'event_date': '1990-01-01',
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertTrue(form.is_valid())
        event = form.save()
        self.assertEqual(event.person, self.person)

    def test_save_sets_created_by(self) -> None:
        data = {
            'event_type': EventTypeEnum.BIRTH,
            'event_date': '1990-01-01',
        }
        form = LifeEventForm(
            data=data, person=self.person, tree=self.tree, user=self.user
        )
        self.assertTrue(form.is_valid())
        event = form.save()
        self.assertEqual(event.created_by, self.user)

    def test_save_increments_sync_version(self) -> None:
        event = LifeEvent.objects.create(
            person=self.person,
            event_type=EventTypeEnum.BIRTH,
            event_date='1990-01-01'
        )
        initial_version = event.sync_version
        data = {
            'event_type': EventTypeEnum.BIRTH,
            'event_date': '1990-01-01',
            'location': 'Москва',
        }
        form = LifeEventForm(
            data=data, instance=event, person=self.person,
            tree=self.tree, user=self.user
        )
        self.assertTrue(form.is_valid())
        updated_event = form.save()
        self.assertEqual(updated_event.sync_version, initial_version + 1)