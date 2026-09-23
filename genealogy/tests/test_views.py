"""
Тесты для views приложения genealogy.

Проверяют:
- Доступность страниц для разных пользователей
- Корректность отображения списка деревьев
- Проверку прав доступа
- CRUD для персон
- CRUD для родственных связей
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from genealogy.models import (
    CollaboratorRoleEnum,
    Person,
    Relationship,
    Tree,
    TreeCollaborator,
)


class AuthenticationViewsTest(TestCase):
    """Тесты страниц аутентификации."""

    def test_login_page_accessible(self) -> None:
        """Страница входа доступна анонимному пользователю."""
        response = self.client.get(reverse('genealogy:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Вход в Исток')

    def test_login_with_valid_credentials(self) -> None:
        """Вход с правильными учётными данными работает."""
        User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        response = self.client.post(
            reverse('genealogy:login'),
            {'username': 'testuser', 'password': 'testpass123'}
        )
        # Должен быть редирект после успешного входа
        self.assertEqual(response.status_code, 302)

    def test_login_with_invalid_credentials(self) -> None:
        """Вход с неправильными учётными данными показывает ошибку."""
        User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        response = self.client.post(
            reverse('genealogy:login'),
            {'username': 'testuser', 'password': 'wrongpass'}
        )
        # Остаёмся на странице входа с ошибкой
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Неверное имя пользователя или пароль')

    def test_logout_requires_post(self) -> None:
        """Выход работает через POST-запрос."""
        User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('genealogy:logout'))
        # Должен быть редирект после выхода
        self.assertEqual(response.status_code, 302)

    def test_password_change_requires_login(self) -> None:
        """Страница смены пароля требует входа."""
        response = self.client.get(reverse('genealogy:password_change'))
        # Должен быть редирект на страницу входа
        self.assertEqual(response.status_code, 302)

    def test_password_change_accessible_when_logged_in(self) -> None:
        """Страница смены пароля доступна авторизованному пользователю."""
        User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('genealogy:password_change'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Смена пароля')


class TreeListViewTest(TestCase):
    """Тесты главной страницы (список деревьев)."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        # Пользователь с деревом
        self.user = User.objects.create_user(
            username='treeowner',
            password='pass123'
        )
        self.tree = Tree.objects.create(
            name='Семья Ивановых',
            description='Родовое дерево семьи Ивановых'
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

        # Добавляем несколько персон
        for i in range(5):
            Person.objects.create(
                first_name=f'Person{i}',
                last_name='Иванов',
                tree=self.tree
            )

        # Другой пользователь без деревьев
        self.other_user = User.objects.create_user(
            username='otheruser',
            password='pass123'
        )

        # Суперпользователь
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )

        # Публичное дерево
        self.public_tree = Tree.objects.create(
            name='Публичное дерево',
            is_public=True
        )

    def test_home_requires_login(self) -> None:
        """Главная страница требует входа."""
        response = self.client.get(reverse('genealogy:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_home_accessible_when_logged_in(self) -> None:
        """Главная страница доступна авторизованному пользователю."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Мои деревья')

    def test_user_sees_own_trees(self) -> None:
        """Пользователь видит свои деревья."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Семья Ивановых')

    def test_user_does_not_see_other_private_trees(self) -> None:
        """Пользователь не видит приватные деревья других пользователей."""
        self.client.login(username='otheruser', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertNotContains(response, 'Семья Ивановых')

    def test_user_sees_public_trees(self) -> None:
        """Пользователь видит публичные деревья."""
        self.client.login(username='otheruser', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Публичное дерево')

    def test_superuser_sees_all_trees(self) -> None:
        """Суперпользователь видит все деревья."""
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Семья Ивановых')
        self.assertContains(response, 'Публичное дерево')

    def test_tree_shows_persons_count(self) -> None:
        """Дерево показывает количество персон."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        # Мы добавили 5 персон в setUp
        self.assertContains(response, '5')

    def test_empty_state_for_user_without_trees(self) -> None:
        """Показывается пустое состояние для пользователя без деревьев."""
        # Создаем пользователя без деревьев (но видим публичное)
        user_no_trees = User.objects.create_user(
            username='notrees',
            password='pass123'
        )
        # Удаляем публичное дерево для чистого теста
        self.public_tree.delete()

        self.client.login(username='notrees', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Пока нет деревьев')

    def test_tree_shows_user_role(self) -> None:
        """Дерево показывает роль пользователя."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Владелец')

    def test_collaborator_sees_tree(self) -> None:
        """Соавтор видит дерево."""
        editor = User.objects.create_user(
            username='editor',
            password='pass123'
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=editor,
            role=CollaboratorRoleEnum.EDITOR
        )

        self.client.login(username='editor', password='pass123')
        response = self.client.get(reverse('genealogy:home'))
        self.assertContains(response, 'Семья Ивановых')
        self.assertContains(response, 'Редактор')


class TreeDetailViewTest(TestCase):
    """Тесты детальной страницы дерева."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='treeowner',
            password='pass123'
        )
        self.tree = Tree.objects.create(
            name='Семья Ивановых',
            description='Родовое дерево'
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

        # Добавляем персон
        self.person1 = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )
        self.person2 = Person.objects.create(
            first_name='Мария',
            last_name='Иванова',
            tree=self.tree
        )

    def test_tree_detail_requires_login(self) -> None:
        """Детальная страница требует входа."""
        response = self.client.get(
            reverse('genealogy:tree_detail', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_tree_detail_accessible_for_owner(self) -> None:
        """Владелец может открыть детальную страницу."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_detail', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Семья Ивановых')

    def test_tree_detail_shows_persons(self) -> None:
        """Детальная страница показывает персон."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_detail', args=[self.tree.pk])
        )
        self.assertContains(response, 'Иванов Иван')
        self.assertContains(response, 'Иванова Мария')

    def test_tree_detail_forbidden_for_other_user(self) -> None:
        """Другой пользователь не может открыть приватное дерево."""
        other_user = User.objects.create_user(
            username='other',
            password='pass123'
        )
        self.client.login(username='other', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_detail', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 403)


class TreeDataAPITest(TestCase):
    """Тесты API для получения данных дерева."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='treeowner',
            password='pass123'
        )
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )

    def test_api_requires_login(self) -> None:
        """API требует входа."""
        response = self.client.get(
            reverse('genealogy:tree_data_api', args=[self.tree.pk])
        )
        # Должен быть редирект на страницу входа
        self.assertEqual(response.status_code, 302)

    def test_api_returns_json(self) -> None:
        """API возвращает JSON."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_data_api', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_api_contains_nodes_and_edges(self) -> None:
        """API содержит узлы и рёбра."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_data_api', args=[self.tree.pk])
        )
        data = response.json()
        self.assertIn('nodes', data)
        self.assertIn('edges', data)
        self.assertEqual(len(data['nodes']), 1)

    def test_api_forbidden_for_other_user(self) -> None:
        """API запрещён для других пользователей."""
        other_user = User.objects.create_user(
            username='other',
            password='pass123'
        )
        self.client.login(username='other', password='pass123')
        response = self.client.get(
            reverse('genealogy:tree_data_api', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 403)


class PersonCRUDViewsTest(TestCase):
    """Тесты CRUD для персон."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.owner = User.objects.create_user(
            username='owner',
            password='pass123'
        )
        self.editor = User.objects.create_user(
            username='editor',
            password='pass123'
        )
        self.viewer = User.objects.create_user(
            username='viewer',
            password='pass123'
        )
        self.other_user = User.objects.create_user(
            username='other',
            password='pass123'
        )

        self.tree = Tree.objects.create(name='Тестовое дерево')

        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.owner,
            role=CollaboratorRoleEnum.OWNER
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.editor,
            role=CollaboratorRoleEnum.EDITOR
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.viewer,
            role=CollaboratorRoleEnum.VIEWER
        )

        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender='male',
            tree=self.tree
        )

    def test_create_requires_login(self) -> None:
        """Создание требует входа."""
        response = self.client.get(
            reverse('genealogy:person_create', args=[self.tree.pk])
        )
        # Должен быть редирект на страницу входа
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_by_owner(self) -> None:
        """Владелец может создавать персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать персон."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_create_person_success(self) -> None:
        """Успешное создание персоны."""
        self.client.login(username='owner', password='pass123')
        data = {
            'first_name': 'Мария',
            'last_name': 'Петрова',
            'gender': 'female',
            'birth_date': '1995-05-15',
        }
        response = self.client.post(
            reverse('genealogy:person_create', args=[self.tree.pk]),
            data
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Person.objects.filter(
                first_name='Мария',
                last_name='Петрова',
                tree=self.tree
            ).exists()
        )

    def test_create_person_duplicate_forbidden(self) -> None:
        """Создание дубликата запрещено."""
        self.client.login(username='owner', password='pass123')
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',  # Уже существует
            'gender': 'male',
        }
        response = self.client.post(
            reverse('genealogy:person_create', args=[self.tree.pk]),
            data
        )
        self.assertEqual(response.status_code, 200)  # Остаёмся на форме
        self.assertContains(response, 'уже есть персона')

    def test_update_requires_login(self) -> None:
        """Редактирование требует входа."""
        response = self.client.get(
            reverse('genealogy:person_update', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_update_by_owner(self) -> None:
        """Владелец может редактировать персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_update', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_update_by_editor(self) -> None:
        """Редактор может редактировать персон."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_update', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_update_by_viewer_forbidden(self) -> None:
        """Читатель не может редактировать персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_update', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_update_success(self) -> None:
        """Успешное обновление персоны."""
        self.client.login(username='owner', password='pass123')
        data = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'gender': 'male',
            'middle_name': 'Иванович',  # Добавляем отчество
        }
        response = self.client.post(
            reverse('genealogy:person_update', args=[self.person.pk]),
            data
        )
        self.assertEqual(response.status_code, 302)

        self.person.refresh_from_db()
        self.assertEqual(self.person.middle_name, 'Иванович')

    def test_delete_requires_login(self) -> None:
        """Удаление требует входа."""
        response = self.client.get(
            reverse('genealogy:person_delete', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_delete', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_delete', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление персоны."""
        self.client.login(username='owner', password='pass123')
        person_pk = self.person.pk

        response = self.client.post(
            reverse('genealogy:person_delete', args=[person_pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Person.objects.filter(pk=person_pk).exists())

    def test_person_detail_requires_login(self) -> None:
        """Карточка персоны требует входа."""
        response = self.client.get(
            reverse('genealogy:person_detail', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_person_detail_accessible(self) -> None:
        """Карточка персоны доступна."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_detail', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иванов Иван')

    def test_person_detail_forbidden_for_other_user(self) -> None:
        """Карточка персоны недоступна для чужого пользователя."""
        self.client.login(username='other', password='pass123')
        response = self.client.get(
            reverse('genealogy:person_detail', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 403)


class RelationshipCRUDViewsTest(TestCase):
    """Тесты CRUD для родственных связей."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.owner = User.objects.create_user(
            username='owner',
            password='pass123'
        )
        self.editor = User.objects.create_user(
            username='editor',
            password='pass123'
        )
        self.viewer = User.objects.create_user(
            username='viewer',
            password='pass123'
        )

        self.tree = Tree.objects.create(name='Тестовое дерево')

        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.owner,
            role=CollaboratorRoleEnum.OWNER
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.editor,
            role=CollaboratorRoleEnum.EDITOR
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.viewer,
            role=CollaboratorRoleEnum.VIEWER
        )

        self.father = Person.objects.create(
            first_name='Пётр',
            last_name='Иванов',
            gender='male',
            tree=self.tree
        )
        self.son = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender='male',
            tree=self.tree
        )

        self.relationship = Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type='biological_parent'
        )

    def test_create_requires_login(self) -> None:
        """Создание связи требует входа."""
        response = self.client.get(
            reverse('genealogy:relationship_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_by_owner(self) -> None:
        """Владелец может создавать связи."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:relationship_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать связи."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(
            reverse('genealogy:relationship_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать связи."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:relationship_create', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_create_relationship_success(self) -> None:
        """Успешное создание связи."""
        self.client.login(username='owner', password='pass123')

        # Создаём ещё одну персону для связи
        mother = Person.objects.create(
            first_name='Мария',
            last_name='Иванова',
            gender='female',
            tree=self.tree
        )

        data = {
            'from_person': mother.pk,
            'to_person': self.son.pk,
            'relationship_type': 'biological_parent',
        }
        response = self.client.post(
            reverse('genealogy:relationship_create', args=[self.tree.pk]),
            data
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Relationship.objects.filter(
                from_person=mother,
                to_person=self.son,
                relationship_type='biological_parent'
            ).exists()
        )

    def test_delete_requires_login(self) -> None:
        """Удаление связи требует входа."""
        response = self.client.get(
            reverse('genealogy:relationship_delete', args=[self.relationship.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять связи."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:relationship_delete', args=[self.relationship.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять связи."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:relationship_delete', args=[self.relationship.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление связи."""
        self.client.login(username='owner', password='pass123')
        relationship_pk = self.relationship.pk

        response = self.client.post(
            reverse('genealogy:relationship_delete', args=[relationship_pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Relationship.objects.filter(pk=relationship_pk).exists())