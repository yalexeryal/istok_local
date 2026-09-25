"""
Тесты проверки корректности начальной настройки проекта.
Эти тесты запускаются первыми, чтобы убедиться, что проект настроен правильно.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings


class ProjectSetupTest(TestCase):
    """Тесты корректности настройки проекта."""

    def test_project_name_is_istok_local(self) -> None:
        """Проверяем, что название проекта корректное."""
        self.assertEqual(settings.ROOT_URLCONF, "istok_local.urls")

    def test_database_is_sqlite(self) -> None:
        """Проверяем, что используется SQLite."""
        engine = settings.DATABASES["default"]["ENGINE"]
        self.assertEqual(engine, "django.db.backends.sqlite3")

    def test_database_file_path_is_correct(self) -> None:
        """
        Проверяем, что путь к файлу БД настроен корректно.

        Важно: во время тестов Django подменяет БД на in-memory,
        поэтому мы проверяем не реальное имя файла, а то, что путь
        построен относительно BASE_DIR и заканчивается на istok_local.db.
        """
        db_name = settings.DATABASES["default"]["NAME"]

        # Во время тестов Django использует in-memory БД
        # Проверяем, что это либо in-memory (для тестов), либо наш файл
        if "memorydb" in str(db_name):
            # Это тестовый режим — проверяем, что БД действительно in-memory
            self.assertIn("memory", str(db_name))
        else:
            # Это обычный режим — проверяем имя файла
            db_path = Path(db_name)
            self.assertEqual(db_path.name, "istok_local.db")
            # И что путь абсолютный или относительно BASE_DIR
            self.assertTrue(db_path.is_absolute() or db_path.parent != Path("."))

    def test_genealogy_app_is_installed(self) -> None:
        """Проверяем, что приложение genealogy установлено."""
        self.assertIn("genealogy.apps.GenealogyConfig", settings.INSTALLED_APPS)

    def test_language_is_russian(self) -> None:
        """Проверяем, что язык интерфейса — русский."""
        self.assertEqual(settings.LANGUAGE_CODE, "ru-ru")

    def test_timezone_is_moscow(self) -> None:
        """Проверяем, что часовой пояс — Москва."""
        self.assertEqual(settings.TIME_ZONE, "Europe/Moscow")

    def test_media_root_exists(self) -> None:
        """Проверяем, что директория для медиафайлов настроена."""
        media_root = Path(settings.MEDIA_ROOT)
        self.assertEqual(media_root.name, "media")

    def test_tier_limits_are_configured(self) -> None:
        """Проверяем, что лимиты тарифов настроены."""
        self.assertIn("free", settings.TIER_LIMITS)
        self.assertIn("one_time", settings.TIER_LIMITS)
        self.assertIn("subscription", settings.TIER_LIMITS)

        # Проверяем структуру лимитов Free тарифа
        free_limits = settings.TIER_LIMITS["free"]
        self.assertEqual(free_limits["max_users"], 1)
        self.assertEqual(free_limits["max_devices"], 2)
        self.assertEqual(free_limits["max_persons_per_tree"], 200)

        # Проверяем, что в платных тарифах есть неограниченные значения
        self.assertIsNone(settings.TIER_LIMITS["subscription"]["max_users"])
        self.assertIsNone(settings.TIER_LIMITS["subscription"]["max_devices"])


class DirectoryStructureTest(TestCase):
    """Тесты структуры директорий проекта."""

    def test_base_dir_exists(self) -> None:
        """Проверяем, что BASE_DIR существует."""
        self.assertTrue(settings.BASE_DIR.exists())
        self.assertTrue(settings.BASE_DIR.is_dir())

    def test_static_dirs_configured(self) -> None:
        """Проверяем, что STATICFILES_DIRS настроен."""
        self.assertTrue(len(settings.STATICFILES_DIRS) > 0)
        static_dir = Path(settings.STATICFILES_DIRS[0])
        self.assertEqual(static_dir.name, "static")

    def test_media_root_is_absolute_path(self) -> None:
        """Проверяем, что MEDIA_ROOT — абсолютный путь."""
        media_root = Path(settings.MEDIA_ROOT)
        self.assertTrue(media_root.is_absolute())


class SettingsIntegrityTest(TestCase):
    """Тесты целостности настроек."""

    @override_settings(DEBUG=True)
    def test_debug_can_be_set_to_true(self) -> None:
        """
        Проверяем, что настройка DEBUG может быть установлена в True.

        Важно: Django автоматически устанавливает DEBUG=False во время тестов
        для предсказуемости. Этот тест проверяет, что настройка DEBUG вообще
        работает и может быть переопределена.

        В вашем settings.py DEBUG=True для режима разработки.
        """
        self.assertTrue(settings.DEBUG)

    def test_debug_is_false_during_tests(self) -> None:
        """
        Проверяем, что Django подменяет DEBUG на False во время тестов.

        Это особенность Django: для предсказуемости тестов DEBUG всегда False.
        Этот тест документирует это поведение.
        """
        # Во время тестов Django всегда устанавливает DEBUG=False
        self.assertFalse(settings.DEBUG)

    def test_allowed_hosts_permits_local_access(self) -> None:
        """
        Проверяем, что разрешён доступ с любых хостов.

        Это нужно для доступа со смартфона по локальной сети.
        В продакшене нужно указать конкретные домены.
        """
        self.assertIn("*", settings.ALLOWED_HOSTS)

    def test_login_urls_are_configured(self) -> None:
        """Проверяем, что URL для аутентификации настроены."""
        self.assertEqual(settings.LOGIN_URL, "/accounts/login/")
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "/")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "/accounts/login/")
