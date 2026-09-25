"""
Модель родственных связей.
"""

from django.contrib.auth.models import User
from django.db import models

from .enums import RelationshipTypeEnum


class Relationship(models.Model):
    """Родственная связь между двумя персонами."""

    from_person = models.ForeignKey(
        "Person",
        on_delete=models.CASCADE,
        related_name="relationships_from",
        verbose_name="От кого",
    )
    to_person = models.ForeignKey(
        "Person",
        on_delete=models.CASCADE,
        related_name="relationships_to",
        verbose_name="К кому",
    )
    relationship_type = models.CharField(
        max_length=20,
        choices=RelationshipTypeEnum.choices,
        verbose_name="Тип связи",
    )
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
                fields=["from_person", "to_person", "relationship_type"],
                name="unique_relationship",
            )
        ]
        indexes = [
            models.Index(fields=["from_person", "to_person"]),
            models.Index(fields=["relationship_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.from_person} → {self.to_person} ({self.get_relationship_type_display()})"
