"""
Модели пользователей и настроек приватности.
"""

from django.contrib.auth.models import User
from django.db import models

from .enums import ChangeRequestStatusEnum, UserTierEnum


class UserProfile(models.Model):
    """Профиль пользователя с тарифом."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", verbose_name="Пользователь")
    tier = models.CharField(
        max_length=20,
        choices=UserTierEnum.choices,
        default=UserTierEnum.FREE,
        verbose_name="Тариф",
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

    def can_add_person(self, tree) -> bool:
        """Проверить, может ли пользователь добавить персону в дерево."""
        from django.conf import settings

        tier_limits = settings.TIER_LIMITS.get(self.tier, {})
        max_persons = tier_limits.get("max_persons_per_tree")
        if max_persons is None:
            return True
        return tree.get_persons_count() < max_persons


class PrivacySettings(models.Model):
    """Настройки приватности пользователя."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="privacy_settings", verbose_name="Пользователь"
    )
    hide_birth_date = models.BooleanField(default=False, verbose_name="Скрывать дату рождения")
    hide_death_date = models.BooleanField(default=False, verbose_name="Скрывать дату смерти")
    hide_birth_place = models.BooleanField(default=False, verbose_name="Скрывать место рождения")
    hide_death_place = models.BooleanField(default=False, verbose_name="Скрывать место смерти")
    hide_notes = models.BooleanField(default=True, verbose_name="Скрывать заметки")
    hide_photos = models.BooleanField(default=False, verbose_name="Скрывать фотографии")
    full_data_min_degree = models.IntegerField(
        default=2,
        verbose_name="Минимальная степень родства для полных данных",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")

    class Meta:
        verbose_name = "Настройки приватности"
        verbose_name_plural = "Настройки приватности"

    def __str__(self) -> str:
        return f"Настройки приватности для {self.user.username}"


class ChangeRequest(models.Model):
    """Запрос на изменение персоны."""

    person = models.ForeignKey(
        "Person",
        on_delete=models.CASCADE,
        related_name="change_requests",
        verbose_name="Персона",
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="requested_changes",
        verbose_name="Кем запрошено",
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="owned_change_requests",
        verbose_name="Владелец дерева",
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
