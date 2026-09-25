"""
Модель событий жизни.
"""

from django.contrib.auth.models import User
from django.db import models

from .enums import EventTypeEnum


class LifeEvent(models.Model):
    """Событие жизни персоны."""

    person = models.ForeignKey(
        "Person",
        on_delete=models.CASCADE,
        related_name="life_events",
        verbose_name="Персона",
    )
    event_type = models.CharField(max_length=20, choices=EventTypeEnum.choices, verbose_name="Тип события")
    event_date = models.DateField(blank=True, null=True, verbose_name="Дата события")
    end_date = models.DateField(blank=True, null=True, verbose_name="Дата окончания")
    is_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата")
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место")
    description = models.TextField(blank=True, null=True, verbose_name="Описание")
    related_person = models.ForeignKey(
        "Person",
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
        indexes = [
            models.Index(fields=["person", "event_date"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self) -> str:
        date_str = self.event_date.strftime("%d.%m.%Y") if self.event_date else "неизвестно"
        return f"{self.get_event_type_display()} - {date_str}"
