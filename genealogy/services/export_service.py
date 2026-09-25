"""
Сервис экспорта данных дерева.

Поддерживает три типа экспорта:
- FULL: полная выгрузка всех данных дерева
- RELATIVE: выгрузка только родственников целевой персоны
- PUBLIC: урезанная публичная версия

Формат: JSON + ZIP (с медиафайлами)
"""

import json
import zipfile
from collections import deque
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db.models import Q
from django.utils import timezone

from genealogy.models import (
    ExportFormatEnum,
    ExportStatusEnum,
    ExportTask,
    ExportTypeEnum,
    LifeEvent,
    Person,
    PrivacySettings,
    Relationship,
    RelationshipTypeEnum,
    Tree,
    TreeCollaborator,
)


class ExportService:
    """
    Сервис для экспорта данных генеалогического дерева.

    Пример использования:
        service = ExportService()
        task = service.create_export_task(
            user=user,
            tree=tree,
            export_type=ExportTypeEnum.FULL,
            export_format=ExportFormatEnum.JSON_ZIP
        )
        service.execute_export(task)
    """

    def create_export_task(
        self,
        user,
        tree: Tree,
        export_type: str,
        export_format: str = ExportFormatEnum.JSON_ZIP,
        target_person: Person | None = None,
        privacy_overrides: dict | None = None,
    ) -> ExportTask:
        """
        Создаёт задачу на экспорт.

        Args:
            user: Пользователь, запрашивающий экспорт
            tree: Дерево для экспорта
            export_type: Тип экспорта (full/relative/public)
            export_format: Формат экспорта (json_zip/gedcom)
            target_person: Целевая персона (для типа RELATIVE)
            privacy_overrides: Переопределение настроек приватности

        Returns:
            ExportTask: Созданная задача экспорта
        """
        task = ExportTask.objects.create(
            user=user,
            tree=tree,
            export_type=export_type,
            export_format=export_format,
            target_person=target_person,
            privacy_overrides=privacy_overrides or {},
            status=ExportStatusEnum.PENDING,
        )
        return task

    def execute_export(self, task: ExportTask) -> ExportTask:
        """
        Выполняет задачу экспорта.

        Args:
            task: Задача экспорта

        Returns:
            ExportTask: Обновлённая задача с результатом
        """
        try:
            task.status = ExportStatusEnum.PROCESSING
            task.save(update_fields=["status"])

            # Выбираем метод экспорта в зависимости от типа
            if task.export_type == ExportTypeEnum.FULL:
                content, person_count = self._export_full(task.tree)
            elif task.export_type == ExportTypeEnum.RELATIVE:
                if not task.target_person:
                    raise ValueError("Для типа RELATIVE необходима целевая персона")
                content, person_count = self._export_relative(
                    task.tree, task.target_person, task.user, task.privacy_overrides
                )
            elif task.export_type == ExportTypeEnum.PUBLIC:
                content, person_count = self._export_public(task.tree)
            else:
                raise ValueError(f"Неизвестный тип экспорта: {task.export_type}")

            # Сохраняем файл
            timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{task.tree.name}_{timestamp}.zip"

            task.file.save(filename, ContentFile(content))
            task.file_size = len(content)
            task.person_count = person_count
            task.status = ExportStatusEnum.COMPLETED
            task.completed_at = timezone.now()
            task.save()

            return task

        except Exception as e:
            task.status = ExportStatusEnum.FAILED
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save()
            raise

    def _export_full(self, tree: Tree) -> tuple[bytes, int]:
        """
        Полная выгрузка всех данных дерева.

        Args:
            tree: Дерево для экспорта

        Returns:
            tuple[bytes, int]: Содержимое ZIP и количество персон
        """
        persons = tree.persons.all()
        person_count = persons.count()

        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Manifest
            manifest = {
                "version": "1.0",
                "export_type": ExportTypeEnum.FULL,
                "exported_at": timezone.now().isoformat(),
                "tree_name": tree.name,
                "tree_description": tree.description or "",
                "person_count": person_count,
                "app_version": "0.1.0",
            }
            zip_file.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            # Tree
            tree_data = {
                "id": tree.pk,
                "name": tree.name,
                "description": tree.description,
                "is_public": tree.is_public,
            }
            zip_file.writestr("tree.json", json.dumps(tree_data, indent=2, ensure_ascii=False))

            # Persons
            persons_data = [self._person_to_dict(p) for p in persons]
            zip_file.writestr("persons.json", json.dumps(persons_data, indent=2, ensure_ascii=False))

            # Relationships
            relationships = Relationship.objects.filter(from_person__tree=tree)
            relationships_data = [self._relationship_to_dict(r) for r in relationships]
            zip_file.writestr("relationships.json", json.dumps(relationships_data, indent=2, ensure_ascii=False))

            # Life Events
            life_events = LifeEvent.objects.filter(person__tree=tree)
            life_events_data = [self._life_event_to_dict(e) for e in life_events]
            zip_file.writestr("life_events.json", json.dumps(life_events_data, indent=2, ensure_ascii=False))

            # Collaborators
            collaborators = tree.collaborators.all()
            collaborators_data = [self._collaborator_to_dict(c) for c in collaborators]
            zip_file.writestr("collaborators.json", json.dumps(collaborators_data, indent=2, ensure_ascii=False))

            # Media files
            for person in persons:
                if person.photo:
                    try:
                        photo_path = Path(person.photo.path)
                        if photo_path.exists():
                            with open(photo_path, "rb") as f:
                                zip_file.writestr(f"media/photos/{person.photo.name}", f.read())
                    except (ValueError, NotImplementedError):
                        # Фото нет или оно не на диске
                        pass

        return buffer.getvalue(), person_count

    def _export_relative(
        self,
        tree: Tree,
        target_person: Person,
        user,
        privacy_overrides: dict | None = None,
    ) -> tuple[bytes, int]:
        """
        Выгрузка только родственников целевой персоны.

        Использует BFS для поиска всех связанных персон и применяет
        настройки приватности в зависимости от степени родства.

        Args:
            tree: Дерево для экспорта
            target_person: Персона, для которой экспортируем
            user: Пользователь, запрашивающий экспорт
            privacy_overrides: Переопределение настроек приватности

        Returns:
            tuple[bytes, int]: Содержимое ZIP и количество персон
        """
        # Получаем настройки приватности
        try:
            privacy_settings = user.privacy_settings
        except PrivacySettings.DoesNotExist:
            privacy_settings = None

        # Находим всех родственников через BFS
        relatives, degrees = self._find_relatives(target_person)

        person_count = len(relatives)

        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Manifest
            manifest = {
                "version": "1.0",
                "export_type": ExportTypeEnum.RELATIVE,
                "exported_at": timezone.now().isoformat(),
                "tree_name": tree.name,
                "target_person": target_person.full_name_display,
                "person_count": person_count,
                "app_version": "0.1.0",
            }
            zip_file.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            # Persons с учётом приватности
            persons_data = []
            for person in relatives:
                degree = degrees.get(person.pk, float("inf"))
                person_data = self._person_to_dict_with_privacy(person, privacy_settings, degree, privacy_overrides)
                persons_data.append(person_data)

            zip_file.writestr("persons.json", json.dumps(persons_data, indent=2, ensure_ascii=False))

            # Только связи между включёнными персонами
            relative_ids = {p.pk for p in relatives}
            relationships = Relationship.objects.filter(from_person_id__in=relative_ids, to_person_id__in=relative_ids)
            relationships_data = [self._relationship_to_dict(r) for r in relationships]
            zip_file.writestr("relationships.json", json.dumps(relationships_data, indent=2, ensure_ascii=False))

            # Только события включённых персон
            life_events = LifeEvent.objects.filter(person_id__in=relative_ids)
            life_events_data = [self._life_event_to_dict(e) for e in life_events]
            zip_file.writestr("life_events.json", json.dumps(life_events_data, indent=2, ensure_ascii=False))

            # Media files (с учётом приватности)
            for person in relatives:
                if person.photo and not self._should_hide_photos(
                    person, privacy_settings, degrees.get(person.pk, float("inf")), privacy_overrides
                ):
                    try:
                        photo_path = Path(person.photo.path)
                        if photo_path.exists():
                            with open(photo_path, "rb") as f:
                                zip_file.writestr(f"media/photos/{person.photo.name}", f.read())
                    except (ValueError, NotImplementedError):
                        pass

        return buffer.getvalue(), person_count

    def _export_public(self, tree: Tree) -> tuple[bytes, int]:
        """
        Урезанная публичная выгрузка.

        Включает только базовую информацию без заметок, точных дат и медиа.

        Args:
            tree: Дерево для экспорта

        Returns:
            tuple[bytes, int]: Содержимое ZIP и количество персон
        """
        persons = tree.persons.all()
        person_count = persons.count()

        buffer = BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Manifest
            manifest = {
                "version": "1.0",
                "export_type": ExportTypeEnum.PUBLIC,
                "exported_at": timezone.now().isoformat(),
                "tree_name": tree.name,
                "person_count": person_count,
                "app_version": "0.1.0",
                "note": "Публичная версия с ограниченной информацией",
            }
            zip_file.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

            # Persons (урезанные)
            persons_data = [self._person_to_dict_public(p) for p in persons]
            zip_file.writestr("persons.json", json.dumps(persons_data, indent=2, ensure_ascii=False))

            # Relationships
            relationships = Relationship.objects.filter(from_person__tree=tree)
            relationships_data = [self._relationship_to_dict(r) for r in relationships]
            zip_file.writestr("relationships.json", json.dumps(relationships_data, indent=2, ensure_ascii=False))

            # Нет life_events, нет media, нет collaborators

        return buffer.getvalue(), person_count

    def _find_relatives(self, target_person: Person, max_depth: int = 20) -> tuple[list[Person], dict[int, int]]:
        """
        Находит всех родственников целевой персоны через BFS.

        Args:
            target_person: Персона, от которой ищем родственников
            max_depth: Максимальная глубина поиска

        Returns:
            tuple[list[Person], dict[int, int]]:
                Список персон и словарь степеней родства
        """
        visited = set()
        degrees = {}  # person_id -> degree
        queue = deque([(target_person, 0)])

        while queue:
            current, depth = queue.popleft()

            if current.pk in visited or depth > max_depth:
                continue

            visited.add(current.pk)
            degrees[current.pk] = depth

            # Находим всех связанных персон
            connected_persons = set()

            # Родители (через relationships_to, где текущая персона — ребёнок)
            parent_rels = current.relationships_to.filter(
                relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ]
            )
            for rel in parent_rels:
                connected_persons.add(rel.from_person)

            # Дети (через relationships_from, где текущая персона — родитель)
            child_rels = current.relationships_from.filter(
                relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ]
            )
            for rel in child_rels:
                connected_persons.add(rel.to_person)

            # Супруги
            spouse_rels = Relationship.objects.filter(
                relationship_type__in=[
                    RelationshipTypeEnum.SPOUSE,
                    RelationshipTypeEnum.EX_SPOUSE,
                    RelationshipTypeEnum.FIANCE,
                ]
            ).filter(Q(from_person=current) | Q(to_person=current))
            for rel in spouse_rels:
                if rel.from_person_id == current.pk:
                    connected_persons.add(rel.to_person)
                else:
                    connected_persons.add(rel.from_person)

            # Добавляем в очередь
            for person in connected_persons:
                if person.pk not in visited:
                    queue.append((person, depth + 1))

        # Получаем объекты персон
        relatives = list(Person.objects.filter(pk__in=visited))

        return relatives, degrees

    def _person_to_dict(self, person: Person) -> dict:
        """Конвертирует персону в словарь для экспорта."""
        return {
            "id": person.pk,
            "tree_id": person.tree_id,
            "first_name": person.first_name,
            "middle_name": person.middle_name,
            "last_name": person.last_name,
            "maiden_name": person.maiden_name,
            "gender": person.gender,
            "birth_date": person.birth_date.isoformat() if person.birth_date else None,
            "is_birth_date_approx": person.is_birth_date_approx,
            "death_date": person.death_date.isoformat() if person.death_date else None,
            "is_death_date_approx": person.is_death_date_approx,
            "birth_place": person.birth_place,
            "death_place": person.death_place,
            "burial_place": person.burial_place,
            "culture": person.culture,
            "photo": person.photo.name if person.photo else None,
            "notes": person.notes,
            "status": person.status,
        }

    def _person_to_dict_with_privacy(
        self,
        person: Person,
        privacy_settings: PrivacySettings | None,
        degree: int,
        privacy_overrides: dict | None = None,
    ) -> dict:
        """
        Конвертирует персону в словарь с учётом настроек приватности.

        Если степень родства <= full_data_min_degree, возвращает полные данные.
        Иначе применяет настройки приватности.
        """
        # Если степень родства близкая — полные данные
        if privacy_settings and degree <= privacy_settings.full_data_min_degree:
            return self._person_to_dict(person)

        # Иначе применяем приватность
        data = self._person_to_dict(person)

        # Применяем настройки приватности
        if privacy_settings:
            if privacy_settings.hide_birth_date:
                data["birth_date"] = None
                data["is_birth_date_approx"] = False
            elif degree > privacy_settings.full_data_min_degree:
                # Для дальних родственников — только год
                if data["birth_date"]:
                    data["birth_date"] = data["birth_date"][:4] + "-01-01"
                    data["is_birth_date_approx"] = True

            if privacy_settings.hide_death_date:
                data["death_date"] = None
                data["is_death_date_approx"] = False

            if privacy_settings.hide_birth_place:
                data["birth_place"] = None

            if privacy_settings.hide_death_place:
                data["death_place"] = None

            if privacy_settings.hide_notes:
                data["notes"] = None

        # Переопределения
        if privacy_overrides:
            for key, value in privacy_overrides.items():
                if key in data:
                    data[key] = value

        return data

    def _person_to_dict_public(self, person: Person) -> dict:
        """Конвертирует персону в урезанный словарь для публичного экспорта."""
        return {
            "id": person.pk,
            "first_name": person.first_name,
            "last_name": person.last_name,
            "gender": person.gender,
            "birth_year": person.birth_date.year if person.birth_date else None,
            "death_year": person.death_date.year if person.death_date else None,
            "is_alive": person.is_alive,
        }

    def _relationship_to_dict(self, relationship: Relationship) -> dict:
        """Конвертирует связь в словарь для экспорта."""
        return {
            "id": relationship.pk,
            "from_person_id": relationship.from_person_id,
            "to_person_id": relationship.to_person_id,
            "relationship_type": relationship.relationship_type,
            "start_date": relationship.start_date.isoformat() if relationship.start_date else None,
            "end_date": relationship.end_date.isoformat() if relationship.end_date else None,
            "is_current": relationship.is_current,
            "description": relationship.description,
        }

    def _life_event_to_dict(self, event: LifeEvent) -> dict:
        """Конвертирует событие в словарь для экспорта."""
        return {
            "id": event.pk,
            "person_id": event.person_id,
            "event_type": event.event_type,
            "event_date": event.event_date.isoformat() if event.event_date else None,
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "is_date_approx": event.is_date_approx,
            "location": event.location,
            "description": event.description,
            "related_person_id": event.related_person_id,
        }

    def _collaborator_to_dict(self, collaborator: TreeCollaborator) -> dict:
        """Конвертирует соавтора в словарь для экспорта."""
        return {
            "id": collaborator.pk,
            "user_username": collaborator.user.username,
            "user_email": collaborator.user.email,
            "role": collaborator.role,
            "can_invite": collaborator.can_invite,
        }

    def _should_hide_photos(
        self,
        person: Person,
        privacy_settings: PrivacySettings | None,
        degree: int,
        privacy_overrides: dict | None = None,
    ) -> bool:
        """Проверяет, нужно ли скрывать фото персоны."""
        if not privacy_settings:
            return False

        if privacy_settings.hide_photos and degree > privacy_settings.full_data_min_degree:
            return True

        return bool(privacy_overrides and privacy_overrides.get("hide_photos"))
