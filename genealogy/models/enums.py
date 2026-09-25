"""
Перечисления (TextChoices) для приложения genealogy.
"""

from django.db import models


class GenderEnum(models.TextChoices):
    """Пол персоны."""

    MALE = "male", "Мужской"
    FEMALE = "female", "Женский"
    UNKNOWN = "unknown", "Неизвестно"


class EventTypeEnum(models.TextChoices):
    """Типы событий жизни."""

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
    """Типы родственных связей."""

    BIOLOGICAL_PARENT = "biological_parent", "Биологический родитель"
    ADOPTIVE_PARENT = "adoptive_parent", "Приемный родитель"
    STEP_PARENT = "step_parent", "Отчим/мачеха"
    SPOUSE = "spouse", "Супруг(а)"
    EX_SPOUSE = "ex_spouse", "Бывший супруг(а)"
    FIANCE = "fiance", "Жених/невеста"
    GUARDIAN = "guardian", "Опекун"
    GODPARENT = "godparent", "Крестный родитель"


class CollaboratorRoleEnum(models.TextChoices):
    """Роли соавторов дерева."""

    OWNER = "owner", "Владелец"
    EDITOR = "editor", "Редактор"
    VIEWER = "viewer", "Читатель"


class ChangeRequestStatusEnum(models.TextChoices):
    """Статусы запросов на изменение."""

    PENDING = "pending", "Ожидает"
    APPROVED = "approved", "Одобрен"
    REJECTED = "rejected", "Отклонен"
    AUTO_APPROVED = "auto_approved", "Автоматически одобрен"


class PersonStatusEnum(models.TextChoices):
    """Статусы персон."""

    SANDBOX = "sandbox", "Черновик"
    PUBLISHED = "published", "Опубликовано"
    MERGED = "merged", "Объединена"


class UserTierEnum(models.TextChoices):
    """Тарифы пользователей."""

    FREE = "free", "Бесплатный"
    ONE_TIME = "one_time", "Единоразовая оплата"
    SUBSCRIPTION = "subscription", "Подписка"


class ExportTypeEnum(models.TextChoices):
    """Типы экспорта."""

    FULL = "full", "Полная выгрузка"
    RELATIVE = "relative", "Для родственника"
    PUBLIC = "public", "Публичная версия"


class ExportFormatEnum(models.TextChoices):
    """Форматы экспорта."""

    JSON_ZIP = "json_zip", "JSON + ZIP"
    GEDCOM = "gedcom", "GEDCOM"


class ExportStatusEnum(models.TextChoices):
    """Статусы задач экспорта."""

    PENDING = "pending", "Ожидает"
    PROCESSING = "processing", "В процессе"
    COMPLETED = "completed", "Завершён"
    FAILED = "failed", "Ошибка"


class ImportStatusEnum(models.TextChoices):
    """Статусы задач импорта."""

    PENDING = "pending", "Ожидает"
    PROCESSING = "processing", "В процессе"
    COMPLETED = "completed", "Завершён"
    FAILED = "failed", "Ошибка"
