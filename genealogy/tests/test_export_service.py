"""
Тесты для сервиса экспорта.

Проверяют:
- Создание задач экспорта
- Полную выгрузку (FULL)
- Выгрузку для родственника (RELATIVE)
- Публичную выгрузку (PUBLIC)
- Применение настроек приватности
"""
import json
import zipfile
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase

from genealogy.models import (
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ExportStatusEnum,
    ExportTask,
    ExportTypeEnum,
    GenderEnum,
    Person,
    PrivacySettings,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)
from genealogy.services.export_service import ExportService


class ExportServiceTest(TestCase):
    """Тесты сервиса экспорта."""

    def setUp(self) -> None:
        """Создание тестовых данных."""
        self.user = User.objects.create_user(
            username='testuser',
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

        # Создаём персон
        self.father = Person.objects.create(
            first_name='Пётр',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            birth_date='1960-01-01',
            tree=self.tree,
            notes='Заметки об отце'
        )
        self.mother = Person.objects.create(
            first_name='Мария',
            last_name='Иванова',
            gender=GenderEnum.FEMALE,
            birth_date='1965-05-15',
            tree=self.tree
        )
        self.son = Person.objects.create(
            first_name='Иван',
            last_name='Иванов',
            gender=GenderEnum.MALE,
            birth_date='1990-03-20',
            tree=self.tree
        )

        # Создаём связи
        Relationship.objects.create(
            from_person=self.father,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        Relationship.objects.create(
            from_person=self.mother,
            to_person=self.son,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT
        )
        Relationship.objects.create(
            from_person=self.father,
            to_person=self.mother,
            relationship_type=RelationshipTypeEnum.SPOUSE
        )

        self.service = ExportService()

    def test_create_export_task(self) -> None:
        """Тест создания задачи экспорта."""
        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.FULL,
            export_format=ExportFormatEnum.JSON_ZIP
        )

        self.assertEqual(task.user, self.user)
        self.assertEqual(task.tree, self.tree)
        self.assertEqual(task.export_type, ExportTypeEnum.FULL)
        self.assertEqual(task.status, ExportStatusEnum.PENDING)

    def test_export_full(self) -> None:
        """Тест полной выгрузки."""
        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.FULL
        )

        self.service.execute_export(task)

        # Проверяем статус
        self.assertEqual(task.status, ExportStatusEnum.COMPLETED)
        self.assertIsNotNone(task.file)
        self.assertEqual(task.person_count, 3)

        # Проверяем содержимое ZIP
        with zipfile.ZipFile(BytesIO(task.file.read()), 'r') as zip_file:
            # Проверяем наличие файлов
            self.assertIn('manifest.json', zip_file.namelist())
            self.assertIn('tree.json', zip_file.namelist())
            self.assertIn('persons.json', zip_file.namelist())
            self.assertIn('relationships.json', zip_file.namelist())
            self.assertIn('life_events.json', zip_file.namelist())
            self.assertIn('collaborators.json', zip_file.namelist())

            # Проверяем manifest
            manifest = json.loads(zip_file.read('manifest.json'))
            self.assertEqual(manifest['export_type'], ExportTypeEnum.FULL)
            self.assertEqual(manifest['person_count'], 3)

            # Проверяем persons
            persons = json.loads(zip_file.read('persons.json'))
            self.assertEqual(len(persons), 3)

            # Проверяем, что все данные на месте
            father_data = next(p for p in persons if p['first_name'] == 'Пётр')
            self.assertEqual(father_data['notes'], 'Заметки об отце')
            self.assertEqual(father_data['birth_date'], '1960-01-01')

            # Проверяем relationships
            relationships = json.loads(zip_file.read('relationships.json'))
            self.assertEqual(len(relationships), 3)

    def test_export_relative(self) -> None:
        """Тест выгрузки для родственника."""
        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.RELATIVE,
            target_person=self.son
        )

        self.service.execute_export(task)

        # Проверяем статус
        self.assertEqual(task.status, ExportStatusEnum.COMPLETED)
        self.assertEqual(task.person_count, 3)  # Все три персоны связаны

        # Проверяем содержимое ZIP
        with zipfile.ZipFile(BytesIO(task.file.read()), 'r') as zip_file:
            manifest = json.loads(zip_file.read('manifest.json'))
            self.assertEqual(manifest['export_type'], ExportTypeEnum.RELATIVE)
            self.assertEqual(manifest['target_person'], 'Иванов Иван')

    def test_export_public(self) -> None:
        """Тест публичной выгрузки."""
        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.PUBLIC
        )

        self.service.execute_export(task)

        # Проверяем статус
        self.assertEqual(task.status, ExportStatusEnum.COMPLETED)
        self.assertEqual(task.person_count, 3)

        # Проверяем содержимое ZIP
        with zipfile.ZipFile(BytesIO(task.file.read()), 'r') as zip_file:
            # Проверяем наличие файлов
            self.assertIn('manifest.json', zip_file.namelist())
            self.assertIn('persons.json', zip_file.namelist())
            self.assertIn('relationships.json', zip_file.namelist())

            # НЕ должно быть life_events и collaborators
            self.assertNotIn('life_events.json', zip_file.namelist())
            self.assertNotIn('collaborators.json', zip_file.namelist())

            # Проверяем persons (урезанные)
            persons = json.loads(zip_file.read('persons.json'))
            father_data = next(p for p in persons if p['first_name'] == 'Пётр')

            # В публичной версии только год, нет заметок
            self.assertEqual(father_data['birth_year'], 1960)
            self.assertNotIn('notes', father_data)
            self.assertNotIn('birth_date', father_data)

    def test_export_with_privacy_settings(self) -> None:
        """
        Тест выгрузки с настройками приватности.

        full_data_min_degree = 0 означает, что НИКТО не получает полные данные.
        Все персоны будут урезаны согласно настройкам приватности.
        """
        # Настраиваем приватность
        privacy = self.user.privacy_settings
        privacy.hide_notes = True
        privacy.full_data_min_degree = 0  # Никому не показывать полные данные
        privacy.save()

        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.RELATIVE,
            target_person=self.son
        )

        self.service.execute_export(task)

        # Проверяем содержимое ZIP
        with zipfile.ZipFile(BytesIO(task.file.read()), 'r') as zip_file:
            persons = json.loads(zip_file.read('persons.json'))
            father_data = next(p for p in persons if p['first_name'] == 'Пётр')

            # Заметки должны быть скрыты
            self.assertIsNone(father_data['notes'])

    def test_export_relative_close_relatives_get_full_data(self) -> None:
        """
        Тест: близкие родственники (степень <= full_data_min_degree)
        получают полные данные.

        full_data_min_degree = 1 означает, что родители/дети (степень 1)
        получают полные данные, а более дальние — урезанные.
        """
        # Настраиваем приватность
        privacy = self.user.privacy_settings
        privacy.hide_notes = True
        privacy.full_data_min_degree = 1  # Полные данные для степени <= 1
        privacy.save()

        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.RELATIVE,
            target_person=self.son
        )

        self.service.execute_export(task)

        # Проверяем содержимое ZIP
        with zipfile.ZipFile(BytesIO(task.file.read()), 'r') as zip_file:
            persons = json.loads(zip_file.read('persons.json'))
            father_data = next(p for p in persons if p['first_name'] == 'Пётр')

            # Отец имеет степень родства 1 (родитель целевой персоны)
            # 1 <= 1 = True, поэтому полные данные, включая заметки
            self.assertEqual(father_data['notes'], 'Заметки об отце')

    def test_export_requires_target_person_for_relative(self) -> None:
        """Тест: для RELATIVE экспорта нужна целевая персона."""
        task = self.service.create_export_task(
            user=self.user,
            tree=self.tree,
            export_type=ExportTypeEnum.RELATIVE
            # Без target_person
        )

        with self.assertRaises(ValueError):
            self.service.execute_export(task)

        self.assertEqual(task.status, ExportStatusEnum.FAILED)
        self.assertIsNotNone(task.error_message)

    def test_export_task_error_handling(self) -> None:
        """Тест обработки ошибок при экспорте."""
        # Создаём задачу с несуществующим типом
        task = ExportTask.objects.create(
            user=self.user,
            tree=self.tree,
            export_type='invalid_type',
            status=ExportStatusEnum.PENDING
        )

        with self.assertRaises(ValueError):
            self.service.execute_export(task)

        task.refresh_from_db()
        self.assertEqual(task.status, ExportStatusEnum.FAILED)
        self.assertIsNotNone(task.error_message)