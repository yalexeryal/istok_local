"""
Тесты для Admin-панели Django.

Проверяют:
- Доступность админки для разных пользователей
- Корректность отображения моделей
- Inline-редактирование
- Кастомные действия
- Автоматическое создание UserProfile через сигналы
"""
from datetime import date

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.urls import reverse

from genealogy.admin import (
    CustomUserAdmin,
    LifeEventAdmin,
    PersonAdmin,
    TreeAdmin,
    UserProfileAdmin,
)
from genealogy.models import (
    CollaboratorRoleEnum,
    GenderEnum,
    LifeEvent,
    Person,
    PersonStatusEnum,
    Tree,
    TreeCollaborator,
    UserProfile,
    UserTierEnum,
)


class MockRequest:
    """Мок-объект запроса для тестов."""
    pass


class AdminAccessTest(TestCase):
    """Тесты доступа к админке."""

    def setUp(self) -> None:
        """Создание тестовых пользователей."""
        # Суперпользователь (полный доступ)
        self.superuser = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='adminpass123'
        )

        # Обычный пользователь (нет доступа к админке)
        self.regular_user = User.objects.create_user(
            username='user',
            email='user@example.com',
            password='userpass123'
        )

        # Staff пользователь (есть доступ к админке, но без прав)
        self.staff_user = User.objects.create_user(
            username='staff',
            email='staff@example.com',
            password='staffpass123',
            is_staff=True
        )

    def test_superuser_can_access_admin(self) -> None:
        """Суперпользователь может войти в админку."""
        self.client.login(username='admin', password='adminpass123')
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_access_admin(self) -> None:
        """Обычный пользователь не может войти в админку."""
        self.client.login(username='user', password='userpass123')
        response = self.client.get(reverse('admin:index'))
        # Должен быть редирект на страницу входа
        self.assertEqual(response.status_code, 302)

    def test_anonymous_user_redirected_to_login(self) -> None:
        """Анонимный пользователь перенаправляется на страницу входа."""
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        # Django admin использует свой собственный URL для входа
        self.assertIn('/admin/login/', response.url)


class TreeAdminTest(TestCase):
    """Тесты админки для модели Tree."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')

        self.user = User.objects.create_user(
            username='treeowner',
            password='pass123'
        )
        self.tree = Tree.objects.create(
            name='Тестовое дерево',
            description='Описание'
        )
        TreeCollaborator.objects.create(
            tree=self.tree,
            user=self.user,
            role=CollaboratorRoleEnum.OWNER
        )

    def test_tree_list_view(self) -> None:
        """Тест списка деревьев."""
        response = self.client.get(reverse('admin:genealogy_tree_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Тестовое дерево')

    def test_tree_add_view(self) -> None:
        """Тест страницы добавления дерева."""
        response = self.client.get(reverse('admin:genealogy_tree_add'))
        self.assertEqual(response.status_code, 200)

    def test_tree_change_view(self) -> None:
        """Тест страницы редактирования дерева."""
        response = self.client.get(
            reverse('admin:genealogy_tree_change', args=[self.tree.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Тестовое дерево')

    def test_tree_admin_get_owner_display(self) -> None:
        """Тест метода get_owner_display."""
        admin_instance = TreeAdmin(Tree, AdminSite())
        owner_display = admin_instance.get_owner_display(self.tree)
        self.assertEqual(owner_display, 'treeowner')

    def test_tree_admin_persons_count(self) -> None:
        """Тест метода persons_count."""
        admin_instance = TreeAdmin(Tree, AdminSite())

        # Пустое дерево
        self.assertEqual(admin_instance.persons_count(self.tree), 0)

        # Добавляем персону
        Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            tree=self.tree
        )
        self.assertEqual(admin_instance.persons_count(self.tree), 1)


class PersonAdminTest(TestCase):
    """Тесты админки для модели Person."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')

        self.tree = Tree.objects.create(name='Тестовое дерево')
        self.person = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            birth_date=date(1990, 1, 1),
            tree=self.tree
        )

    def test_person_list_view(self) -> None:
        """Тест списка персон."""
        response = self.client.get(reverse('admin:genealogy_person_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иванов Иван')

    def test_person_add_view(self) -> None:
        """Тест страницы добавления персоны."""
        response = self.client.get(reverse('admin:genealogy_person_add'))
        self.assertEqual(response.status_code, 200)

    def test_person_change_view(self) -> None:
        """Тест страницы редактирования персоны."""
        response = self.client.get(
            reverse('admin:genealogy_person_change', args=[self.person.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иван')

    def test_person_admin_get_age_display_alive(self) -> None:
        """Тест отображения возраста для живого человека."""
        admin_instance = PersonAdmin(Person, AdminSite())
        age_display = admin_instance.get_age_display(self.person)
        self.assertIn('лет', age_display)

    def test_person_admin_get_age_display_dead(self) -> None:
        """Тест отображения возраста для умершего человека."""
        self.person.death_date = date(2020, 1, 1)
        self.person.save()

        admin_instance = PersonAdmin(Person, AdminSite())
        age_display = admin_instance.get_age_display(self.person)
        self.assertIn('†', age_display)

    def test_person_admin_get_age_display_unknown(self) -> None:
        """Тест отображения возраста при неизвестной дате."""
        self.person.birth_date = None
        self.person.save()

        admin_instance = PersonAdmin(Person, AdminSite())
        age_display = admin_instance.get_age_display(self.person)
        self.assertEqual(age_display, '—')

    def test_mark_as_published_action(self) -> None:
        """Тест массового действия 'Опубликовать'."""
        self.assertEqual(self.person.status, PersonStatusEnum.SANDBOX)

        # Имитируем запрос к действию
        request = RequestFactory().post('/')
        request.user = self.superuser
        request._messages = MockMessages()  # Мок для сообщений

        admin_instance = PersonAdmin(Person, AdminSite())
        admin_instance.mark_as_published(request, Person.objects.all())

        self.person.refresh_from_db()
        self.assertEqual(self.person.status, PersonStatusEnum.PUBLISHED)

    def test_person_search(self) -> None:
        """Тест поиска персон."""
        response = self.client.get(
            reverse('admin:genealogy_person_changelist') + '?q=Иванов'
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Иванов')


class MockMessages:
    """Мок для сообщений Django."""

    def add(self, *args, **kwargs) -> None:
        """Ничего не делаем."""
        pass


class UserProfileAdminTest(TestCase):
    """Тесты админки для модели UserProfile."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')

        self.user = User.objects.create_user(
            username='testuser',
            password='pass123'
        )
        # Используем get_or_create, так как сигнал уже мог создать профиль
        self.profile, _ = UserProfile.objects.get_or_create(
            user=self.user,
            defaults={'tier': UserTierEnum.FREE}
        )

    def test_profile_list_view(self) -> None:
        """Тест списка профилей."""
        response = self.client.get(reverse('admin:genealogy_userprofile_changelist'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'testuser')

    def test_profile_change_view(self) -> None:
        """Тест страницы редактирования профиля."""
        response = self.client.get(
            reverse('admin:genealogy_userprofile_change', args=[self.profile.pk])
        )
        self.assertEqual(response.status_code, 200)


class UserAdminIntegrationTest(TestCase):
    """
    Тесты интеграции UserProfile в UserAdmin.

    Проверяем наше поведение (сигнал создаёт профиль),
    а не поведение Django (двухэтапный процесс UserAdmin).
    """

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='adminpass123'
        )
        self.client.login(username='admin', password='adminpass123')

    def test_user_change_view_has_profile_inline(self) -> None:
        """
        Тест: при редактировании пользователя виден inline профиля.
        """
        response = self.client.get(
            reverse('admin:auth_user_change', args=[self.superuser.pk])
        )
        self.assertEqual(response.status_code, 200)
        # Проверяем, что на странице есть упоминание профиля
        self.assertContains(response, 'Профиль istok_local')

    def test_signal_creates_profile_on_user_creation(self) -> None:
        """
        Тест: при создании пользователя автоматически создается профиль.

        Проверяем работу Django signal, который создает UserProfile
        при создании нового User. Это работает не только в админке,
        но и при любом создании пользователя через ORM.
        """
        initial_count = UserProfile.objects.count()

        # Создаем пользователя через ORM
        new_user = User.objects.create_user(
            username='signaltest',
            password='pass123'
        )

        # Проверяем, что профиль создан сигналом
        self.assertEqual(UserProfile.objects.count(), initial_count + 1)
        self.assertTrue(hasattr(new_user, 'profile'))
        self.assertEqual(new_user.profile.tier, UserTierEnum.FREE)

    def test_signal_creates_profile_on_superuser_creation(self) -> None:
        """
        Тест: при создании суперпользователя также создается профиль.
        """
        initial_count = UserProfile.objects.count()

        # Создаем суперпользователя
        new_superuser = User.objects.create_superuser(
            username='newsuperuser',
            email='super@example.com',
            password='superpass123'
        )

        # Проверяем, что профиль создан
        self.assertEqual(UserProfile.objects.count(), initial_count + 1)
        self.assertTrue(hasattr(new_superuser, 'profile'))

    def test_profile_default_tier_is_free(self) -> None:
        """
        Тест: профиль по умолчанию имеет тариф FREE.
        """
        new_user = User.objects.create_user(
            username='freetieruser',
            password='pass123'
        )
        self.assertEqual(new_user.profile.tier, UserTierEnum.FREE)
        self.assertEqual(new_user.profile.devices_count, 1)

    def test_profile_not_created_twice(self) -> None:
        """
        Тест: сигнал не создает дубликат профиля при повторном сохранении.
        """
        new_user = User.objects.create_user(
            username='nosignalduplicate',
            password='pass123'
        )
        profile_id = new_user.profile.pk

        # Сохраняем пользователя еще раз
        new_user.first_name = 'Обновленное имя'
        new_user.save()

        # Проверяем, что профиль тот же самый (не создан дубликат)
        new_user.refresh_from_db()
        self.assertEqual(new_user.profile.pk, profile_id)
        self.assertEqual(UserProfile.objects.filter(user=new_user).count(), 1)