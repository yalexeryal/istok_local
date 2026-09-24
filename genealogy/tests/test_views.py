"""
Тесты для views приложения genealogy.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from genealogy.models import (
    CollaboratorRoleEnum,
    LifeEvent,
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
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('genealogy:login'),
            {'username': 'testuser', 'password': 'testpass123'}
        )
        self.assertEqual(response.status_code, 302)

    def test_login_with_invalid_credentials(self) -> None:
        """Вход с неправильными учётными данными показывает ошибку."""
        User.objects.create_user(username='testuser', password='testpass123')
        response = self.client.post(
            reverse('genealogy:login'),
            {'username': 'testuser', 'password': 'wrongpass'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Неверное имя пользователя или пароль')

    def test_logout_requires_post(self) -> None:
        """Выход работает через POST-запрос."""
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.post(reverse('genealogy:logout'))
        self.assertEqual(response.status_code, 302)

    def test_password_change_requires_login(self) -> None:
        """Страница смены пароля требует входа."""
        response = self.client.get(reverse('genealogy:password_change'))
        self.assertEqual(response.status_code, 302)

    def test_password_change_accessible_when_logged_in(self) -> None:
        """Страница смены пароля доступна авторизованному пользователю."""
        User.objects.create_user(username='testuser', password='testpass123')
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('genealogy:password_change'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Смена пароля')


class TreeListViewTest(TestCase):
    """Тесты главной страницы (список деревьев)."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='treeowner', password='pass123')
        self.tree = Tree.objects.create(
            name='Семья Ивановых',
            description='Родовое дерево семьи Ивановых'
        )
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )

        for i in range(5):
            Person.objects.create(
                first_name=f'Person{i}',
                last_name='Иванов',
                tree=self.tree
            )

        self.other_user = User.objects.create_user(username='otheruser', password='pass123')
        self.superuser = User.objects.create_superuser(username='admin', password='adminpass123')
        self.public_tree = Tree.objects.create(name='Публичное дерево', is_public=True)

    def test_tree_list_requires_login(self) -> None:
        """Список деревьев требует входа."""
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_tree_list_accessible_when_logged_in(self) -> None:
        """Список деревьев доступен авторизованному пользователю."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Мои деревья')

    def test_user_sees_own_trees(self) -> None:
        """Пользователь видит свои деревья."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Семья Ивановых')

    def test_user_does_not_see_other_private_trees(self) -> None:
        """Пользователь не видит приватные деревья других пользователей."""
        self.client.login(username='otheruser', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertNotContains(response, 'Семья Ивановых')

    def test_user_sees_public_trees(self) -> None:
        """Пользователь видит публичные деревья."""
        self.client.login(username='otheruser', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Публичное дерево')

    def test_superuser_sees_all_trees(self) -> None:
        """Суперпользователь видит все деревья."""
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Семья Ивановых')
        self.assertContains(response, 'Публичное дерево')

    def test_tree_shows_persons_count(self) -> None:
        """Дерево показывает количество персон."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, '5')

    def test_empty_state_for_user_without_trees(self) -> None:
        """Показывается пустое состояние для пользователя без деревьев."""
        user_no_trees = User.objects.create_user(username='notrees', password='pass123')
        self.public_tree.delete()

        self.client.login(username='notrees', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Пока нет деревьев')

    def test_tree_shows_user_role(self) -> None:
        """Дерево показывает роль пользователя."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Владелец')

    def test_collaborator_sees_tree(self) -> None:
        """Соавтор видит дерево."""
        editor = User.objects.create_user(username='editor', password='pass123')
        TreeCollaborator.objects.create(
            tree=self.tree, user=editor, role=CollaboratorRoleEnum.EDITOR
        )

        self.client.login(username='editor', password='pass123')
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertContains(response, 'Семья Ивановых')
        self.assertContains(response, 'Редактор')


class TreeDetailViewTest(TestCase):
    """Тесты детальной страницы дерева."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='treeowner', password='pass123')
        self.tree = Tree.objects.create(name='Семья Ивановых', description='Родовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )

        self.person1 = Person.objects.create(first_name='Иван', last_name='Иванов', tree=self.tree)
        self.person2 = Person.objects.create(first_name='Мария', last_name='Иванова', tree=self.tree)

    def test_tree_detail_requires_login(self) -> None:
        """Детальная страница требует входа."""
        response = self.client.get(reverse('genealogy:tree_detail', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 302)

    def test_tree_detail_accessible_for_owner(self) -> None:
        """Владелец может открыть детальную страницу."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_detail', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Семья Ивановых')

    def test_tree_detail_shows_persons(self) -> None:
        """Детальная страница показывает персон."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_detail', args=[self.tree.pk]))
        self.assertContains(response, 'Иванов Иван')
        self.assertContains(response, 'Иванова Мария')

    def test_tree_detail_forbidden_for_other_user(self) -> None:
        """Другой пользователь не может открыть приватное дерево."""
        other_user = User.objects.create_user(username='other', password='pass123')
        self.client.login(username='other', password='pass123')
        response = self.client.get(reverse('genealogy:tree_detail', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)


class TreeDataAPITest(TestCase):
    """Тесты API для получения данных дерева."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username='treeowner', password='pass123')
        self.tree = Tree.objects.create(name='Тестовое дерево')
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.user, role=CollaboratorRoleEnum.OWNER
        )
        self.person = Person.objects.create(first_name='Иван', last_name='Иванов', tree=self.tree)

    def test_api_requires_login(self) -> None:
        """API требует входа."""
        response = self.client.get(reverse('genealogy:tree_data_api', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 302)

    def test_api_returns_json(self) -> None:
        """API возвращает JSON."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_data_api', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_api_contains_nodes_and_edges(self) -> None:
        """API содержит узлы и рёбра."""
        self.client.login(username='treeowner', password='pass123')
        response = self.client.get(reverse('genealogy:tree_data_api', args=[self.tree.pk]))
        data = response.json()
        self.assertIn('nodes', data)
        self.assertIn('edges', data)
        self.assertEqual(len(data['nodes']), 1)

    def test_api_forbidden_for_other_user(self) -> None:
        """API запрещён для других пользователей."""
        other_user = User.objects.create_user(username='other', password='pass123')
        self.client.login(username='other', password='pass123')
        response = self.client.get(reverse('genealogy:tree_data_api', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)


class PersonCRUDViewsTest(TestCase):
    """Тесты CRUD для персон."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='owner', password='pass123')
        self.editor = User.objects.create_user(username='editor', password='pass123')
        self.viewer = User.objects.create_user(username='viewer', password='pass123')
        self.other_user = User.objects.create_user(username='other', password='pass123')

        self.tree = Tree.objects.create(name='Тестовое дерево')

        TreeCollaborator.objects.create(tree=self.tree, user=self.owner, role=CollaboratorRoleEnum.OWNER)
        TreeCollaborator.objects.create(tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR)
        TreeCollaborator.objects.create(tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER)

        self.person = Person.objects.create(
            first_name='Иван', last_name='Иванов', gender='male', tree=self.tree
        )

    def test_create_requires_login(self) -> None:
        """Создание требует входа."""
        response = self.client.get(reverse('genealogy:person_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_by_owner(self) -> None:
        """Владелец может создавать персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:person_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать персон."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(reverse('genealogy:person_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(reverse('genealogy:person_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_create_person_success(self) -> None:
        """Успешное создание персоны."""
        self.client.login(username='owner', password='pass123')
        data = {
            'first_name': 'Мария', 'last_name': 'Петрова',
            'gender': 'female', 'birth_date': '1995-05-15',
        }
        response = self.client.post(reverse('genealogy:person_create', args=[self.tree.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Person.objects.filter(first_name='Мария', last_name='Петрова', tree=self.tree).exists()
        )

    def test_create_person_duplicate_forbidden(self) -> None:
        """Создание дубликата запрещено."""
        self.client.login(username='owner', password='pass123')
        data = {'first_name': 'Иван', 'last_name': 'Иванов', 'gender': 'male'}
        response = self.client.post(reverse('genealogy:person_create', args=[self.tree.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'уже есть персона')

    def test_update_requires_login(self) -> None:
        """Редактирование требует входа."""
        response = self.client.get(reverse('genealogy:person_update', args=[self.person.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_update_by_owner(self) -> None:
        """Владелец может редактировать персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:person_update', args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update_by_editor(self) -> None:
        """Редактор может редактировать персон."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(reverse('genealogy:person_update', args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_update_by_viewer_forbidden(self) -> None:
        """Читатель не может редактировать персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(reverse('genealogy:person_update', args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_update_success(self) -> None:
        """Успешное обновление персоны."""
        self.client.login(username='owner', password='pass123')
        data = {
            'first_name': 'Иван', 'last_name': 'Иванов',
            'gender': 'male', 'middle_name': 'Иванович',
        }
        response = self.client.post(reverse('genealogy:person_update', args=[self.person.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.middle_name, 'Иванович')

    def test_delete_requires_login(self) -> None:
        """Удаление требует входа."""
        response = self.client.get(reverse('genealogy:person_delete', args=[self.person.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять персон."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:person_delete', args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять персон."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(reverse('genealogy:person_delete', args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление персоны."""
        self.client.login(username='owner', password='pass123')
        person_pk = self.person.pk
        response = self.client.post(reverse('genealogy:person_delete', args=[person_pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Person.objects.filter(pk=person_pk).exists())

    def test_person_detail_requires_login(self) -> None:
        """Карточка персоны требует входа."""
        response = self.client.get(reverse('genealogy:person_detail', args=[self.person.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_person_detail_accessible(self) -> None:
        """Карточка персоны доступна."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:person_detail', args=[self.person.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иванов Иван')

    def test_person_detail_forbidden_for_other_user(self) -> None:
        """Карточка персоны недоступна для чужого пользователя."""
        self.client.login(username='other', password='pass123')
        response = self.client.get(reverse('genealogy:person_detail', args=[self.person.pk]))
        self.assertEqual(response.status_code, 403)


class RelationshipCRUDViewsTest(TestCase):
    """Тесты CRUD для родственных связей."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username='owner', password='pass123')
        self.editor = User.objects.create_user(username='editor', password='pass123')
        self.viewer = User.objects.create_user(username='viewer', password='pass123')

        self.tree = Tree.objects.create(name='Тестовое дерево')

        TreeCollaborator.objects.create(tree=self.tree, user=self.owner, role=CollaboratorRoleEnum.OWNER)
        TreeCollaborator.objects.create(tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR)
        TreeCollaborator.objects.create(tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER)

        self.father = Person.objects.create(first_name='Пётр', last_name='Иванов', gender='male', tree=self.tree)
        self.son = Person.objects.create(first_name='Иван', last_name='Иванов', gender='male', tree=self.tree)

        self.relationship = Relationship.objects.create(
            from_person=self.father, to_person=self.son,
            relationship_type='biological_parent'
        )

    def test_create_requires_login(self) -> None:
        """Создание связи требует входа."""
        response = self.client.get(reverse('genealogy:relationship_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_by_owner(self) -> None:
        """Владелец может создавать связи."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:relationship_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать связи."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(reverse('genealogy:relationship_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать связи."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(reverse('genealogy:relationship_create', args=[self.tree.pk]))
        self.assertEqual(response.status_code, 403)

    def test_create_relationship_success(self) -> None:
        """Успешное создание связи."""
        self.client.login(username='owner', password='pass123')
        mother = Person.objects.create(first_name='Мария', last_name='Иванова', gender='female', tree=self.tree)
        data = {
            'from_person': mother.pk, 'to_person': self.son.pk,
            'relationship_type': 'biological_parent',
        }
        response = self.client.post(reverse('genealogy:relationship_create', args=[self.tree.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Relationship.objects.filter(
                from_person=mother, to_person=self.son,
                relationship_type='biological_parent'
            ).exists()
        )

    def test_delete_requires_login(self) -> None:
        """Удаление связи требует входа."""
        response = self.client.get(reverse('genealogy:relationship_delete', args=[self.relationship.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять связи."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(reverse('genealogy:relationship_delete', args=[self.relationship.pk]))
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять связи."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(reverse('genealogy:relationship_delete', args=[self.relationship.pk]))
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление связи."""
        self.client.login(username='owner', password='pass123')
        relationship_pk = self.relationship.pk
        response = self.client.post(reverse('genealogy:relationship_delete', args=[relationship_pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Relationship.objects.filter(pk=relationship_pk).exists())


class WelcomeAndRegisterViewsTest(TestCase):
    """Тесты страницы приветствия и регистрации."""

    def test_welcome_page_accessible_anonymously(self) -> None:
        """Страница приветствия доступна анонимному пользователю."""
        response = self.client.get(reverse('genealogy:welcome'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Исток')
        self.assertContains(response, 'Создать аккаунт')

    def test_welcome_redirects_authenticated_user(self) -> None:
        """Авторизованный пользователь перенаправляется на список деревьев."""
        User.objects.create_user(username='testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        response = self.client.get(reverse('genealogy:welcome'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/trees/', response.url)

    def test_register_page_accessible(self) -> None:
        """Страница регистрации доступна анонимному пользователю."""
        response = self.client.get(reverse('genealogy:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Создать аккаунт')

    def test_register_redirects_authenticated_user(self) -> None:
        """Авторизованный пользователь перенаправляется на список деревьев."""
        User.objects.create_user(username='testuser', password='pass123')
        self.client.login(username='testuser', password='pass123')
        response = self.client.get(reverse('genealogy:register'))
        self.assertEqual(response.status_code, 302)

    def test_register_creates_user(self) -> None:
        """Регистрация создаёт нового пользователя."""
        initial_count = User.objects.count()
        response = self.client.post(
            reverse('genealogy:register'),
            {'username': 'newuser', 'password1': 'ComplexPass123!', 'password2': 'ComplexPass123!'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.count(), initial_count + 1)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_register_creates_user_profile(self) -> None:
        """При регистрации автоматически создаётся профиль пользователя."""
        self.client.post(
            reverse('genealogy:register'),
            {'username': 'newuser2', 'password1': 'ComplexPass123!', 'password2': 'ComplexPass123!'}
        )
        new_user = User.objects.get(username='newuser2')
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertTrue(hasattr(new_user, 'privacy_settings'))

    def test_register_auto_login(self) -> None:
        """После регистрации пользователь автоматически входит в систему."""
        self.client.post(
            reverse('genealogy:register'),
            {'username': 'newuser3', 'password1': 'ComplexPass123!', 'password2': 'ComplexPass123!'}
        )
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertEqual(response.status_code, 200)

    def test_register_invalid_password(self) -> None:
        """Регистрация с несовпадающими паролями не проходит."""
        initial_count = User.objects.count()
        response = self.client.post(
            reverse('genealogy:register'),
            {'username': 'newuser4', 'password1': 'ComplexPass123!', 'password2': 'DifferentPass456!'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), initial_count)

    def test_tree_list_requires_login(self) -> None:
        """Список деревьев требует входа."""
        response = self.client.get(reverse('genealogy:tree_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_login_page_has_register_link(self) -> None:
        """На странице входа есть ссылка на регистрацию."""
        response = self.client.get(reverse('genealogy:login'))
        self.assertContains(response, 'Зарегистрироваться')


class LifeEventCRUDViewsTest(TestCase):
    """Тесты CRUD для событий жизни."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.owner = User.objects.create_user(username='owner', password='pass123')
        self.editor = User.objects.create_user(username='editor', password='pass123')
        self.viewer = User.objects.create_user(username='viewer', password='pass123')

        self.tree = Tree.objects.create(name='Тестовое дерево')

        TreeCollaborator.objects.create(
            tree=self.tree, user=self.owner, role=CollaboratorRoleEnum.OWNER
        )
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.editor, role=CollaboratorRoleEnum.EDITOR
        )
        TreeCollaborator.objects.create(
            tree=self.tree, user=self.viewer, role=CollaboratorRoleEnum.VIEWER
        )

        self.person = Person.objects.create(
            first_name='Иван', last_name='Иванов',
            gender='male', tree=self.tree
        )

        self.event = LifeEvent.objects.create(
            person=self.person,
            event_type='birth',
            event_date='1990-01-01'
        )

    def test_create_requires_login(self) -> None:
        """Создание события требует входа."""
        response = self.client.get(
            reverse('genealogy:life_event_create', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_create_by_owner(self) -> None:
        """Владелец может создавать события."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_create', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_editor(self) -> None:
        """Редактор может создавать события."""
        self.client.login(username='editor', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_create', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_create_by_viewer_forbidden(self) -> None:
        """Читатель не может создавать события."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_create', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_create_event_success(self) -> None:
        """Успешное создание события."""
        self.client.login(username='owner', password='pass123')
        data = {
            'event_type': 'education',
            'event_date': '2010-09-01',
            'location': 'МГУ',
            'description': 'Бакалавриат',
        }
        response = self.client.post(
            reverse('genealogy:life_event_create', args=[self.person.pk]),
            data
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LifeEvent.objects.filter(
                person=self.person,
                event_type='education',
                location='МГУ'
            ).exists()
        )

    def test_update_requires_login(self) -> None:
        """Редактирование события требует входа."""
        response = self.client.get(
            reverse('genealogy:life_event_update', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_update_by_owner(self) -> None:
        """Владелец может редактировать события."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_update', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_update_by_viewer_forbidden(self) -> None:
        """Читатель не может редактировать события."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_update', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_update_success(self) -> None:
        """Успешное обновление события."""
        self.client.login(username='owner', password='pass123')
        data = {
            'event_type': 'birth',
            'event_date': '1990-01-01',
            'location': 'Москва',
        }
        response = self.client.post(
            reverse('genealogy:life_event_update', args=[self.event.pk]),
            data
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.location, 'Москва')

    def test_delete_requires_login(self) -> None:
        """Удаление события требует входа."""
        response = self.client.get(
            reverse('genealogy:life_event_delete', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_delete_by_owner(self) -> None:
        """Владелец может удалять события."""
        self.client.login(username='owner', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_delete', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_delete_by_viewer_forbidden(self) -> None:
        """Читатель не может удалять события."""
        self.client.login(username='viewer', password='pass123')
        response = self.client.get(
            reverse('genealogy:life_event_delete', args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_delete_success(self) -> None:
        """Успешное удаление события."""
        self.client.login(username='owner', password='pass123')
        event_pk = self.event.pk
        response = self.client.post(
            reverse('genealogy:life_event_delete', args=[event_pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LifeEvent.objects.filter(pk=event_pk).exists())