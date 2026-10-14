"""
Модель для логирования действий в дереве.
"""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Запись лога действий пользователя."""

    class ActionEnum(models.TextChoices):
        CREATE = "CREATE", "Создание"
        UPDATE = "UPDATE", "Редактирование"
        DELETE = "DELETE", "Удаление"
        LOGIN = "LOGIN", "Вход в систему"
        EXPORT = "EXPORT", "Экспорт"
        IMPORT = "IMPORT", "Импорт"

    class EntityTypeEnum(models.TextChoices):
        PERSON = "PERSON", "Персона"
        EVENT = "EVENT", "Событие"
        RELATIONSHIP = "RELATIONSHIP", "Связь"
        PHOTO = "PHOTO", "Фотография"
        TREE = "TREE", "Дерево"
        COLLABORATOR = "COLLABORATOR", "Участник"

    tree = models.ForeignKey(
        "genealogy.Tree",
        on_delete=models.CASCADE,
        related_name="audit_logs",
        verbose_name="Дерево",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="Пользователь",
    )
    action = models.CharField(
        max_length=20,
        choices=ActionEnum.choices,
        verbose_name="Действие",
    )
    entity_type = models.CharField(
        max_length=20,
        choices=EntityTypeEnum.choices,
        verbose_name="Тип сущности",
    )
    entity_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ID сущности",
    )
    entity_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Название сущности",
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Детали",
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="IP-адрес",
    )

    class Meta:
        verbose_name = "Запись лога"
        verbose_name_plural = "Записи лога"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["tree", "-timestamp"]),
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["entity_type", "entity_id"]),
        ]

    def __str__(self):
        user_name = self.user.username if self.user else "Система"
        return f"{user_name} {self.get_action_display().lower()} {self.get_entity_type_display().lower()} '{self.entity_name}'"
