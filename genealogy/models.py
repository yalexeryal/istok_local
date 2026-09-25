"""
Модели данных для генеалогического приложения istok_local.
"""

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone


class GenderEnum(models.TextChoices):
    MALE = "male", "Мужской"
    FEMALE = "female", "Женский"
    UNKNOWN = "unknown", "Неизвестно"


class EventTypeEnum(models.TextChoices):
    BIRTH = "birth", "Рождение"
    DEATH = "death", "Смерть"
    MARRIAGE = "marriage", "Брак"
    DIVORCE = "divorce", "Развод"
    BIRTH_OF_CHILD = "birth_of_child", "Рождение ребенка"
    EDUCATION = "education", "Образование"
    WORK = "work", "Работа"
    MILITARY_SERVICE = "military", "Военная служба"
    MIGRATION = "migration", "Миграция"
    RELIGIOUS_EVENT = "religious_event", "Религиозное событие"
    OTHER = "other", "Другое"


class RelationshipTypeEnum(models.TextChoices):
    BIOLOGICAL_PARENT = "biological_parent", "Биологический родитель"
    ADOPTIVE_PARENT = "adoptive_parent", "Приемный родитель"
    STEP_PARENT = "step_parent", "Отчим/мачеха"
    SPOUSE = "spouse", "Супруг(а)"
    EX_SPOUSE = "ex_spouse", "Бывший супруг(а)"
    FIANCE = "fiance", "Жених/невеста"
    GUARDIAN = "guardian", "Опекун"
    GODPARENT = "godparent", "Крестный родитель"


class CollaboratorRoleEnum(models.TextChoices):
    OWNER = "owner", "Владелец"
    EDITOR = "editor", "Редактор"
    VIEWER = "viewer", "Читатель"


class ChangeRequestStatusEnum(models.TextChoices):
    PENDING = "pending", "Ожидает"
    APPROVED = "approved", "Одобрен"
    REJECTED = "rejected", "Отклонен"
    AUTO_APPROVED = "auto_approved", "Автоматически одобрен"


class PersonStatusEnum(models.TextChoices):
    SANDBOX = "sandbox", "Черновик"
    PUBLISHED = "published", "Опубликовано"
    MERGED = "merged", "Объединена"


class UserTierEnum(models.TextChoices):
    FREE = "free", "Бесплатный"
    ONE_TIME = "one_time", "Единоразовая оплата"
    SUBSCRIPTION = "subscription", "Подписка"


class ExportTypeEnum(models.TextChoices):
    FULL = "full", "Полная выгрузка"
    RELATIVE = "relative", "Для родственника"
    PUBLIC = "public", "Публичная версия"


class ExportFormatEnum(models.TextChoices):
    JSON_ZIP = "json_zip", "JSON + ZIP"
    GEDCOM = "gedcom", "GEDCOM"


class ExportStatusEnum(models.TextChoices):
    PENDING = "pending", "Ожидает"
    PROCESSING = "processing", "В процессе"
    COMPLETED = "completed", "Завершён"
    FAILED = "failed", "Ошибка"


class ImportStatusEnum(models.TextChoices):
    PENDING = "pending", "Ожидает"
    PROCESSING = "processing", "В процессе"
    COMPLETED = "completed", "Завершён"
    FAILED = "failed", "Ошибка"


class Tree(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Название")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    is_public = models.BooleanField(default=False, verbose_name="Публичное дерево")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    sync_version = models.IntegerField(default=0, verbose_name="Версия синхронизации")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "Дерево"
        verbose_name_plural = "Деревья"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("genealogy:tree_detail", kwargs={"pk": self.pk})

    def get_owner(self) -> User | None:
        collaborator = self.collaborators.filter(role=CollaboratorRoleEnum.OWNER).first()
        return collaborator.user if collaborator else None

    def user_can_edit(self, user: User) -> bool:
        if user.is_superuser:
            return True
        return self.collaborators.filter(
            user=user, role__in=[CollaboratorRoleEnum.OWNER, CollaboratorRoleEnum.EDITOR]
        ).exists()

    def user_can_view(self, user: User) -> bool:
        if self.is_public or user.is_superuser:
            return True
        return self.collaborators.filter(user=user).exists()

    def get_persons_count(self) -> int:
        return self.persons.count()


class Person(models.Model):
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    middle_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Отчество")
    last_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Фамилия")
    maiden_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Девичья фамилия")
    birth_date = models.DateField(blank=True, null=True, verbose_name="Дата рождения")
    is_birth_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата рождения")
    death_date = models.DateField(blank=True, null=True, verbose_name="Дата смерти")
    is_death_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата смерти")
    birth_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место рождения")
    death_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место смерти")
    burial_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место захоронения")
    gender = models.CharField(max_length=10, choices=GenderEnum.choices, default=GenderEnum.UNKNOWN, verbose_name="Пол")
    culture = models.CharField(max_length=50, blank=True, null=True, verbose_name="Культура/Национальность")
    photo = models.ImageField(upload_to="persons/photos/%Y/%m/%d/", blank=True, null=True, verbose_name="Фотография")
    notes = models.TextField(blank=True, null=True, verbose_name="Заметки")
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="persons", verbose_name="Дерево")
    status = models.CharField(
        max_length=20, choices=PersonStatusEnum.choices, default=PersonStatusEnum.SANDBOX, verbose_name="Статус"
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="merged_persons",
        verbose_name="Объединена с",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_persons",
        verbose_name="Кем обновлено",
    )
    sync_version = models.IntegerField(default=0, verbose_name="Версия синхронизации")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "Персона"
        verbose_name_plural = "Персоны"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(fields=["first_name", "last_name", "tree"], name="unique_person_in_tree")
        ]
        indexes = [models.Index(fields=["last_name", "first_name"]), models.Index(fields=["tree", "status"])]

    def __str__(self) -> str:
        return self.full_name_display

    def get_absolute_url(self) -> str:
        return reverse("genealogy:person_detail", kwargs={"pk": self.pk})

    @property
    def full_name_display(self) -> str:
        parts = []
        if self.maiden_name and self.gender == GenderEnum.FEMALE:
            parts.append(f"{self.last_name} ({self.maiden_name})")
        elif self.last_name:
            parts.append(self.last_name)
        parts.append(self.first_name)
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)

    @property
    def age(self) -> int | None:
        if not self.birth_date:
            return None
        end_date = self.death_date or timezone.now().date()
        age = end_date.year - self.birth_date.year
        if (end_date.month, end_date.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1
        return age

    @property
    def is_alive(self) -> bool:
        return self.death_date is None

    def get_parents(self):
        parent_relationships = self.relationships_to.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(relationships_from__in=parent_relationships).distinct()

    def get_children(self):
        child_relationships = self.relationships_from.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(relationships_to__in=child_relationships).distinct()

    def get_siblings(self):
        parents = self.get_parents()
        if not parents.exists():
            return Person.objects.none()
        return (
            Person.objects.filter(
                tree=self.tree,
                relationships_to__from_person__in=parents,
                relationships_to__relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ],
            )
            .exclude(pk=self.pk)
            .distinct()
        )

    def get_spouses(self):
        """Возвращает всех супругов/партнеров персоны."""
        spouse_rels = Relationship.objects.filter(
            models.Q(
                from_person=self,
                relationship_type__in=[
                    RelationshipTypeEnum.SPOUSE,
                    RelationshipTypeEnum.EX_SPOUSE,
                    RelationshipTypeEnum.FIANCE,
                ],
            )
            | models.Q(
                to_person=self,
                relationship_type__in=[
                    RelationshipTypeEnum.SPOUSE,
                    RelationshipTypeEnum.EX_SPOUSE,
                    RelationshipTypeEnum.FIANCE,
                ],
            )
        ).distinct()
        spouses = []
        for rel in spouse_rels:
            partner = rel.to_person if rel.from_person == self else rel.from_person
            spouses.append(
                {
                    "person": partner,
                    "relationship": rel,
                    "type": rel.relationship_type,
                }
            )
        return spouses

    def get_combined_timeline(self):
        """
        Собирает объединенную хронологию жизни персоны.

        Включает:
        - Собственные события (включая браки/разводы из связей)
        - Рождение детей
        - Смерть родителей

        НЕ включает:
        - События "Рождение ребенка" как события родственников (чтобы избежать задвоения)

        Сортировка браков без даты:
        - Если есть совместные дети — перед рождением первого ребенка
        - Иначе — в самом конце хронологии
        """
        timeline = []

        # 1. Собственные события (исключая BIRTH_OF_CHILD, чтобы не было задвоения)
        for event in self.life_events.exclude(event_type=EventTypeEnum.BIRTH_OF_CHILD):
            if event.event_date:
                timeline.append(
                    {
                        "date": event.event_date,
                        "title": event.get_event_type_display(),
                        "description": event.description or "",
                        "location": event.location or "",
                        "type": "own",
                        "related_person": event.related_person,
                        "event_obj": event,
                        "has_date": True,
                    }
                )
            else:
                # События без даты добавим позже
                timeline.append(
                    {
                        "date": None,
                        "title": event.get_event_type_display(),
                        "description": event.description or "",
                        "location": event.location or "",
                        "type": "own",
                        "related_person": event.related_person,
                        "event_obj": event,
                        "has_date": False,
                    }
                )

        # 2. Браки и разводы из связей (как собственные события)
        for spouse_info in self.get_spouses():
            rel = spouse_info["relationship"]
            partner = spouse_info["person"]

            if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
                title = f"Брак с {partner.full_name_display}"
            elif rel.relationship_type == RelationshipTypeEnum.EX_SPOUSE:
                title = f"Развод с {partner.full_name_display}"
            else:
                title = f"Помолвка с {partner.full_name_display}"

            if rel.start_date:
                timeline.append(
                    {
                        "date": rel.start_date,
                        "title": title,
                        "description": rel.description or "",
                        "location": "",
                        "type": "own",
                        "related_person": partner,
                        "event_obj": None,
                        "has_date": True,
                        "relationship_obj": rel,
                    }
                )
            else:
                # Брак без даты — добавим позже с учетом детей
                timeline.append(
                    {
                        "date": None,
                        "title": title,
                        "description": rel.description or "",
                        "location": "",
                        "type": "own",
                        "related_person": partner,
                        "event_obj": None,
                        "has_date": False,
                        "relationship_obj": rel,
                    }
                )

        # 3. Рождение детей
        children_birth_dates = []
        for child in self.get_children():
            if child.birth_date:
                children_birth_dates.append(child.birth_date)
                timeline.append(
                    {
                        "date": child.birth_date,
                        "title": f"Рождение {'сына' if child.gender == 'male' else 'дочери'}: {child.full_name_display}",
                        "description": "",
                        "location": child.birth_place or "",
                        "type": "relative",
                        "related_person": child,
                        "event_obj": None,
                        "has_date": True,
                    }
                )

        # 4. Смерть родителей
        for parent in self.get_parents():
            if parent.death_date:
                timeline.append(
                    {
                        "date": parent.death_date,
                        "title": f"Смерть родителя: {parent.full_name_display}",
                        "description": "",
                        "location": parent.death_place or "",
                        "type": "relative",
                        "related_person": parent,
                        "event_obj": None,
                        "has_date": True,
                    }
                )

        # 5. Обработка событий без даты
        # Находим самую раннюю дату рождения ребенка (если есть)
        earliest_child_birth = min(children_birth_dates) if children_birth_dates else None

        # События без даты:
        # - Браки без даты — перед рождением первого ребенка (если есть) или в конце
        # - Другие события без даты — в конце
        no_date_events = [item for item in timeline if not item["has_date"]]
        dated_events = [item for item in timeline if item["has_date"]]

        # Сортируем события с датами
        dated_events.sort(key=lambda x: x["date"])

        # Разделяем события без даты на браки и остальные
        marriages_no_date = [item for item in no_date_events if item.get("relationship_obj")]
        other_no_date = [item for item in no_date_events if not item.get("relationship_obj")]

        # Собираем итоговую хронологию
        final_timeline = []

        if earliest_child_birth:
            # Добавляем события до рождения первого ребенка
            for item in dated_events:
                if item["date"] < earliest_child_birth:
                    final_timeline.append(item)

            # Добавляем браки без даты (перед детьми)
            final_timeline.extend(marriages_no_date)

            # Добавляем оставшиеся события с датами
            for item in dated_events:
                if item["date"] >= earliest_child_birth:
                    final_timeline.append(item)
        else:
            # Нет детей — все события с датами
            final_timeline.extend(dated_events)

        # В конце — остальные события без даты
        final_timeline.extend(other_no_date)

        return final_timeline


class LifeEvent(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="life_events", verbose_name="Персона")
    event_type = models.CharField(max_length=20, choices=EventTypeEnum.choices, verbose_name="Тип события")
    event_date = models.DateField(blank=True, null=True, verbose_name="Дата события")
    end_date = models.DateField(blank=True, null=True, verbose_name="Дата окончания")
    is_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата")
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    related_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="related_events",
        verbose_name="Связанная персона",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_events",
        verbose_name="Кем создано",
    )
    sync_version = models.IntegerField(default=0, verbose_name="Версия синхронизации")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "Событие жизни"
        verbose_name_plural = "События жизни"
        ordering = ["event_date"]
        indexes = [models.Index(fields=["person", "event_date"]), models.Index(fields=["event_type"])]

    def __str__(self) -> str:
        date_str = self.event_date.strftime("%d.%m.%Y") if self.event_date else "неизвестно"
        return f"{self.get_event_type_display()} - {date_str}"


class Relationship(models.Model):
    from_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="relationships_from", verbose_name="От кого"
    )
    to_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="relationships_to", verbose_name="К кому"
    )
    relationship_type = models.CharField(max_length=20, choices=RelationshipTypeEnum.choices, verbose_name="Тип связи")
    start_date = models.DateField(blank=True, null=True, verbose_name="Дата начала")
    end_date = models.DateField(blank=True, null=True, verbose_name="Дата окончания")
    is_current = models.BooleanField(default=True, verbose_name="Текущая связь")
    description = models.CharField(max_length=255, blank=True, null=True, verbose_name="Описание")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_relationships",
        verbose_name="Кем создано",
    )
    sync_version = models.IntegerField(default=0, verbose_name="Версия синхронизации")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "Родственная связь"
        verbose_name_plural = "Родственные связи"
        constraints = [
            models.UniqueConstraint(
                fields=["from_person", "to_person", "relationship_type"], name="unique_relationship"
            )
        ]
        indexes = [models.Index(fields=["from_person", "to_person"]), models.Index(fields=["relationship_type"])]

    def __str__(self) -> str:
        return f"{self.from_person} → {self.to_person} ({self.get_relationship_type_display()})"


class TreeCollaborator(models.Model):
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="collaborators", verbose_name="Дерево")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tree_collaborations", verbose_name="Пользователь"
    )
    role = models.CharField(
        max_length=20, choices=CollaboratorRoleEnum.choices, default=CollaboratorRoleEnum.VIEWER, verbose_name="Роль"
    )
    can_invite = models.BooleanField(default=False, verbose_name="Может приглашать других")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Соавтор дерева"
        verbose_name_plural = "Соавторы деревьев"
        constraints = [models.UniqueConstraint(fields=["tree", "user"], name="unique_collaborator_per_tree")]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.tree.name} ({self.get_role_display()})"


class ChangeRequest(models.Model):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="change_requests", verbose_name="Персона")
    requested_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="requested_changes", verbose_name="Кем запрошено"
    )
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="owned_change_requests", verbose_name="Владелец дерева"
    )
    change_type = models.CharField(max_length=50, verbose_name="Тип изменения")
    proposed_data = models.JSONField(blank=True, null=True, verbose_name="Предложенные данные")
    status = models.CharField(
        max_length=20,
        choices=ChangeRequestStatusEnum.choices,
        default=ChangeRequestStatusEnum.PENDING,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    responded_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата ответа")
    response_comment = models.TextField(blank=True, null=True, verbose_name="Комментарий к ответу")

    class Meta:
        verbose_name = "Запрос на изменение"
        verbose_name_plural = "Запросы на изменения"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Запрос #{self.pk} для {self.person} ({self.get_status_display()})"


class PrivacySettings(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="privacy_settings", verbose_name="Пользователь"
    )
    hide_birth_date = models.BooleanField(default=False, verbose_name="Скрывать дату рождения")
    hide_death_date = models.BooleanField(default=False, verbose_name="Скрывать дату смерти")
    hide_birth_place = models.BooleanField(default=False, verbose_name="Скрывать место рождения")
    hide_death_place = models.BooleanField(default=False, verbose_name="Скрывать место смерти")
    hide_notes = models.BooleanField(default=True, verbose_name="Скрывать заметки")
    hide_photos = models.BooleanField(default=False, verbose_name="Скрывать фотографии")
    full_data_min_degree = models.IntegerField(default=2, verbose_name="Минимальная степень родства для полных данных")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Настройки приватности"
        verbose_name_plural = "Настройки приватности"

    def __str__(self) -> str:
        return f"Настройки приватности для {self.user.username}"


class ExportTask(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="export_tasks", verbose_name="Пользователь")
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="export_tasks", verbose_name="Дерево")
    export_type = models.CharField(max_length=20, choices=ExportTypeEnum.choices, verbose_name="Тип экспорта")
    export_format = models.CharField(
        max_length=20,
        choices=ExportFormatEnum.choices,
        default=ExportFormatEnum.JSON_ZIP,
        verbose_name="Формат экспорта",
    )
    target_person = models.ForeignKey(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_tasks",
        verbose_name="Целевая персона",
    )
    privacy_overrides = models.JSONField(default=dict, blank=True, verbose_name="Переопределение настроек приватности")
    status = models.CharField(
        max_length=20, choices=ExportStatusEnum.choices, default=ExportStatusEnum.PENDING, verbose_name="Статус"
    )
    file = models.FileField(upload_to="exports/%Y/%m/%d/", null=True, blank=True, verbose_name="Файл экспорта")
    file_size = models.BigIntegerField(null=True, blank=True, verbose_name="Размер файла (байт)")
    person_count = models.IntegerField(null=True, blank=True, verbose_name="Количество экспортированных персон")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    error_message = models.TextField(null=True, blank=True, verbose_name="Сообщение об ошибке")

    class Meta:
        verbose_name = "Задача экспорта"
        verbose_name_plural = "Задачи экспорта"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Экспорт #{self.pk} ({self.get_export_type_display()})"


class ImportTask(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="import_tasks", verbose_name="Пользователь")
    tree = models.ForeignKey(
        Tree, on_delete=models.SET_NULL, null=True, blank=True, related_name="import_tasks", verbose_name="Дерево"
    )
    import_format = models.CharField(max_length=20, choices=ExportFormatEnum.choices, verbose_name="Формат импорта")
    source_file = models.FileField(upload_to="imports/%Y/%m/%d/", verbose_name="Исходный файл")
    status = models.CharField(
        max_length=20, choices=ImportStatusEnum.choices, default=ImportStatusEnum.PENDING, verbose_name="Статус"
    )
    person_count = models.IntegerField(null=True, blank=True, verbose_name="Количество импортированных персон")
    relationship_count = models.IntegerField(null=True, blank=True, verbose_name="Количество импортированных связей")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Дата завершения")
    error_message = models.TextField(null=True, blank=True, verbose_name="Сообщение об ошибке")

    class Meta:
        verbose_name = "Задача импорта"
        verbose_name_plural = "Задачи импорта"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Импорт #{self.pk} ({self.get_import_format_display()})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь")
    tier = models.CharField(
        max_length=20, choices=UserTierEnum.choices, default=UserTierEnum.FREE, verbose_name="Тариф"
    )
    tier_expires_at = models.DateTimeField(null=True, blank=True, verbose_name="Срок действия тарифа")
    devices_count = models.IntegerField(default=1, verbose_name="Количество устройств")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def __str__(self) -> str:
        return f"Профиль {self.user.username} ({self.get_tier_display()})"

    def can_add_person(self, tree: Tree) -> bool:
        from django.conf import settings

        tier_limits = settings.TIER_LIMITS.get(self.tier, {})
        max_persons = tier_limits.get("max_persons_per_tree")
        if max_persons is None:
            return True
        return tree.get_persons_count() < max_persons
