"""
Сервис импорта данных дерева с поддержкой разрешения конфликтов.
"""

import json
import zipfile
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Q
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
    """Сервис для импорта данных генеалогического дерева."""

    def create_import_task(
        self,
        user,
        source_file: UploadedFile,
        import_format: str = ExportFormatEnum.JSON_ZIP,
        target_tree: Tree | None = None,
    ) -> ImportTask:
        """Создаёт задачу на импорт."""
        task = ImportTask.objects.create(
            user=user,
            tree=target_tree,
            import_format=import_format,
            status=ImportStatusEnum.PENDING,
        )

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"import_{task.pk}_{timestamp}_{source_file.name}"
        task.source_file.save(filename, source_file)

        return task

    def analyze_import(self, task: ImportTask) -> list[dict]:
        """
        Анализирует файл импорта и находит потенциальные дубликаты.

        Returns:
            list[dict]: Список конфликтов с информацией о дубликатах.
        """
        try:
            task.status = ImportStatusEnum.PROCESSING
            task.save(update_fields=["status"])

            if task.import_format == ExportFormatEnum.JSON_ZIP:
                conflicts = self._analyze_json_zip(task)
            else:
                raise ImportError(f"Неизвестный формат импорта: {task.import_format}")

            # Сохраняем конфликты в задаче
            task.conflict_data = conflicts
            task.save(update_fields=["conflict_data"])

            return conflicts

        except Exception as e:
            task.status = ImportStatusEnum.FAILED
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save()
            raise

    def apply_import(self, task: ImportTask, decisions: list[dict]) -> ImportTask:
        """
        Применяет импорт с учётом решений пользователя.

        Args:
            task: Задача импорта
            decisions: Список решений вида:
                [
                    {"old_id": 1, "action": "merge", "existing_person_id": 5},
                    {"old_id": 2, "action": "create"},
                    {"old_id": 3, "action": "skip"}
                ]

        Returns:
            ImportTask: Обновлённая задача с результатом.
        """
        try:
            task.status = ImportStatusEnum.PROCESSING
            task.save(update_fields=["status"])

            if task.import_format == ExportFormatEnum.JSON_ZIP:
                person_count, relationship_count = self._apply_json_zip_import(task, decisions)
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

    def _analyze_json_zip(self, task: ImportTask) -> list[dict]:
        """Анализирует JSON+ZIP файл и находит дубликаты."""
        try:
            task.source_file.open("rb")
            zip_content = task.source_file.read()
            task.source_file.close()
        except Exception as e:
            raise ImportError(f"Не удалось открыть файл: {e}") from e

        try:
            zip_file = zipfile.ZipFile(BytesIO(zip_content), "r")
        except zipfile.BadZipFile as e:
            raise ImportError("Файл не является корректным ZIP-архивом") from e

        with zip_file:
            required_files = ["manifest.json", "persons.json", "relationships.json"]
            for filename in required_files:
                if filename not in zip_file.namelist():
                    raise ImportError(f"Отсутствует обязательный файл: {filename}")

            manifest = json.loads(zip_file.read("manifest.json"))
            tree = self._get_or_create_tree(task, zip_file, manifest)
            task.tree = tree
            task.save(update_fields=["tree"])

            # Анализируем персон на дубликаты
            persons_data = json.loads(zip_file.read("persons.json"))
            conflicts = []

            for person_data in persons_data:
                old_id = person_data.get("id")
                first_name = person_data.get("first_name", "")
                last_name = person_data.get("last_name", "") or ""
                middle_name = person_data.get("middle_name", "") or ""
                birth_date = self._parse_date(person_data.get("birth_date"))

                # Ищем потенциальные дубликаты (используем улучшенную логику)
                duplicates = self._find_duplicates(tree, first_name, middle_name, last_name, birth_date)

                if duplicates:
                    # Есть потенциальные дубликаты — добавляем в список конфликтов
                    conflicts.append(
                        {
                            "old_id": old_id,
                            "person_data": person_data,
                            "duplicates": [
                                {
                                    "id": dup.pk,
                                    "full_name": dup.full_name_display,
                                    "birth_date": dup.birth_date.strftime("%d.%m.%Y") if dup.birth_date else None,
                                    "death_date": dup.death_date.strftime("%d.%m.%Y") if dup.death_date else None,
                                    "birth_place": dup.birth_place,
                                }
                                for dup in duplicates
                            ],
                        }
                    )
                else:
                    # Дубликатов нет — автоматически создаём
                    conflicts.append(
                        {
                            "old_id": old_id,
                            "person_data": person_data,
                            "duplicates": [],
                            "auto_action": "create",
                        }
                    )

            return conflicts

    def _find_duplicates(
        self, tree: Tree, first_name: str, middle_name: str, last_name: str, birth_date
    ) -> list[Person]:
        """Ищет потенциальные дубликаты в дереве."""
        if not first_name:
            return []

        candidates = Person.objects.filter(tree=tree).exclude(Q(first_name="") & Q(last_name=""))
        duplicates = []

        for person in candidates:
            score = 0

            # Имя
            if person.first_name:
                if person.first_name.lower() == first_name.lower():
                    score += 3
                elif person.first_name[0].lower() == first_name[0].lower():
                    score += 1

            # Фамилия
            if person.last_name and last_name:
                if person.last_name.lower() == last_name.lower():
                    score += 3
                elif person.last_name[0].lower() == last_name[0].lower():
                    score += 1

            # Отчество
            if person.middle_name and middle_name:
                if person.middle_name.lower() == middle_name.lower():
                    score += 2
                elif person.middle_name[0].lower() == middle_name[0].lower():
                    score += 1

            # Дата рождения
            if person.birth_date and birth_date:
                if person.birth_date == birth_date:
                    score += 4
                elif person.birth_date.year == birth_date.year:
                    score += 1
                else:
                    score -= 5
            elif not person.birth_date and not birth_date:
                score += 1

            # Порог совпадения
            if score >= 6:
                duplicates.append(person)

        return duplicates

    def _apply_json_zip_import(self, task: ImportTask, decisions: list[dict]) -> tuple[int, int]:
        """Применяет импорт с учётом решений."""
        try:
            task.source_file.open("rb")
            zip_content = task.source_file.read()
            task.source_file.close()
        except Exception as e:
            raise ImportError(f"Не удалось открыть файл: {e}") from e

        try:
            zip_file = zipfile.ZipFile(BytesIO(zip_content), "r")
        except zipfile.BadZipFile as e:
            raise ImportError("Файл не является корректным ZIP-архивом") from e

        with zip_file:
            tree = task.tree
            if not tree:
                raise ImportError("Дерево не определено")

            # Создаём маппинг решений
            decision_map = {d["old_id"]: d for d in decisions}

            with transaction.atomic():
                person_id_mapping = self._apply_persons_import(zip_file, tree, decision_map)
                relationship_count = self._import_relationships(zip_file, person_id_mapping)
                self._import_life_events(zip_file, person_id_mapping)
                self._import_media(zip_file, person_id_mapping)

            person_count = len(person_id_mapping)
            return person_count, relationship_count

    def _apply_persons_import(self, zip_file: zipfile.ZipFile, tree: Tree, decision_map: dict) -> dict[int, int]:
        """Импортирует персон с учётом решений."""
        persons_data = json.loads(zip_file.read("persons.json"))
        id_mapping = {}

        for person_data in persons_data:
            old_id = person_data.get("id")
            decision = decision_map.get(old_id)

            if not decision:
                continue

            action = decision.get("action", "create")

            if action == "skip":
                continue

            elif action == "merge":
                # Объединяем с существующей персоной
                existing_person_id = decision.get("existing_person_id")
                if existing_person_id:
                    person = Person.objects.get(pk=existing_person_id)
                    # Обновляем данные, если в импорте они более полные
                    self._merge_person_data(person, person_data)
                    id_mapping[old_id] = person.pk

            elif action == "create":
                # Создаём новую персону
                birth_date = self._parse_date(person_data.get("birth_date"))
                death_date = self._parse_date(person_data.get("death_date"))

                person = Person.objects.create(
                    tree=tree,
                    first_name=person_data.get("first_name", ""),
                    middle_name=person_data.get("middle_name") or "",
                    last_name=person_data.get("last_name") or "",
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

    def _merge_person_data(self, person: Person, person_data: dict):
        """Обновляет данные персоны, если в импорте они более полные."""
        fields_to_update = []

        # Обновляем только если в импорте есть данные, а в базе их нет
        if person_data.get("middle_name") and not person.middle_name:
            person.middle_name = person_data["middle_name"]
            fields_to_update.append("middle_name")

        if person_data.get("maiden_name") and not person.maiden_name:
            person.maiden_name = person_data["maiden_name"]
            fields_to_update.append("maiden_name")

        birth_date = self._parse_date(person_data.get("birth_date"))
        if birth_date and not person.birth_date:
            person.birth_date = birth_date
            fields_to_update.append("birth_date")

        death_date = self._parse_date(person_data.get("death_date"))
        if death_date and not person.death_date:
            person.death_date = death_date
            fields_to_update.append("death_date")

        if person_data.get("birth_place") and not person.birth_place:
            person.birth_place = person_data["birth_place"]
            fields_to_update.append("birth_place")

        if person_data.get("death_place") and not person.death_place:
            person.death_place = person_data["death_place"]
            fields_to_update.append("death_place")

        if person_data.get("burial_place") and not person.burial_place:
            person.burial_place = person_data["burial_place"]
            fields_to_update.append("burial_place")

        if person_data.get("culture") and not person.culture:
            person.culture = person_data["culture"]
            fields_to_update.append("culture")

        if person_data.get("notes") and not person.notes:
            person.notes = person_data["notes"]
            fields_to_update.append("notes")

        if fields_to_update:
            person.save(update_fields=fields_to_update)

    # === Остальные методы без изменений ===

    def _get_or_create_tree(self, task: ImportTask, zip_file: zipfile.ZipFile, manifest: dict) -> Tree:
        """Получает существующее дерево или создаёт новое."""
        if task.tree:
            return task.tree

        tree_data = None
        if "tree.json" in zip_file.namelist():
            tree_data = json.loads(zip_file.read("tree.json"))

        tree_name = manifest.get("tree_name", "Импортированное дерево")

        existing_tree = Tree.objects.filter(name=tree_name).first()

        if existing_tree:
            suffix = 1
            new_name = f"{tree_name} (импорт {suffix})"
            while Tree.objects.filter(name=new_name).exists():
                suffix += 1
                new_name = f"{tree_name} (импорт {suffix})"
            tree_name = new_name

        description = ""
        if tree_data:
            description = tree_data.get("description", "") or ""

        tree = Tree.objects.create(
            name=tree_name,
            description=description,
            is_public=tree_data.get("is_public", False) if tree_data else False,
        )

        TreeCollaborator.objects.create(
            tree=tree,
            user=task.user,
            role=CollaboratorRoleEnum.OWNER,
        )

        return tree

    def _import_relationships(self, zip_file: zipfile.ZipFile, id_mapping: dict[int, int]) -> int:
        """Импортирует связи."""
        relationships_data = json.loads(zip_file.read("relationships.json"))
        count = 0

        for rel_data in relationships_data:
            old_from_id = rel_data.get("from_person_id")
            old_to_id = rel_data.get("to_person_id")

            if old_from_id not in id_mapping or old_to_id not in id_mapping:
                continue

            new_from_id = id_mapping[old_from_id]
            new_to_id = id_mapping[old_to_id]
            rel_type = rel_data.get("relationship_type")

            if Relationship.objects.filter(
                from_person_id=new_from_id,
                to_person_id=new_to_id,
                relationship_type=rel_type,
            ).exists():
                continue

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
        """Импортирует события жизни."""
        if "life_events.json" not in zip_file.namelist():
            return 0

        events_data = json.loads(zip_file.read("life_events.json"))
        count = 0

        for event_data in events_data:
            old_person_id = event_data.get("person_id")

            if old_person_id not in id_mapping:
                continue

            new_person_id = id_mapping[old_person_id]

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
        """Импортирует медиафайлы."""
        count = 0
        media_files = [name for name in zip_file.namelist() if name.startswith("media/")]

        for media_path in media_files:
            try:
                content = zip_file.read(media_path)
                filename = Path(media_path).name
                person = Person.objects.filter(pk__in=id_mapping.values()).first()

                if person:
                    person.photo.save(filename, ContentFile(content))
                    count += 1
            except Exception:
                continue

        return count

    def _parse_date(self, date_str: str | None):
        """Парсит дату из строки."""
        if not date_str:
            return None

        try:
            from datetime import datetime

            return datetime.fromisoformat(date_str).date()
        except (ValueError, TypeError):
            return None
