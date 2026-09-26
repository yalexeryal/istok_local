"""
Тесты для моделей приложения genealogy.
"""

from datetime import date

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from genealogy.models import (
    ChangeRequest,
    ChangeRequestStatusEnum,
    CollaboratorRoleEnum,
    EventTypeEnum,
    ExportFormatEnum,
    ExportStatusEnum,
    ExportTask,
    ExportTypeEnum,
    GenderEnum,
    ImportStatusEnum,
    ImportTask,
    LifeEvent,
    Person,
    PrivacySettings,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
    UserProfile,
    UserTierEnum,
)


class TreeModelTest(TestCase):
    """Тесты модели Tree."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)

    def test_tree_creation(self) -> None:
        """Тест создания дерева."""
        self.assertEqual(self.tree.name, "Тестовое дерево")
        self.assertEqual(self.tree.get_persons_count(), 0)

    def test_tree_unique_name(self) -> None:
        """Тест: имя дерева должно быть уникальным."""
        with self.assertRaises(IntegrityError):
            Tree.objects.create(name="Тестовое дерево")

    def test_tree_get_owner(self) -> None:
        """Тест получения владельца дерева."""
        self.assertEqual(self.tree.get_owner(), self.user)

    def test_tree_user_can_edit(self) -> None:
        """Тест прав на редактирование дерева."""
        self.assertTrue(self.tree.user_can_edit(self.user))
        other_user = User.objects.create_user(username="other", password="pass123")
        self.assertFalse(self.tree.user_can_edit(other_user))

    def test_tree_user_can_view(self) -> None:
        """Тест прав на просмотр дерева."""
        self.assertTrue(self.tree.user_can_view(self.user))
        other_user = User.objects.create_user(username="other", password="pass123")
        self.assertFalse(self.tree.user_can_view(other_user))

        self.tree.is_public = True
        self.tree.save()
        self.assertTrue(self.tree.user_can_view(other_user))


class PersonModelTest(TestCase):
    """Тесты модели Person."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")

    def test_person_creation(self) -> None:
        """Тест создания персоны."""
        person = Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        self.assertEqual(person.full_name_display, "Иванов Иван")

    def test_person_full_name_display_male(self) -> None:
        """Тест формирования полного имени для мужчины."""
        person = Person.objects.create(
            first_name="Иван", last_name="Иванов", middle_name="Иванович", gender=GenderEnum.MALE, tree=self.tree
        )
        self.assertEqual(person.full_name_display, "Иванов Иван Иванович")

    def test_person_full_name_display_female_with_maiden_name(self) -> None:
        """Тест формирования полного имени для женщины с девичьей фамилией."""
        female = Person.objects.create(
            first_name="Мария", last_name="Петрова", maiden_name="Сидорова", gender=GenderEnum.FEMALE, tree=self.tree
        )
        self.assertEqual(female.full_name_display, "Петрова (Сидорова) Мария")

    def test_person_age_calculation(self) -> None:
        """Тест расчёта возраста."""
        person = Person.objects.create(
            first_name="Иван",
            last_name="Иванов",
            gender=GenderEnum.MALE,
            tree=self.tree,
            birth_date=date(1990, 1, 1),
            death_date=date(2020, 1, 1),
        )
        self.assertEqual(person.age, 30)

    def test_person_is_alive(self) -> None:
        """Тест проверки, жива ли персона."""
        alive = Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        self.assertTrue(alive.is_alive)
        dead = Person.objects.create(
            first_name="Пётр", last_name="Петров", gender=GenderEnum.MALE, tree=self.tree, death_date=date(2020, 1, 1)
        )
        self.assertFalse(dead.is_alive)

    def test_person_parents_children_relationships(self) -> None:
        """Тест связей родитель-ребёнок."""
        parent = Person.objects.create(first_name="Отец", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        child = Person.objects.create(first_name="Сын", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        Relationship.objects.create(
            from_person=parent, to_person=child, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        self.assertEqual(child.get_parents().count(), 1)
        self.assertEqual(parent.get_children().count(), 1)

    def test_person_siblings(self) -> None:
        """Тест получения братьев и сестёр."""
        parent = Person.objects.create(first_name="Отец", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        child1 = Person.objects.create(first_name="Сын1", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        child2 = Person.objects.create(first_name="Сын2", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        Relationship.objects.create(
            from_person=parent, to_person=child1, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        Relationship.objects.create(
            from_person=parent, to_person=child2, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        self.assertEqual(child1.get_siblings().count(), 1)
        self.assertEqual(child1.get_siblings().first(), child2)

    def test_person_allows_namesakes(self) -> None:
        """Тест: модель разрешает создание полных тёзок (UniqueConstraint удалён)."""
        Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        # Это не должно вызывать IntegrityError
        Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        self.assertEqual(Person.objects.filter(first_name="Иван", last_name="Иванов", tree=self.tree).count(), 2)


class LifeEventModelTest(TestCase):
    """Тесты модели LifeEvent."""

    def setUp(self) -> None:
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_life_event_creation(self) -> None:
        """Тест создания события жизни."""
        event = LifeEvent.objects.create(
            person=self.person, event_type=EventTypeEnum.BIRTH, event_date=date(1990, 1, 1)
        )
        self.assertEqual(event.person, self.person)
        self.assertEqual(event.event_type, EventTypeEnum.BIRTH)


class RelationshipModelTest(TestCase):
    """Тесты модели Relationship."""

    def setUp(self) -> None:
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person1 = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.person2 = Person.objects.create(
            first_name="Пётр", last_name="Петров", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_relationship_creation(self) -> None:
        """Тест создания связи."""
        rel = Relationship.objects.create(
            from_person=self.person1, to_person=self.person2, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        self.assertEqual(rel.from_person, self.person1)
        self.assertEqual(rel.to_person, self.person2)

    def test_relationship_unique_constraint(self) -> None:
        """Тест: связь между двумя персонами одного типа должна быть уникальной."""
        Relationship.objects.create(
            from_person=self.person1, to_person=self.person2, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        with self.assertRaises(IntegrityError):
            Relationship.objects.create(
                from_person=self.person1,
                to_person=self.person2,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
            )


class TreeCollaboratorModelTest(TestCase):
    """Тесты модели TreeCollaborator."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")

    def test_collaborator_creation(self) -> None:
        """Тест создания соавтора."""
        collab = TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.assertEqual(collab.role, CollaboratorRoleEnum.OWNER)

    def test_collaborator_unique_constraint(self) -> None:
        """Тест: пользователь может быть соавтором дерева только один раз."""
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        with self.assertRaises(IntegrityError):
            TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.EDITOR)


class UserProfileModelTest(TestCase):
    """Тесты модели UserProfile."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.profile = UserProfile.objects.get(user=self.user)
        self.tree = Tree.objects.create(name="Тестовое дерево")

    def test_profile_creation(self) -> None:
        """Тест автоматического создания профиля."""
        self.assertEqual(self.profile.tier, UserTierEnum.FREE)

    def test_can_add_person_free_tier(self) -> None:
        """Тест лимита персон для бесплатного тарифа."""
        self.assertTrue(self.profile.can_add_person(self.tree))

    def test_can_add_person_subscription_tier(self) -> None:
        """Тест лимита персон для подписки."""
        self.profile.tier = UserTierEnum.SUBSCRIPTION
        self.profile.save()
        self.assertTrue(self.profile.can_add_person(self.tree))


class ChangeRequestModelTest(TestCase):
    """Тесты модели ChangeRequest."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_change_request_creation(self) -> None:
        """Тест создания запроса на изменение."""
        req = ChangeRequest.objects.create(
            person=self.person,
            requested_by=self.user,
            owner=self.user,
            change_type="update_name",
            status=ChangeRequestStatusEnum.PENDING,
        )
        self.assertEqual(req.status, ChangeRequestStatusEnum.PENDING)


class PrivacySettingsModelTest(TestCase):
    """Тесты модели PrivacySettings."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")

    def test_privacy_settings_created_automatically(self) -> None:
        """Тест автоматического создания настроек приватности."""
        settings = PrivacySettings.objects.get(user=self.user)
        self.assertIsNotNone(settings)

    def test_privacy_settings_defaults(self) -> None:
        """Тест значений по умолчанию для настроек приватности."""
        settings = PrivacySettings.objects.get(user=self.user)
        self.assertFalse(settings.hide_birth_date)
        self.assertTrue(settings.hide_notes)


class ExportTaskModelTest(TestCase):
    """Тесты модели ExportTask."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")

    def test_export_task_creation(self) -> None:
        """Тест создания задачи экспорта."""
        task = ExportTask.objects.create(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.FULL,
            export_format=ExportFormatEnum.JSON_ZIP,
        )
        self.assertEqual(task.status, ExportStatusEnum.PENDING)

    def test_export_task_str(self) -> None:
        """Тест строкового представления задачи экспорта."""
        task = ExportTask.objects.create(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.FULL,
            export_format=ExportFormatEnum.JSON_ZIP,
        )
        self.assertIn("Экспорт", str(task))


class ImportTaskModelTest(TestCase):
    """Тесты модели ImportTask."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")

    def test_import_task_creation(self) -> None:
        """Тест создания задачи импорта."""
        task = ImportTask.objects.create(
            user=self.user,
            import_format=ExportFormatEnum.JSON_ZIP,
            source_file="test.zip",
        )
        self.assertEqual(task.status, ImportStatusEnum.PENDING)

    def test_import_task_str(self) -> None:
        """Тест строкового представления задачи импорта."""
        task = ImportTask.objects.create(
            user=self.user,
            import_format=ExportFormatEnum.JSON_ZIP,
            source_file="test.zip",
        )
        self.assertIn("Импорт", str(task))
