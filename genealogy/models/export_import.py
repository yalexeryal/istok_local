"""
Модели экспорта и импорта данных.
"""

from django.contrib.auth.models import User
from django.db import models

from .enums import (
    ExportFormatEnum,
    ExportStatusEnum,
    ExportTypeEnum,
    ImportStatusEnum,
)


class ExportTask(models.Model):
    """Задача на экспорт данных."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="export_tasks", verbose_name="Пользователь")
    tree = models.ForeignKey("Tree", on_delete=models.CASCADE, related_name="export_tasks", verbose_name="Дерево")
    export_type = models.CharField(max_length=20, choices=ExportTypeEnum.choices, verbose_name="Тип экспорта")
    export_format = models.CharField(
        max_length=20,
        choices=ExportFormatEnum.choices,
        default=ExportFormatEnum.JSON_ZIP,
        verbose_name="Формат экспорта",
    )
    target_person = models.ForeignKey(
        "Person",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="export_tasks",
        verbose_name="Целевая персона",
    )
    privacy_overrides = models.JSONField(default=dict, blank=True, verbose_name="Переопределение настроек приватности")
    status = models.CharField(
        max_length=20,
        choices=ExportStatusEnum.choices,
        default=ExportStatusEnum.PENDING,
        verbose_name="Статус",
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
    """Задача на импорт данных."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="import_tasks", verbose_name="Пользователь")
    tree = models.ForeignKey(
        "Tree",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_tasks",
        verbose_name="Дерево",
    )
    import_format = models.CharField(max_length=20, choices=ExportFormatEnum.choices, verbose_name="Формат импорта")
    source_file = models.FileField(upload_to="imports/%Y/%m/%d/", verbose_name="Исходный файл")
    status = models.CharField(
        max_length=20,
        choices=ImportStatusEnum.choices,
        default=ImportStatusEnum.PENDING,
        verbose_name="Статус",
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
