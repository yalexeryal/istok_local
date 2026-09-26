"""
Тесты для views приложения genealogy.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

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


class AuthenticationViewsTest(TestCase):
    """Тесты аутентификации."""

    def test_login_page_accessible(self) -> None:
        """Страница входа доступна."""
        response = self.client.get(reverse("genealogy:login"))
        self.assertEqual(response.status_code, 200)

    def test_login_with_valid_credentials(self) -> None:
        """Вход с правильными учётными данными работает."""
        User.objects.create_user(username="testuser", password="testpass123")
        response = self.client.post(reverse("genealogy:login"), {"username": "testuser", "password": "testpass123"})
        self.assertEqual(response.status_code, 302)
        # Django перенаправляет на LOGIN_REDIRECT_URL (обычно '/')
        self.assertIn(response.url, ["/", reverse("genealogy:tree_list")])

    def test_login_with_invalid_credentials(self) -> None:
        """Вход с неправильными учётными данными показывает ошибку."""
        User.objects.create_user(username="testuser", password="testpass123")
        response = self.client.post(reverse("genealogy:login"), {"username": "testuser", "password": "wrongpass"})
        self.assertEqual(response.status_code, 200)
        # Стандартное сообщение Django об ошибке входа
        self.assertContains(response, "Неверное имя пользователя или пароль")

    def test_logout_requires_post(self) -> None:
        """Выход требует POST-запроса."""
        response = self.client.get(reverse("genealogy:logout"))
        self.assertEqual(response.status_code, 405)

    def test_password_change_requires_login(self) -> None:
        """Смена пароля требует авторизации."""
        response = self.client.get(reverse("genealogy:password_change"))
        self.assertRedirects(response, f"/accounts/login/?next={reverse('genealogy:password_change')}")

    def test_password_change_accessible_when_logged_in(self) -> None:
        """Смена пароля доступна авторизованному пользователю."""
        User.objects.create_user(username="testuser", password="testpass123")
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("genealogy:password_change"))
        self.assertEqual(response.status_code, 200)


class TreeListViewTest(TestCase):
    """Тесты списка деревьев."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Моё дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.public_tree = Tree.objects.create(name="Публичное дерево", is_public=True)
        self.other_tree = Tree.objects.create(name="Чужое дерево")

    def test_tree_list_requires_login(self) -> None:
        """Список деревьев требует авторизации."""
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertRedirects(response, f"/accounts/login/?next={reverse('genealogy:tree_list')}")

    def test_tree_list_accessible_when_logged_in(self) -> None:
        """Список деревьев доступен авторизованному пользователю."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Моё дерево")

    def test_user_sees_own_trees(self) -> None:
        """Пользователь видит свои деревья."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertContains(response, "Моё дерево")

    def test_user_does_not_see_other_private_trees(self) -> None:
        """Пользователь не видит чужие приватные деревья."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertNotContains(response, "Чужое дерево")

    def test_user_sees_public_trees(self) -> None:
        """Пользователь видит публичные деревья."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertContains(response, "Публичное дерево")

    def test_superuser_sees_all_trees(self) -> None:
        """Суперпользователь видит все деревья."""
        User.objects.create_superuser(username="admin", password="pass123")
        self.client.login(username="admin", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertContains(response, "Моё дерево")
        self.assertContains(response, "Чужое дерево")
        self.assertContains(response, "Публичное дерево")

    def test_tree_shows_persons_count(self) -> None:
        """Список деревьев показывает количество персон."""
        Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        # Проверяем наличие числа и слова "Персон" (они могут быть разделены HTML-тегами)
        self.assertContains(response, ">1<")
        self.assertContains(response, "Персон")

    def test_tree_shows_user_role(self) -> None:
        """Список деревьев показывает роль пользователя."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertContains(response, "Владелец")

    def test_collaborator_sees_tree(self) -> None:
        """Соавтор видит дерево."""
        collaborator = User.objects.create_user(username="collab", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=collaborator, role=CollaboratorRoleEnum.EDITOR)
        self.client.login(username="collab", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertContains(response, "Моё дерево")

    def test_empty_state_for_user_without_trees(self) -> None:
        """Показывается пустое состояние для пользователя без деревьев."""
        User.objects.create_user(username="notrees", password="pass123")
        self.public_tree.delete()
        self.client.login(username="notrees", password="pass123")
        response = self.client.get(reverse("genealogy:tree_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "У вас пока нет деревьев")


class TreeDetailViewTest(TestCase):
    """Тесты детальной страницы дерева."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_tree_detail_requires_login(self) -> None:
        """Детальная страница дерева требует авторизации."""
        response = self.client.get(reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertRedirects(response, f"/accounts/login/?next={reverse('genealogy:tree_detail', args=[self.tree.pk])}")

    def test_tree_detail_accessible_for_owner(self) -> None:
        """Владелец может открыть детальную страницу дерева."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Тестовое дерево")

    def test_tree_detail_forbidden_for_other_user(self) -> None:
        """Другой пользователь не может открыть приватное дерево."""
        User.objects.create_user(username="other", password="pass123")
        self.client.login(username="other", password="pass123")
        response = self.client.get(reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_tree_detail_shows_persons(self) -> None:
        """Детальная страница показывает персоны дерева."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertContains(response, "Иванов Иван")


class TreeDataAPITest(TestCase):
    """Тесты API данных дерева."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )

    def test_api_requires_login(self) -> None:
        """API требует авторизации."""
        response = self.client.get(reverse("genealogy:tree_data_api", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 302)

    def test_api_forbidden_for_other_user(self) -> None:
        """API запрещён для других пользователей."""
        User.objects.create_user(username="other", password="pass123")
        self.client.login(username="other", password="pass123")
        response = self.client.get(reverse("genealogy:tree_data_api", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_api_returns_json(self) -> None:
        """API возвращает JSON."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_data_api", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_api_contains_nodes_and_edges(self) -> None:
        """API содержит узлы и связи."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:tree_data_api", args=[self.tree.pk]))
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertEqual(len(data["nodes"]), 1)


class PersonCRUDViewsTest(TestCase):
    """Тесты CRUD операций с персонами."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.editor = User.objects.create_user(username="editor", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR)
        self.viewer = User.objects.create_user(username="viewer", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER)

    def test_create_requires_login(self) -> None:
        """Создание персоны требует авторизации."""
        response = self.client.get(reverse("genealogy:person_create", args=[self.tree.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:person_create', args=[self.tree.pk])}"
        )

    def test_create_by_owner(self) -> None:
        """Владелец может создавать персон."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:person_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать персон."""
        self.client.login(username="editor", password="pass123")
        response = self.client.get(reverse("genealogy:person_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать персон."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:person_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_create_person_success(self) -> None:
        """Успешное создание персоны."""
        self.client.login(username="testuser", password="pass123")
        data = {
            "first_name": "Пётр",
            "last_name": "Петров",
            "gender": GenderEnum.MALE,
        }
        response = self.client.post(reverse("genealogy:person_create", args=[self.tree.pk]), data)
        self.assertRedirects(response, reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(Person.objects.filter(first_name="Пётр").count(), 1)

    def test_create_person_duplicate_forbidden(self) -> None:
        """Тест: при создании дубликата показывается предупреждение, а не ошибка валидации."""
        # ВАЖНО: нужно залогиниться, иначе будет редирект на страницу входа!
        self.client.login(username="testuser", password="pass123")
        Person.objects.create(first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree)
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
        }
        response = self.client.post(reverse("genealogy:person_create", args=[self.tree.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Возможные дубликаты")

    def test_update_requires_login(self) -> None:
        """Обновление персоны требует авторизации."""
        response = self.client.get(reverse("genealogy:person_update", args=[self.person.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:person_update', args=[self.person.pk])}"
        )

    def test_update_by_owner(self) -> None:
        """Владелец может обновлять персон."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:person_update", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update_by_editor(self) -> None:
        """Редактор может обновлять персон."""
        self.client.login(username="editor", password="pass123")
        response = self.client.get(reverse("genealogy:person_update", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update_by_viewer_forbidden(self) -> None:
        """Читатель не может обновлять персон."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:person_update", args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_update_success(self) -> None:
        """Успешное обновление персоны."""
        self.client.login(username="testuser", password="pass123")
        data = {
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": GenderEnum.MALE,
            "birth_date": "1990-01-01",
        }
        response = self.client.post(reverse("genealogy:person_update", args=[self.person.pk]), data)
        self.assertRedirects(response, reverse("genealogy:person_detail", args=[self.person.pk]))
        self.person.refresh_from_db()
        self.assertEqual(self.person.birth_date.isoformat(), "1990-01-01")

    def test_delete_requires_login(self) -> None:
        """Удаление персоны требует авторизации."""
        response = self.client.get(reverse("genealogy:person_delete", args=[self.person.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:person_delete', args=[self.person.pk])}"
        )

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять персон."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:person_delete", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять персон."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:person_delete", args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление персоны."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.post(reverse("genealogy:person_delete", args=[self.person.pk]))
        self.assertRedirects(response, reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(Person.objects.filter(pk=self.person.pk).count(), 0)

    def test_person_detail_requires_login(self) -> None:
        """Детальная страница персоны требует авторизации."""
        response = self.client.get(reverse("genealogy:person_detail", args=[self.person.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:person_detail', args=[self.person.pk])}"
        )

    def test_person_detail_accessible(self) -> None:
        """Детальная страница персоны доступна."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:person_detail", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Иванов Иван")

    def test_person_detail_forbidden_for_other_user(self) -> None:
        """Детальная страница персоны запрещена для других пользователей."""
        User.objects.create_user(username="other", password="pass123")
        self.client.login(username="other", password="pass123")
        response = self.client.get(reverse("genealogy:person_detail", args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)


class RelationshipCRUDViewsTest(TestCase):
    """Тесты CRUD операций со связями."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.person1 = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.person2 = Person.objects.create(
            first_name="Пётр", last_name="Петров", gender=GenderEnum.MALE, tree=self.tree
        )
        self.relationship = Relationship.objects.create(
            from_person=self.person1, to_person=self.person2, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        self.editor = User.objects.create_user(username="editor", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR)
        self.viewer = User.objects.create_user(username="viewer", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER)

    def test_create_requires_login(self) -> None:
        """Создание связи требует авторизации."""
        response = self.client.get(reverse("genealogy:relationship_create", args=[self.tree.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:relationship_create', args=[self.tree.pk])}"
        )

    def test_create_by_owner(self) -> None:
        """Владелец может создавать связи."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:relationship_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать связи."""
        self.client.login(username="editor", password="pass123")
        response = self.client.get(reverse("genealogy:relationship_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать связи."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:relationship_create", args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_create_relationship_success(self) -> None:
        """Успешное создание связи."""
        self.client.login(username="testuser", password="pass123")
        person3 = Person.objects.create(first_name="Анна", last_name="Анна", gender=GenderEnum.FEMALE, tree=self.tree)
        data = {
            "from_person": self.person1.pk,
            "to_person": person3.pk,
            "relationship_type": RelationshipTypeEnum.BIOLOGICAL_PARENT,
        }
        response = self.client.post(reverse("genealogy:relationship_create", args=[self.tree.pk]), data)
        self.assertRedirects(response, reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(Relationship.objects.filter(to_person=person3).count(), 1)

    def test_delete_requires_login(self) -> None:
        """Удаление связи требует авторизации."""
        response = self.client.get(reverse("genealogy:relationship_delete", args=[self.relationship.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:relationship_delete', args=[self.relationship.pk])}"
        )

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять связи."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:relationship_delete", args=[self.relationship.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять связи."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:relationship_delete", args=[self.relationship.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление связи."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.post(reverse("genealogy:relationship_delete", args=[self.relationship.pk]))
        self.assertRedirects(response, reverse("genealogy:tree_detail", args=[self.tree.pk]))
        self.assertEqual(Relationship.objects.filter(pk=self.relationship.pk).count(), 0)


class WelcomeAndRegisterViewsTest(TestCase):
    """Тесты страниц приветствия и регистрации."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")

    def test_welcome_page_accessible_anonymously(self) -> None:
        """Страница приветствия доступна анонимно."""
        response = self.client.get(reverse("genealogy:welcome"))
        self.assertEqual(response.status_code, 200)

    def test_welcome_redirects_authenticated_user(self) -> None:
        """Страница приветствия перенаправляет авторизованного пользователя."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:welcome"))
        self.assertRedirects(response, reverse("genealogy:tree_list"))

    def test_register_page_accessible(self) -> None:
        """Страница регистрации доступна."""
        response = self.client.get(reverse("genealogy:register"))
        self.assertEqual(response.status_code, 200)

    def test_register_redirects_authenticated_user(self) -> None:
        """Страница регистрации перенаправляет авторизованного пользователя."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:register"))
        self.assertRedirects(response, reverse("genealogy:tree_list"))

    def test_register_creates_user(self) -> None:
        """Регистрация создаёт пользователя."""
        initial_count = User.objects.count()
        response = self.client.post(
            reverse("genealogy:register"),
            {"username": "newuser", "password1": "testpass123", "password2": "testpass123"},
        )
        self.assertEqual(User.objects.count(), initial_count + 1)
        self.assertRedirects(response, reverse("genealogy:tree_list"))

    def test_register_creates_user_profile(self) -> None:
        """Регистрация создаёт профиль пользователя."""
        self.client.post(
            reverse("genealogy:register"),
            {"username": "newuser", "password1": "testpass123", "password2": "testpass123"},
        )
        new_user = User.objects.get(username="newuser")
        self.assertTrue(hasattr(new_user, "profile"))

    def test_register_invalid_password(self) -> None:
        """Регистрация с несовпадающими паролями не проходит."""
        initial_count = User.objects.count()
        response = self.client.post(
            reverse("genealogy:register"),
            {"username": "newuser", "password1": "testpass123", "password2": "wrongpass"},
        )
        self.assertEqual(User.objects.count(), initial_count)
        self.assertEqual(response.status_code, 200)

    def test_login_page_has_register_link(self) -> None:
        """На странице входа есть ссылка на регистрацию."""
        response = self.client.get(reverse("genealogy:login"))
        self.assertContains(response, "Зарегистрироваться")


class LifeEventCRUDViewsTest(TestCase):
    """Тесты CRUD операций с событиями жизни."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="testuser", password="pass123")
        self.tree = Tree.objects.create(name="Тестовое дерево")
        TreeCollaborator.objects.create(tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER)
        self.person = Person.objects.create(
            first_name="Иван", last_name="Иванов", gender=GenderEnum.MALE, tree=self.tree
        )
        self.event = LifeEvent.objects.create(
            person=self.person, event_type=EventTypeEnum.BIRTH, event_date="1990-01-01"
        )
        self.editor = User.objects.create_user(username="editor", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR)
        self.viewer = User.objects.create_user(username="viewer", password="pass123")
        TreeCollaborator.objects.create(tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER)

    def test_create_requires_login(self) -> None:
        """Создание события требует авторизации."""
        response = self.client.get(reverse("genealogy:life_event_create", args=[self.person.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:life_event_create', args=[self.person.pk])}"
        )

    def test_create_by_owner(self) -> None:
        """Владелец может создавать события."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_create", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать события."""
        self.client.login(username="editor", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_create", args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать события."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_create", args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_create_event_success(self) -> None:
        """Успешное создание события."""
        self.client.login(username="testuser", password="pass123")
        data = {
            "event_type": EventTypeEnum.WORK,
            "event_date": "2010-01-01",
        }
        response = self.client.post(reverse("genealogy:life_event_create", args=[self.person.pk]), data)
        self.assertRedirects(response, reverse("genealogy:person_detail", args=[self.person.pk]))
        self.assertEqual(LifeEvent.objects.filter(person=self.person, event_type=EventTypeEnum.WORK).count(), 1)

    def test_update_requires_login(self) -> None:
        """Обновление события требует авторизации."""
        response = self.client.get(reverse("genealogy:life_event_update", args=[self.event.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:life_event_update', args=[self.event.pk])}"
        )

    def test_update_by_owner(self) -> None:
        """Владелец может обновлять события."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_update", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update_by_viewer_forbidden(self) -> None:
        """Читатель не может обновлять события."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_update", args=[self.event.pk]))
        self.assertEqual(response.status_code, 403)

    def test_update_success(self) -> None:
        """Успешное обновление события."""
        self.client.login(username="testuser", password="pass123")
        data = {
            "event_type": EventTypeEnum.BIRTH,
            "event_date": "1990-01-01",
            "location": "Москва",
        }
        response = self.client.post(reverse("genealogy:life_event_update", args=[self.event.pk]), data)
        self.assertRedirects(response, reverse("genealogy:person_detail", args=[self.person.pk]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.location, "Москва")

    def test_delete_requires_login(self) -> None:
        """Удаление события требует авторизации."""
        response = self.client.get(reverse("genealogy:life_event_delete", args=[self.event.pk]))
        self.assertRedirects(
            response, f"/accounts/login/?next={reverse('genealogy:life_event_delete', args=[self.event.pk])}"
        )

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять события."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_delete", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять события."""
        self.client.login(username="viewer", password="pass123")
        response = self.client.get(reverse("genealogy:life_event_delete", args=[self.event.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление события."""
        self.client.login(username="testuser", password="pass123")
        response = self.client.post(reverse("genealogy:life_event_delete", args=[self.event.pk]))
        self.assertRedirects(response, reverse("genealogy:person_detail", args=[self.person.pk]))
        self.assertEqual(LifeEvent.objects.filter(pk=self.event.pk).count(), 0)
