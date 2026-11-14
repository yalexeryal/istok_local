"""
Сервис импорта данных дерева с поддержкой разрешения конфликтов.
Включает защиту от чрезмерного расхода ресурсов (P1 безопасность).
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


# === 🔒 ЛИМИТЫ БЕЗОПАСНОСТИ (P1) ===
MAX_PERSONS_PER_IMPORT = 10_000  # Максимум персон в одном импорте
MAX_UNCOMPRESSED_SIZE = 500 * 1024 * 1024  # 500 МБ суммарный размер распакованных данных
MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ на один файл внутри архива
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_MANIFEST_VERSIONS = {"1.0", "1.1"}  # Поддерживаемые версии формата


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
        # 🔒 Проверка прав при слиянии в существующее дерево
        if target_tree and not target_tree.user_can_edit(user):
            raise ImportError("Нет прав для импорта в это дерево")

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

    def execute_import(self, task: ImportTask) -> ImportTask:
        """Совместимый однократный импорт; неоднозначные совпадения требуют решения."""
        conflicts = self.analyze_import(task)
        decisions = []
        for conflict in conflicts:
            duplicates = conflict["duplicates"]
            if len(duplicates) > 1:
                raise ImportError("Найдены неоднозначные совпадения. Разрешите конфликты вручную.")
            decision = {"old_id": conflict["old_id"], "action": "create"}
            if duplicates:
                decision.update(action="merge", existing_person_id=duplicates[0]["id"])
            decisions.append(decision)
        return self.apply_import(task, decisions)

    def analyze_import(self, task: ImportTask) -> list[dict]:
        """
        Анализирует файл импорта и находит потенциальные дубликаты.

        Returns:
            list[dict]: Список конфликтов с информацией о дубликатах.
        """
        # 🔒 Проверка состояния задачи
        task.refresh_from_db()
        if task.status != ImportStatusEnum.PENDING:
            raise ImportError("Задача уже была проанализирована")
        if task.tree and not task.tree.user_can_edit(task.user):
            raise ImportError("Нет прав для импорта в это дерево")

        try:
            task.status = ImportStatusEnum.PROCESSING
            task.save(update_fields=["status"])

            if task.import_format == ExportFormatEnum.JSON_ZIP:
                conflicts = self._analyze_json_zip(task)
            else:
                raise ImportError(f"Неизвестный формат импорта: {task.import_format}")

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
        """
        # 🔒 Проверка состояния и прав
        task.refresh_from_db()
        if task.status != ImportStatusEnum.PROCESSING:
            raise ImportError("Задача не находится в состоянии анализа")
        if not task.tree or not task.tree.user_can_edit(task.user):
            raise ImportError("Нет прав для импорта в это дерево")

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

    def _validate_zip_safety(self, zip_file: zipfile.ZipFile) -> None:
        """
        🔒 P1: Проверяет ZIP-архив на безопасность.
        Защита от ZIP-бомб и чрезмерно больших файлов.
        """
        total_uncompressed = 0

        for info in zip_file.infolist():
            # Защита от сжатых файлов с отрицательным размером (сигнатура атаки)
            if info.file_size < 0:
                raise ImportError(f"Обнаружен подозрительный файл: {info.filename}")

            # Защита от одиночных огромных файлов
            if info.file_size > MAX_SINGLE_FILE_SIZE:
                size_mb = info.file_size / (1024 * 1024)
                raise ImportError(
                    f"Файл '{info.filename}' слишком большой ({size_mb:.1f} МБ). "
                    f"Максимум: {MAX_SINGLE_FILE_SIZE // (1024 * 1024)} МБ."
                )

            total_uncompressed += info.file_size

            # Защита от суммарного размера (ZIP-бомба)
            if total_uncompressed > MAX_UNCOMPRESSED_SIZE:
                size_mb = total_uncompressed / (1024 * 1024)
                raise ImportError(
                    f"Суммарный размер распакованных данных слишком велик ({size_mb:.1f} МБ). "
                    f"Максимум: {MAX_UNCOMPRESSED_SIZE // (1024 * 1024)} МБ."
                )

    def _validate_manifest(self, manifest: dict) -> None:
        """🔒 P1: Проверяет структуру и версию manifest.json."""
        if not isinstance(manifest, dict):
            raise ImportError("manifest.json должен быть JSON-объектом")

        # Проверяем обязательные поля
        if "tree_name" not in manifest:
            raise ImportError("В manifest.json отсутствует обязательное поле 'tree_name'")

        # Проверяем версию (если указана)
        version = manifest.get("version")
        if version and version not in SUPPORTED_MANIFEST_VERSIONS:
            raise ImportError(
                f"Неподдерживаемая версия формата: {version}. "
                f"Поддерживаются: {', '.join(sorted(SUPPORTED_MANIFEST_VERSIONS))}"
            )

    def _validate_person_data(self, person_data: dict, index: int) -> None:
        """🔒 P1: Проверяет схему данных персоны."""
        if not isinstance(person_data, dict):
            raise ImportError(f"Запись персоны #{index} имеет неверный формат")

        if "id" not in person_data:
            raise ImportError(f"У персоны #{index} отсутствует обязательное поле 'id'")

        # first_name может быть пустым, но должен присутствовать как ключ
        if "first_name" not in person_data:
            raise ImportError(f"У персоны #{index} (id={person_data.get('id')}) отсутствует поле 'first_name'")

    def _is_safe_image(self, filename: str) -> bool:
        """🔒 P1: Проверяет, что файл является допустимым изображением."""
        ext = Path(filename).suffix.lower()
        return ext in ALLOWED_IMAGE_EXTENSIONS

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
            # 🔒 P1: Проверка безопасности архива
            self._validate_zip_safety(zip_file)

            required_files = ["manifest.json", "persons.json", "relationships.json"]
            for filename in required_files:
                if filename not in zip_file.namelist():
                    raise ImportError(f"Отсутствует обязательный файл: {filename}")

            # 🔒 P1: Валидация манифеста
            try:
                manifest = json.loads(zip_file.read("manifest.json"))
            except json.JSONDecodeError as e:
                raise ImportError(f"manifest.json содержит некорректный JSON: {e}") from e

            self._validate_manifest(manifest)

            tree = self._get_or_create_tree(task, zip_file, manifest)
            task.tree = tree
            task.save(update_fields=["tree"])

            # 🔒 P1: Валидация и загрузка персон
            try:
                persons_data = json.loads(zip_file.read("persons.json"))
            except json.JSONDecodeError as e:
                raise ImportError(f"persons.json содержит некорректный JSON: {e}") from e

            if not isinstance(persons_data, list):
                raise ImportError("persons.json должен содержать массив записей")

            # 🔒 P1: Лимит на количество персон
            if len(persons_data) > MAX_PERSONS_PER_IMPORT:
                raise ImportError(
                    f"Слишком много персон для импорта: {len(persons_data)}. "
                    f"Максимум: {MAX_PERSONS_PER_IMPORT}."
                )

            # 🔒 P1: Валидация схемы каждой записи
            for i, person_data in enumerate(persons_data):
                self._validate_person_data(person_data, i)

            conflicts = []

            for person_data in persons_data:
                old_id = person_data.get("id")
                first_name = person_data.get("first_name", "")
                last_name = person_data.get("last_name", "") or ""
                middle_name = person_data.get("middle_name", "") or ""
                birth_date = self._parse_date(person_data.get("birth_date"))

                duplicates = self._find_duplicates(tree, first_name, middle_name, last_name, birth_date)

                if duplicates:
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

            if person.first_name:
                if person.first_name.lower() == first_name.lower():
                    score += 3
                elif person.first_name[0].lower() == first_name[0].lower():
                    score += 1

            if person.last_name and last_name:
                if person.last_name.lower() == last_name.lower():
                    score += 3
                elif person.last_name[0].lower() == last_name[0].lower():
                    score += 1

            if person.middle_name and middle_name:
                if person.middle_name.lower() == middle_name.lower():
                    score += 2
                elif person.middle_name[0].lower() == middle_name[0].lower():
                    score += 1

            if person.birth_date and birth_date:
                if person.birth_date == birth_date:
                    score += 4
                elif person.birth_date.year == birth_date.year:
                    score += 1
                else:
                    score -= 5
            elif not person.birth_date and not birth_date:
                score += 1

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
            # 🔒 P1: Повторная проверка безопасности (на случай, если analyze не вызывался)
            self._validate_zip_safety(zip_file)

            tree = task.tree
            if not tree:
                raise ImportError("Дерево не определено")

            decision_map = {d["old_id"]: d for d in decisions}

            # 🔒 P1: Валидация решений
            for decision in decisions:
                action = decision.get("action", "create")
                if action not in {"create", "merge", "skip"}:
                    raise ImportError(f"Неизвестное решение конфликта: {action}")

            with transaction.atomic():
                person_id_mapping = self._apply_persons_import(zip_file, tree, decision_map)
                relationship_count = self._import_relationships(zip_file, tree, person_id_mapping)
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

            # 🔒 P1: Если решения нет — создаём по умолчанию (для совместимости)
            action = decision.get("action", "create") if decision else "create"

            if action == "skip":
                continue

            elif action == "merge":
                existing_person_id = decision.get("existing_person_id")
                if existing_person_id:
                    # 🔒 P1: Ограничиваем merge только персонами из целевого дерева
                    try:
                        person = Person.objects.get(pk=existing_person_id, tree=tree)
                    except (Person.DoesNotExist, ValueError, TypeError) as e:
                        raise ImportError("Персона для объединения не найдена в целевом дереве") from e
                    self._merge_person_data(person, person_data)
                    id_mapping[old_id] = person.pk

            elif action == "create":
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

    def _import_relationships(self, zip_file: zipfile.ZipFile, tree: Tree, id_mapping: dict[int, int]) -> int:
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

            # 🔒 P1: Защита от связей с самим собой
            if new_from_id == new_to_id:
                continue

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
        """
        🔒 P1: Импортирует медиафайлы с проверкой типов и правильной привязкой к персонам.
        Теперь фото связывается с персоной через поле 'photo' в persons.json.
        """
        count = 0

        # 🔒 P1: Сначала читаем persons.json, чтобы узнать, какие фото кому принадлежат
        try:
            persons_data = json.loads(zip_file.read("persons.json"))
        except (json.JSONDecodeError, KeyError):
            persons_data = []

        # Строим маппинг: старое ID персоны -> имя файла фото
        person_photo_map = {}
        for person_data in persons_data:
            old_id = person_data.get("id")
            photo_name = person_data.get("photo")
            if old_id and photo_name and old_id in id_mapping:
                person_photo_map[old_id] = photo_name

        # 🔒 P1: Обрабатываем только файлы из папки media/
        media_files = [name for name in zip_file.namelist() if name.startswith("media/")]

        for media_path in media_files:
            try:
                filename = Path(media_path).name

                # 🔒 P1: Проверка типа файла
                if not self._is_safe_image(filename):
                    continue  # Пропускаем не-изображения

                # 🔒 P1: Находим персону, которой принадлежит это фото
                target_person = None
                for old_id, photo_name in person_photo_map.items():
                    if Path(photo_name).name == filename:
                        target_person = Person.objects.get(pk=id_mapping[old_id])
                        break

                if not target_person:
                    continue  # Пропускаем фото без владельца

                content = zip_file.read(media_path)
                target_person.photo.save(filename, ContentFile(content))
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
