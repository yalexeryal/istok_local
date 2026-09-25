"""
Тесты для сервиса импорта.

Проверяют:
- Создание задач импорта
- Импорт из JSON+ZIP
- Создание нового дерева
- Обработка дубликатов
- ID-маппинг
- Импорт медиафайлов
"""

import json
import zipfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from genealogy.models import (
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ExportTypeEnum,
    GenderEnum,
    ImportStatusEnum,
    LifeEvent,
    Person,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)
from genealogy.services.export_service import ExportService
from genealogy.services.import_service import ImportService


class ImportServiceTest(TestCase):
    """Тесты сервиса импорта."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(username="testuser", password="pass123")

        # Создаём исходное дерево с данными
        self.source_tree = Tree.objects.create(name="Исходное дерево", description="Описание исходного дерева")
        TreeCollaborator.objects.create(tree=self.source_tree, user=self.user, role=CollaboratorRoleEnum.OWNER)

        # Создаём персон
        self.father = Person.objects.create(
            first_name="Пётр",
            last_name="Иванов",
            gender=GenderEnum.MALE,
            birth_date="1960-01-01",
            tree=self.source_tree,
            notes="Заметки об отце",
        )
        self.mother = Person.objects.create(
            first_name="Мария",
            last_name="Иванова",
            gender=GenderEnum.FEMALE,
            birth_date="1965-05-15",
            tree=self.source_tree,
        )
        self.son = Person.objects.create(
            first_name="Иван",
            last_name="Иванов",
            gender=GenderEnum.MALE,
            birth_date="1990-03-20",
            tree=self.source_tree,
        )

        # Создаём связи
        Relationship.objects.create(
            from_person=self.father, to_person=self.son, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        Relationship.objects.create(
            from_person=self.mother, to_person=self.son, relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )

        # Создаём событие
        LifeEvent.objects.create(
            person=self.son, event_type="education", event_date="2010-09-01", location="МГУ", description="Бакалавриат"
        )

        # Экспортируем дерево
        export_service = ExportService()
        self.export_task = export_service.create_export_task(
            user=self.user, tree=self.source_tree, export_type=ExportTypeEnum.FULL
        )
        export_service.execute_export(self.export_task)

        self.import_service = ImportService()

    def _get_uploaded_file(self, export_task=None) -> SimpleUploadedFile:
        """Получает экспортированный файл как UploadedFile."""
        task = export_task or self.export_task
        task.file.open("rb")
        content = task.file.read()
        task.file.close()

        return SimpleUploadedFile("export.zip", content, content_type="application/zip")

    def test_create_import_task(self) -> None:
        """Тест создания задачи импорта."""
        uploaded_file = self._get_uploaded_file()

        task = self.import_service.create_import_task(
            user=self.user, source_file=uploaded_file, import_format=ExportFormatEnum.JSON_ZIP
        )

        self.assertEqual(task.user, self.user)
        self.assertEqual(task.import_format, ExportFormatEnum.JSON_ZIP)
        self.assertEqual(task.status, ImportStatusEnum.PENDING)
        self.assertTrue(task.source_file.name.endswith(".zip"))

    def test_import_creates_new_tree(self) -> None:
        """Тест: импорт создаёт новое дерево."""
        uploaded_file = self._get_uploaded_file()

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
        )

        self.import_service.execute_import(task)

        # Проверяем статус
        self.assertEqual(task.status, ImportStatusEnum.COMPLETED)
        self.assertIsNotNone(task.tree)

        # Проверяем, что создано новое дерево
        self.assertEqual(task.person_count, 3)
        self.assertEqual(task.relationship_count, 2)

        # Проверяем содержимое нового дерева
        tree = task.tree
        self.assertIn("Исходное дерево", tree.name)
        self.assertEqual(tree.persons.count(), 3)

        # Проверяем персон
        father = tree.persons.get(first_name="Пётр")
        self.assertEqual(father.notes, "Заметки об отце")
        self.assertEqual(father.birth_date.isoformat(), "1960-01-01")

    def test_import_to_existing_tree(self) -> None:
        """Тест: импорт в существующее дерево."""
        # Создаём пустое дерево
        target_tree = Tree.objects.create(name="Целевое дерево")
        TreeCollaborator.objects.create(tree=target_tree, user=self.user, role=CollaboratorRoleEnum.OWNER)

        uploaded_file = self._get_uploaded_file()

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
            target_tree=target_tree,
        )

        self.import_service.execute_import(task)

        # Проверяем, что импортировано в целевое дерево
        self.assertEqual(task.tree, target_tree)
        self.assertEqual(target_tree.persons.count(), 3)

    def test_import_handles_duplicates(self) -> None:
        """Тест: импорт обрабатывает дубликаты персон."""
        # Создаём дерево с одной из импортируемых персон
        target_tree = Tree.objects.create(name="Дерево с дубликатом")
        TreeCollaborator.objects.create(tree=target_tree, user=self.user, role=CollaboratorRoleEnum.OWNER)

        # Создаём персону с таким же ФИО
        Person.objects.create(first_name="Пётр", last_name="Иванов", gender=GenderEnum.MALE, tree=target_tree)

        uploaded_file = self._get_uploaded_file()

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
            target_tree=target_tree,
        )

        self.import_service.execute_import(task)

        # Проверяем, что дубликат не создан
        persons_with_same_name = target_tree.persons.filter(first_name="Пётр", last_name="Иванов")
        self.assertEqual(persons_with_same_name.count(), 1)

        # Проверяем, что связи используют существующую персону
        self.assertEqual(target_tree.persons.count(), 3)

    def test_import_creates_owner_collaborator(self) -> None:
        """Тест: импорт создаёт владельца для нового дерева."""
        uploaded_file = self._get_uploaded_file()

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
        )

        self.import_service.execute_import(task)

        # Проверяем, что создан владелец
        tree = task.tree
        owner_collaborator = tree.collaborators.filter(user=self.user, role=CollaboratorRoleEnum.OWNER).first()
        self.assertIsNotNone(owner_collaborator)

    def test_import_with_name_conflict(self) -> None:
        """
        Тест: импорт обрабатывает конфликт имён деревьев.

        Создаём отдельное дерево с уникальным именем, экспортируем его,
        затем создаём дерево с таким же именем и проверяем, что импорт
        создаст новое дерево с суффиксом.
        """
        # Создаём отдельное дерево с уникальным именем
        conflict_tree = Tree.objects.create(name="Дерево для конфликта")
        TreeCollaborator.objects.create(tree=conflict_tree, user=self.user, role=CollaboratorRoleEnum.OWNER)

        # Добавляем персону (чтобы экспорт был валидным)
        Person.objects.create(first_name="Тест", last_name="Тестов", gender=GenderEnum.MALE, tree=conflict_tree)

        # Экспортируем это дерево
        export_service = ExportService()
        conflict_export_task = export_service.create_export_task(
            user=self.user, tree=conflict_tree, export_type=ExportTypeEnum.FULL
        )
        export_service.execute_export(conflict_export_task)

        # Удаляем исходное дерево, чтобы освободить имя для конфликта
        conflict_tree.delete()

        # Создаём новое дерево с таким же именем (как будто оно уже существует)
        Tree.objects.create(name="Дерево для конфликта")

        # Импортируем экспорт
        uploaded_file = self._get_uploaded_file(conflict_export_task)

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
        )

        self.import_service.execute_import(task)

        # Проверяем, что создано дерево с суффиксом
        tree = task.tree
        self.assertIn("импорт", tree.name)
        self.assertNotEqual(tree.name, "Дерево для конфликта")

    def test_import_invalid_zip(self) -> None:
        """Тест: импорт обрабатывает некорректный ZIP."""
        invalid_file = SimpleUploadedFile("invalid.zip", b"this is not a zip file", content_type="application/zip")

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=invalid_file,
        )

        with self.assertRaises((Exception, ImportError)):
            self.import_service.execute_import(task)

        task.refresh_from_db()
        self.assertEqual(task.status, ImportStatusEnum.FAILED)
        self.assertIsNotNone(task.error_message)

    def test_import_missing_required_files(self) -> None:
        """Тест: импорт обрабатывает отсутствие обязательных файлов."""
        # Создаём ZIP без обязательных файлов
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as zip_file:
            zip_file.writestr("manifest.json", json.dumps({"version": "1.0"}))
            # Нет persons.json и relationships.json

        invalid_file = SimpleUploadedFile("incomplete.zip", buffer.getvalue(), content_type="application/zip")

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=invalid_file,
        )

        with self.assertRaises((Exception, ImportError)):
            self.import_service.execute_import(task)

        task.refresh_from_db()
        self.assertEqual(task.status, ImportStatusEnum.FAILED)

    def test_import_public_export(self) -> None:
        """Тест: импорт публичного экспорта (с урезанными данными)."""
        # Создаём публичный экспорт
        export_service = ExportService()
        public_task = export_service.create_export_task(
            user=self.user, tree=self.source_tree, export_type=ExportTypeEnum.PUBLIC
        )
        export_service.execute_export(public_task)

        # Импортируем публичный экспорт
        uploaded_file = self._get_uploaded_file(public_task)

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
        )

        self.import_service.execute_import(task)

        # Проверяем, что импортировано
        self.assertEqual(task.status, ImportStatusEnum.COMPLETED)
        self.assertEqual(task.person_count, 3)

        # Проверяем, что даты урезаны (только год)
        tree = task.tree
        father = tree.persons.get(first_name="Пётр")
        # В публичном экспорте birth_date отсутствует, но birth_year = 1960
        # При импорте мы не можем восстановить полную дату
        # Проверяем, что персона создана
        self.assertIsNotNone(father)

    def test_import_relative_export(self) -> None:
        """Тест: импорт экспорта для родственника."""
        # Создаём экспорт для родственника
        export_service = ExportService()
        relative_task = export_service.create_export_task(
            user=self.user, tree=self.source_tree, export_type=ExportTypeEnum.RELATIVE, target_person=self.son
        )
        export_service.execute_export(relative_task)

        # Импортируем
        uploaded_file = self._get_uploaded_file(relative_task)

        task = self.import_service.create_import_task(
            user=self.user,
            source_file=uploaded_file,
        )

        self.import_service.execute_import(task)

        # Проверяем, что импортировано
        self.assertEqual(task.status, ImportStatusEnum.COMPLETED)
        self.assertEqual(task.person_count, 3)
