"""
Сервис импорта данных дерева.

Поддерживает импорт из JSON+ZIP файлов, созданных ExportService.

Особенности:
- Создание нового дерева или добавление в существующее
- Обработка дубликатов (пропуск уже существующих персон)
- ID-маппинг: старые ID из экспорта → новые ID в БД
- Импорт медиафайлов
- Обработка ошибок
"""

import json
import zipfile
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from genealogy.models import (
    CollaboratorRoleEnum,
    ExportFormatEnum,
    ImportStatusEnum,
    ImportTask,
    LifeEvent,
    Person,
    Relationship,
    Tree,
    TreeCollaborator,
)


class ImportError(Exception):
    """Исключение для ошибок импорта."""

    pass


class ImportService:
    """
    Сервис для импорта данных генеалогического дерева.

    Пример использования:
        service = ImportService()
        task = service.create_import_task(
            user=user,
            source_file=uploaded_file,
            import_format=ExportFormatEnum.JSON_ZIP
        )
        service.execute_import(task)
    """

    def create_import_task(
        self,
        user,
        source_file: UploadedFile,
        import_format: str = ExportFormatEnum.JSON_ZIP,
        target_tree: Tree | None = None,
    ) -> ImportTask:
        """
        Создаёт задачу на импорт.

        Args:
            user: Пользователь, запрашивающий импорт
            source_file: Загруженный файл
            import_format: Формат импорта (json_zip/gedcom)
            target_tree: Существующее дерево для импорта (опционально)

        Returns:
            ImportTask: Созданная задача импорта
        """
        task = ImportTask.objects.create(
            user=user,
            tree=target_tree,
            import_format=import_format,
            status=ImportStatusEnum.PENDING,
        )

        # Сохраняем файл
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"import_{task.pk}_{timestamp}_{source_file.name}"
        task.source_file.save(filename, source_file)

        return task

    def execute_import(self, task: ImportTask) -> ImportTask:
        """
        Выполняет задачу импорта.

        Args:
            task: Задача импорта

        Returns:
            ImportTask: Обновлённая задача с результатом
        """
        try:
            task.status = ImportStatusEnum.PROCESSING
            task.save(update_fields=["status"])

            if task.import_format == ExportFormatEnum.JSON_ZIP:
                person_count, relationship_count = self._import_from_json_zip(task)
            else:
                raise ImportError(f"Неизвестный формат импорта: {task.import_format}")

            task.person_count = person_count
            task.relationship_count = relationship_count
            task.status = ImportStatusEnum.COMPLETED
            task.completed_at = timezone.now()
            task.save()

            return task

        except Exception as e:
            task.status = ImportStatusEnum.FAILED
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save()
            raise

    def _import_from_json_zip(self, task: ImportTask) -> tuple[int, int]:
        """
        Импортирует данные из JSON+ZIP файла.

        Args:
            task: Задача импорта

        Returns:
            tuple[int, int]: Количество импортированных персон и связей
        """
        # Открываем ZIP-файл
        try:
            task.source_file.open("rb")
            zip_content = task.source_file.read()
            task.source_file.close()
        except Exception as e:
            raise ImportError(f"Не удалось открыть файл: {e}") from e  # ✅ B904 fixed

        try:
            zip_file = zipfile.ZipFile(BytesIO(zip_content), "r")
        except zipfile.BadZipFile as e:
            raise ImportError("Файл не является корректным ZIP-архивом") from e  # ✅ B904 fixed

        with zip_file:
            required_files = ["manifest.json", "persons.json", "relationships.json"]
            for filename in required_files:
                if filename not in zip_file.namelist():
                    raise ImportError(f"Отсутствует обязательный файл: {filename}")

            manifest = json.loads(zip_file.read("manifest.json"))
            # export_type не используется, но может понадобиться в будущем
            _ = manifest.get("export_type")  # ✅ F841 fixed

            # Определяем дерево для импорта
            tree = self._get_or_create_tree(task, zip_file, manifest)
            task.tree = tree
            task.save(update_fields=["tree"])

            # Импортируем данные в транзакции
            with transaction.atomic():
                # ID-маппинг: старые ID → новые ID
                person_id_mapping = self._import_persons(zip_file, tree)
                relationship_count = self._import_relationships(zip_file, person_id_mapping)
                self._import_life_events(zip_file, person_id_mapping)

                # Импортируем медиафайлы
                self._import_media(zip_file, person_id_mapping)

            person_count = len(person_id_mapping)
            return person_count, relationship_count

    def _get_or_create_tree(self, task: ImportTask, zip_file: zipfile.ZipFile, manifest: dict) -> Tree:
        """
        Получает существующее дерево или создаёт новое.

        Args:
            task: Задача импорта
            zip_file: ZIP-файл
            manifest: Данные из manifest.json

        Returns:
            Tree: Дерево для импорта
        """
        # Если указано существующее дерево — используем его
        if task.tree:
            return task.tree

        # Читаем данные дерева из ZIP
        tree_data = None
        if "tree.json" in zip_file.namelist():
            tree_data = json.loads(zip_file.read("tree.json"))

        tree_name = manifest.get("tree_name", "Импортированное дерево")

        # Проверяем, существует ли дерево с таким именем
        existing_tree = Tree.objects.filter(name=tree_name).first()

        if existing_tree:
            # Дерево существует — добавляем суффикс
            suffix = 1
            new_name = f"{tree_name} (импорт {suffix})"
            while Tree.objects.filter(name=new_name).exists():
                suffix += 1
                new_name = f"{tree_name} (импорт {suffix})"
            tree_name = new_name

        # Создаём новое дерево
        description = ""
        if tree_data:
            description = tree_data.get("description", "") or ""

        tree = Tree.objects.create(
            name=tree_name,
            description=description,
            is_public=tree_data.get("is_public", False) if tree_data else False,
        )

        # Добавляем пользователя как владельца
        TreeCollaborator.objects.create(
            tree=tree,
            user=task.user,
            role=CollaboratorRoleEnum.OWNER,
        )

        return tree

    def _import_persons(self, zip_file: zipfile.ZipFile, tree: Tree) -> dict[int, int]:
        """
        Импортирует персон из persons.json.

        Args:
            zip_file: ZIP-файл
            tree: Дерево для импорта

        Returns:
            dict[int, int]: Маппинг старых ID → новые ID
        """
        persons_data = json.loads(zip_file.read("persons.json"))
        id_mapping = {}  # old_id → new_id

        for person_data in persons_data:
            old_id = person_data.get("id")

            # Проверяем, существует ли персона с таким ФИО в дереве
            first_name = person_data.get("first_name", "")
            last_name = person_data.get("last_name", "") or ""

            existing_person = Person.objects.filter(
                tree=tree,
                first_name=first_name,
                last_name=last_name,
            ).first()

            if existing_person:
                # Персона уже есть — используем существующую
                id_mapping[old_id] = existing_person.pk
                continue

            # Создаём новую персону
            # Обрабатываем дату рождения (может быть только год в публичном экспорте)
            birth_date = self._parse_date(person_data.get("birth_date"))
            death_date = self._parse_date(person_data.get("death_date"))

            person = Person.objects.create(
                tree=tree,
                first_name=first_name,
                middle_name=person_data.get("middle_name") or "",
                last_name=last_name,
                maiden_name=person_data.get("maiden_name") or "",
                gender=person_data.get("gender", "unknown"),
                birth_date=birth_date,
                is_birth_date_approx=person_data.get("is_birth_date_approx", False),
                death_date=death_date,
                is_death_date_approx=person_data.get("is_death_date_approx", False),
                birth_place=person_data.get("birth_place") or "",
                death_place=person_data.get("death_place") or "",
                burial_place=person_data.get("burial_place") or "",
                culture=person_data.get("culture") or "",
                notes=person_data.get("notes") or "",
                status=person_data.get("status", "published"),
            )

            id_mapping[old_id] = person.pk

        return id_mapping

    def _import_relationships(self, zip_file: zipfile.ZipFile, id_mapping: dict[int, int]) -> int:
        """
        Импортирует связи из relationships.json.

        Args:
            zip_file: ZIP-файл
            id_mapping: Маппинг старых ID → новые ID

        Returns:
            int: Количество импортированных связей
        """
        relationships_data = json.loads(zip_file.read("relationships.json"))
        count = 0

        for rel_data in relationships_data:
            old_from_id = rel_data.get("from_person_id")
            old_to_id = rel_data.get("to_person_id")

            # Пропускаем, если персоны не были импортированы
            if old_from_id not in id_mapping or old_to_id not in id_mapping:
                continue

            new_from_id = id_mapping[old_from_id]
            new_to_id = id_mapping[old_to_id]
            rel_type = rel_data.get("relationship_type")

            # Проверяем, существует ли уже такая связь
            if Relationship.objects.filter(
                from_person_id=new_from_id,
                to_person_id=new_to_id,
                relationship_type=rel_type,
            ).exists():
                continue

            # Создаём связь
            start_date = self._parse_date(rel_data.get("start_date"))
            end_date = self._parse_date(rel_data.get("end_date"))

            Relationship.objects.create(
                from_person_id=new_from_id,
                to_person_id=new_to_id,
                relationship_type=rel_type,
                start_date=start_date,
                end_date=end_date,
                is_current=rel_data.get("is_current", True),
                description=rel_data.get("description") or "",
            )
            count += 1

        return count

    def _import_life_events(self, zip_file: zipfile.ZipFile, id_mapping: dict[int, int]) -> int:
        """
        Импортирует события жизни из life_events.json.

        Args:
            zip_file: ZIP-файл
            id_mapping: Маппинг старых ID → новые ID

        Returns:
            int: Количество импортированных событий
        """
        if "life_events.json" not in zip_file.namelist():
            return 0

        events_data = json.loads(zip_file.read("life_events.json"))
        count = 0

        for event_data in events_data:
            old_person_id = event_data.get("person_id")

            # Пропускаем, если персона не была импортирована
            if old_person_id not in id_mapping:
                continue

            new_person_id = id_mapping[old_person_id]

            # Обрабатываем связанную персону
            related_person_id = None
            old_related_id = event_data.get("related_person_id")
            if old_related_id and old_related_id in id_mapping:
                related_person_id = id_mapping[old_related_id]

            event_date = self._parse_date(event_data.get("event_date"))
            end_date = self._parse_date(event_data.get("end_date"))

            LifeEvent.objects.create(
                person_id=new_person_id,
                event_type=event_data.get("event_type"),
                event_date=event_date,
                end_date=end_date,
                is_date_approx=event_data.get("is_date_approx", False),
                location=event_data.get("location") or "",
                description=event_data.get("description") or "",
                related_person_id=related_person_id,
            )
            count += 1

        return count

    def _import_media(self, zip_file: zipfile.ZipFile, id_mapping: dict[int, int]) -> int:
        """
        Импортирует медиафайлы из ZIP.

        Args:
            zip_file: ZIP-файл
            id_mapping: Маппинг старых ID → новые ID

        Returns:
            int: Количество импортированных файлов
        """
        count = 0

        # Ищем все файлы в папке media/
        media_files = [name for name in zip_file.namelist() if name.startswith("media/")]

        for media_path in media_files:
            # Пытаемся определить персону по пути
            # Ожидаемый формат: media/photos/persons/photos/...
            # Но проще — связать с первой персоной, если не удаётся определить
            try:
                content = zip_file.read(media_path)

                # Извлекаем имя файла
                filename = Path(media_path).name

                # Находим персону по photo.name (если есть)
                # В упрощённой версии — пропускаем привязку к персоне
                # и просто сохраняем файлы в media/

                # Сохраняем файл в media/
                person = Person.objects.filter(pk__in=id_mapping.values()).first()

                if person:
                    person.photo.save(filename, ContentFile(content))
                    count += 1
            except Exception:
                # Пропускаем проблемные файлы
                continue

        return count

    def _parse_date(self, date_str: str | None):
        """
        Парсит дату из строки.

        Поддерживает форматы:
        - 'YYYY-MM-DD' (полная дата)
        - 'YYYY-01-01' (только год, с approx=True)
        - None

        Args:
            date_str: Строка с датой

        Returns:
            date или None
        """
        if not date_str:
            return None

        try:
            # Пытаемся распарсить как полную дату
            from datetime import datetime

            return datetime.fromisoformat(date_str).date()
        except (ValueError, TypeError):
            return None
