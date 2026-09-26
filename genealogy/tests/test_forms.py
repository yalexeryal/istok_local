"""
Тесты для форм приложения genealogy.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from genealogy.forms import LifeEventForm, PersonForm, RelationshipForm
from genealogy.models import (
    EventTypeEnum,
    GenderEnum,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
)


class PersonFormTest(TestCase):
    """Тесты формы PersonForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_valid_form(self) -> None:
        """Тест: валидная форма сохраняется успешно."""
        data = {
            "first_name": "Пётр",
            "last_name": "Петров",
            "gender": GenderEnum.MALE,
            "birth_date": "1990-01-01",
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        person = form.save()
        self.assertEqual(person.first_name, "Пётр")
        self.assertEqual(person.updated_by, self.user)

    def test_required_fields(self) -> None:
        """Тест: обязательные поля first_name и gender."""
        data = {"last_name": "Иванов"}
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("first_name", form.errors)
        self.assertIn("gender", form.errors)

    def test_unique_name_in_tree(self) -> None:
        """Тест: форма предупреждает о дубликате, но остаётся валидной для принудительного создания."""
        Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        self.assertIsNotNone(form.exact_duplicate)
        self.assertEqual(form.exact_duplicate.first_name, "Иван")

    def test_same_name_different_tree(self) -> None:
        """Тест: одинаковые имена разрешены в разных деревьях."""
        tree2 = Tree.objects.create(name="Другое дерево")
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
        }
        form = PersonForm(data=data, tree=tree2, user=self.user)
        self.assertTrue(form.is_valid())

    def test_edit_same_person_allowed(self) -> None:
        """Тест: редактирование существующей персоны не считается дубликатом."""
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
        }
        form = PersonForm(data=data, instance=self.person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_death_before_birth_invalid(self) -> None:
        """Тест: дата смерти не может быть раньше даты рождения."""
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
            "birth_date": "1990-01-01",
            "death_date": "1980-01-01",
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("death_date", form.errors)

    def test_maiden_name_only_for_female(self) -> None:
        """Тест: девичья фамилия только для женщин."""
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
            "maiden_name": "Сидорова",
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("maiden_name", form.errors)

    def test_maiden_name_for_female_allowed(self) -> None:
        """Тест: девичья фамилия разрешена для женщин."""
        data = {
            "first_name": "Мария",
            "last_name": "Иванова",
            "gender": GenderEnum.FEMALE,
            "maiden_name": "Сидорова",
        }
        form = PersonForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_increments_sync_version(self) -> None:
        """Тест: сохранение увеличивает версию синхронизации."""
        self.assertEqual(self.person.sync_version, 0)
        form = PersonForm(
            instance=self.person,
            data={"first_name": "Иван", "gender": GenderEnum.MALE},
            tree=self.tree,
            user=self.user,
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.person.refresh_from_db()
        self.assertEqual(self.person.sync_version, 1)

    def test_save_sets_updated_by(self) -> None:
        """Тест: сохранение устанавливает пользователя, обновившего запись."""
        form = PersonForm(
            instance=self.person,
            data={"first_name": "Иван", "gender": GenderEnum.MALE},
            tree=self.tree,
            user=self.user,
        )
        self.assertTrue(form.is_valid())
        form.save()
        self.person.refresh_from_db()
        self.assertEqual(self.person.updated_by, self.user)


class RelationshipFormTest(TestCase):
    """Тесты формы RelationshipForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person1 = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.person2 = Person.objects.create(
            first_name="Пётр", last_name="Петров", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_valid_relationship_form(self) -> None:
        """Тест: валидная форма связи сохраняется успешно."""
        data = {
            "from_person": self.person1.pk,
            "to_person": self.person2.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        rel = form.save()
        self.assertEqual(rel.from_person, self.person1)
        self.assertEqual(rel.created_by, self.user)

    def test_required_fields(self) -> None:
        """Тест: обязательные поля from_person, to_person, relationship_type."""
        data = {}
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("from_person", form.errors)
        self.assertIn("to_person", form.errors)
        self.assertIn("relationship_type", form.errors)

    def test_same_tree_validation(self) -> None:
        """Тест: обе персоны должны быть из одного дерева."""
        tree2 = Tree.objects.create(name="Другое дерево")
        person3 = Person.objects.create(first_name="Анна", last_name="Анна", gender=GenderEnum.FEMALE, tree=tree2)
        data = {
            "from_person": self.person1.pk,
            "to_person": person3.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        # Ошибка будет в поле to_person, так как его нет в queryset текущего дерева
        self.assertIn("to_person", form.errors)

    def test_self_relationship_invalid(self) -> None:
        """Тест: нельзя создать связь персоны с самой собой."""
        data = {
            "from_person": self.person1.pk,
            "to_person": self.person1.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_duplicate_relationship_invalid(self) -> None:
        """Тест: нельзя создать дублирующуюся связь того же типа."""
        Relationship.objects.create(
            from_person=self.person1,
            to_person=self.person2,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
        )
        data = {
            "from_person": self.person1.pk,
            "to_person": self.person2.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    def test_different_relationship_type_allowed(self) -> None:
        """Тест: разные типы связей между теми же персонами разрешены."""
        Relationship.objects.create(
            from_person=self.person1,
            to_person=self.person2,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
        )
        data = {
            "from_person": self.person1.pk,
            "to_person": self.person2.pk,
            "relationship_type": RelationshipTypeEnum.STEP_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_save_sets_created_by(self) -> None:
        """Тест: сохранение устанавливает пользователя, создавшего запись."""
        data = {
            "from_person": self.person1.pk,
            "to_person": self.person2.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        form = RelationshipForm(data=data, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        form.save()
        rel = Relationship.objects.get(from_person=self.person1, to_person=self.person2)
        self.assertEqual(rel.created_by, self.user)


class LifeEventFormTest(TestCase):
    """Тесты формы LifeEventForm."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.related_person = Person.objects.create(
            first_name="Пётр", last_name="Петров", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_valid_event_form(self) -> None:
        """Тест: валидная форма события сохраняется успешно."""
        data = {
            "event_type": EventTypeEnum.BIRTH,
            "event_date": "1990-01-01",
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        event = form.save()
        self.assertEqual(event.person, self.person)
        self.assertEqual(event.created_by, self.user)

    def test_required_event_type(self) -> None:
        """Тест: event_type является обязательным полем."""
        data = {"event_date": "1990-01-01"}
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("event_type", form.errors)

    def test_end_date_before_event_date_invalid(self) -> None:
        """Тест: дата окончания не может быть раньше даты начала."""
        data = {
            "event_type": EventTypeEnum.WORK,
            "event_date": "2020-01-01",
            "end_date": "2010-01-01",
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("end_date", form.errors)

    def test_related_person_from_same_tree(self) -> None:
        """Тест: связанная персона должна быть из того же дерева."""
        data = {
            "event_type": EventTypeEnum.MARRIAGE,
            "event_date": "2015-06-15",
            "related_person": self.related_person.pk,
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())

    def test_related_person_from_different_tree_invalid(self) -> None:
        """Тест: связанная персона из другого дерева недопустима."""
        tree2 = Tree.objects.create(name="Другое дерево")
        person2 = Person.objects.create(first_name="Анна", last_name="Анна", gender=GenderEnum.FEMALE, tree=tree2)
        data = {
            "event_type": EventTypeEnum.MARRIAGE,
            "event_date": "2015-06-15",
            "related_person": person2.pk,
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("related_person", form.errors)

    def test_related_person_self_invalid(self) -> None:
        """Тест: нельзя связать персону саму с собой."""
        data = {
            "event_type": EventTypeEnum.MARRIAGE,
            "event_date": "2015-06-15",
            "related_person": self.person.pk,
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn("related_person", form.errors)

    def test_save_sets_person(self) -> None:
        """Тест: сохранение устанавливает персону, если она не была указана."""
        data = {
            "event_type": EventTypeEnum.BIRTH,
            "event_date": "1990-01-01",
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        event = form.save()
        self.assertEqual(event.person, self.person)

    def test_save_increments_sync_version(self) -> None:
        """Тест: сохранение увеличивает версию синхронизации."""
        event = LifeEvent.objects.create(person=self.person, event_type=EventTypeEnum.BIRTH, event_date="1990-01-01")
        self.assertEqual(event.sync_version, 0)
        form = LifeEventForm(
            instance=event,
            data={"event_type": EventTypeEnum.BIRTH, "event_date": "1990-01-01"},
            person=self.person,
            tree=self.tree,
            user=self.user,
        )
        self.assertTrue(form.is_valid())
        form.save()
        event.refresh_from_db()
        self.assertEqual(event.sync_version, 1)

    def test_save_sets_created_by(self) -> None:
        """Тест: сохранение устанавливает пользователя, создавшего запись."""
        data = {
            "event_type": EventTypeEnum.BIRTH,
            "event_date": "1990-01-01",
        }
        form = LifeEventForm(data=data, person=self.person, tree=self.tree, user=self.user)
        self.assertTrue(form.is_valid())
        form.save()
        event = LifeEvent.objects.get(person=self.person, event_type=EventTypeEnum.BIRTH)
        self.assertEqual(event.created_by, self.user)
