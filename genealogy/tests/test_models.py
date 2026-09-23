"""
Тесты для моделей генеалогии.
"""
from datetime import date
from django.contrib.auth.models import User
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone

from genealogy.models import (
    Tree,
    Person,
    LifeEvent,
    Relationship,
    TreeCollaborator,
    ChangeRequest,
    UserProfile,
    GenderEnum,
    EventTypeEnum,
    RelationshipTypeEnum,
    CollaboratorRoleEnum,
    ChangeRequestStatusEnum,
    PersonStatusEnum,
    UserTierEnum,
)


class TreeModelTest(TestCase):
    """Тесты модели Tree."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.tree = Tree.objects.create(
            name='Тестовое дерево',
            description='Описание теста'
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

    def test_tree_creation(self) -> None:
        """Тест создания дерева."""
        self.assertEqual(self.tree.name, 'Тестовое дерево')
        self.assertEqual(self.tree.description, 'Описание теста')
        self.assertFalse(self.tree.is_public)
        self.assertEqual(self.tree.sync_version, 0)

    def test_tree_unique_name(self) -> None:
        """Тест уникальности имени дерева."""
        with self.assertRaises(IntegrityError):
            Tree.objects.create(name='Тестовое дерево')

    def test_tree_get_owner(self) -> None:
        """Тест получения владельца дерева."""
        owner = self.tree.get_owner()
        self.assertEqual(owner, self.user)

    def test_tree_user_can_edit(self) -> None:
        """Тест проверки прав на редактирование."""
        # Владелец может редактировать
        self.assertTrue(self.tree.user_can_edit(self.user))

        # Другой пользователь не может
        other_user = User.objects.create_user(
            username='other',
            password='pass123'
        )
        self.assertFalse(self.tree.user_can_edit(other_user))

        # Редактор может редактировать
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=other_user,
            role=CollaboratorRoleEnum.EDITOR
        )
        self.assertTrue(self.tree.user_can_edit(other_user))

    def test_tree_user_can_view(self) -> None:
        """Тест проверки прав на просмотр."""
        # Владелец может просматривать
        self.assertTrue(self.tree.user_can_view(self.user))

        # Другой пользователь не может (дерево приватное)
        other_user = User.objects.create_user(
            username='viewer',
            password='pass123'
        )
        self.assertFalse(self.tree.user_can_view(other_user))

        # Публичное дерево могут все
        self.tree.is_public = True
        self.tree.save()
        self.assertTrue(self.tree.user_can_view(other_user))

    def test_tree_get_persons_count(self) -> None:
        """Тест получения количества персон."""
        self.assertEqual(self.tree.get_persons_count(), 0)

        Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )
        self.assertEqual(self.tree.get_persons_count(), 1)


class PersonModelTest(TestCase):
    """Тесты модели Person."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.tree = Tree.objects.create(name='Тестовое дерево')
        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            middle_name='Иванович',
            gender=GenderEnum.MALE,
            birth_date=date(1990, 1, 1),
            tree=self.tree
        )

    def test_person_creation(self) -> None:
        """Тест создания персоны."""
        self.assertEqual(self.person.first_name, 'Иван')
        self.assertEqual(self.person.last_name, 'Иванов')
        self.assertEqual(self.person.gender, GenderEnum.MALE)
        self.assertEqual(self.person.status, PersonStatusEnum.SANDBOX)
        self.assertEqual(self.person.sync_version, 0)

    def test_person_unique_constraint(self) -> None:
        """Тест уникальности ФИО в рамках дерева."""
        with self.assertRaises(IntegrityError):
            Person.objects.create(
                first_name='Иван',
                last_name='Иванов',
                tree=self.tree
            )

    def test_person_same_name_different_tree(self) -> None:
        """Тест: одинаковое ФИО в разных деревьях разрешено."""
        other_tree = Tree.objects.create(name='Другое дерево')
        other_person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=other_tree
        )
        self.assertEqual(other_person.first_name, 'Иван')

    def test_person_full_name_display_male(self) -> None:
        """Тест формирования полного имени для мужчины."""
        self.assertEqual(self.person.full_name_display, 'Иванов Иван Иванович')

    def test_person_full_name_display_female_with_maiden_name(self) -> None:
        """Тест формирования полного имени для женщины с девичьей фамилией."""
        female = Person.objects.create(
            first_name='Мария',
            last_name='Петрова',
            maiden_name='Сидорова',
            gender=GenderEnum.FEMALE,
            tree=self.tree
        )
        self.assertEqual(female.full_name_display, 'Петрова (Сидорова) Мария')

    def test_person_age_calculation(self) -> None:
        """Тест вычисления возраста."""
        # Живой человек
        age = self.person.age
        self.assertIsNotNone(age)
        self.assertGreater(age, 0)

        # Умерший человек
        self.person.death_date = date(2020, 1, 1)
        self.person.save()
        self.assertEqual(self.person.age, 30)

    def test_person_is_alive(self) -> None:
        """Тест проверки, жива ли персона."""
        self.assertTrue(self.person.is_alive)

        self.person.death_date = date(2020, 1, 1)
        self.person.save()
        self.assertFalse(self.person.is_alive)

    def test_person_parents_children_relationships(self) -> None:
        """Тест связей родитель-ребенок."""
        father = Person.objects.create(
            first_name='Петр',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )

        Relationship.objects.create(
            from_person=father,
            to_person=self.person,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )

        parents = self.person.get_parents()
        self.assertEqual(parents.count(), 1)
        self.assertEqual(parents.first(), father)

        children = father.get_children()
        self.assertEqual(children.count(), 1)
        self.assertEqual(children.first(), self.person)

    def test_person_siblings(self) -> None:
        """Тест получения братьев и сестер."""
        father = Person.objects.create(
            first_name='Петр',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            tree=self.tree
        )

        sibling = Person.objects.create(
            first_name='Анна',
            last_name='Иванова',
            gender=GenderEnum.FEMALE,
            tree=self.tree
        )

        # Оба имеют одного отца
        Relationship.objects.create(
            from_person=father,
            to_person=self.person,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        Relationship.objects.create(
            from_person=father,
            to_person=sibling,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )

        siblings = self.person.get_siblings()
        self.assertEqual(siblings.count(), 1)
        self.assertEqual(siblings.first(), sibling)


class LifeEventModelTest(TestCase):
    """Тесты модели LifeEvent."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.tree = Tree.objects.create(name='Тестовое дерево')
        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )

    def test_life_event_creation(self) -> None:
        """Тест создания события."""
        event = LifeEvent.objects.create(
            person=self.person,
            event_type=EventTypeEnum.EDUCATION,
            event_date=date(2010, 9, 1),
            location='МГУ',
            description='Бакалавриат'
        )
        self.assertEqual(event.person, self.person)
        self.assertEqual(event.event_type, EventTypeEnum.EDUCATION)
        self.assertIn('2010', str(event))
        self.assertEqual(event.sync_version, 0)


class RelationshipModelTest(TestCase):
    """Тесты модели Relationship."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.tree = Tree.objects.create(name='Тестовое дерево')
        self.father = Person.objects.create(
            first_name='Петр',
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

    def test_relationship_creation(self) -> None:
        """Тест создания связи."""
        relationship = Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        self.assertEqual(relationship.from_person, self.father)
        self.assertEqual(relationship.to_person, self.son)
        self.assertEqual(relationship.sync_version, 0)

    def test_relationship_unique_constraint(self) -> None:
        """Тест уникальности связи."""
        Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        with self.assertRaises(IntegrityError):
            Relationship.objects.create(
                from_person=self.father,
                to_person=self.son,
                relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
            )


class TreeCollaboratorModelTest(TestCase):
    """Тесты модели TreeCollaborator."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')

    def test_collaborator_creation(self) -> None:
        """Тест создания соавтора."""
        collaborator = TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )
        self.assertEqual(collaborator.tree, self.tree)
        self.assertEqual(collaborator.user, self.user)
        self.assertEqual(collaborator.role, CollaboratorRoleEnum.OWNER)

    def test_collaborator_unique_constraint(self) -> None:
        """Тест уникальности пользователя в дереве."""
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )
        with self.assertRaises(IntegrityError):
            TreeCollaborator.objects.create(
                tree=self.tree,
                user=self.user,
                role=CollaboratorRoleEnum.EDITOR
            )


class UserProfileModelTest(TestCase):
    """
    Тесты модели UserProfile.

    Важно: UserProfile создаётся автоматически сигналом при создании User.
    Поэтому в тестах используем get_or_create вместо create.
    """

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        # Сигнал уже создал профиль, поэтому используем get_or_create
        self.profile, _ = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={'tier': UserTierEnum.FREE}
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')

    def test_profile_creation(self) -> None:
        """Тест создания профиля."""
        self.assertEqual(self.profile.user, self.user)
        self.assertEqual(self.profile.tier, UserTierEnum.FREE)
        self.assertEqual(self.profile.devices_count, 1)

    def test_can_add_person_free_tier(self) -> None:
        """Тест проверки лимита персон для Free тарифа."""
        # Free тариф: 200 персон
        self.assertTrue(self.profile.can_add_person(self.tree))

        # Добавляем 200 персон
        for i in range(200):
            Person.objects.create(
                first_name=f'Person{i}',
                last_name='Test',
                tree=self.tree
            )

        # Теперь нельзя добавить
        self.assertFalse(self.profile.can_add_person(self.tree))

    def test_can_add_person_subscription_tier(self) -> None:
        """Тест проверки лимита персон для Subscription тарифа."""
        self.profile.tier = UserTierEnum.SUBSCRIPTION
        self.profile.save()

        # Subscription: безлимит
        for i in range(300):
            Person.objects.create(
                first_name=f'Person{i}',
                last_name='Test',
                tree=self.tree
            )

        # Можно добавлять бесконечно
        self.assertTrue(self.profile.can_add_person(self.tree))


class ChangeRequestModelTest(TestCase):
    """Тесты модели ChangeRequest."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')
        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )

    def test_change_request_creation(self) -> None:
        """Тест создания запроса на изменение."""
        request = ChangeRequest.objects.create(
            person=self.person,
            requested_by=self.user,
            owner=self.user,
            change_type='update',
            proposed_data={'first_name': 'Петр'}
        )
        self.assertEqual(request.person, self.person)
        self.assertEqual(request.status, ChangeRequestStatusEnum.PENDING)
        self.assertEqual(request.proposed_data, {'first_name': 'Петр'})