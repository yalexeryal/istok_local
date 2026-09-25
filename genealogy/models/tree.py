"""
Модели для генеалогических деревьев и соавторов.
"""

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse

from .enums import CollaboratorRoleEnum


class Tree(models.Model):
    """Генеалогическое дерево."""

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
        """Получить владельца дерева."""
        collaborator = self.collaborators.filter(role=CollaboratorRoleEnum.OWNER).first()
        return collaborator.user if collaborator else None

    def user_can_edit(self, user: User) -> bool:
        """Проверить, может ли пользователь редактировать дерево."""
        if user.is_superuser:
            return True
        return self.collaborators.filter(
            user=user,
            role__in=[CollaboratorRoleEnum.OWNER, CollaboratorRoleEnum.EDITOR],
        ).exists()

    def user_can_view(self, user: User) -> bool:
        """Проверить, может ли пользователь просматривать дерево."""
        if self.is_public or user.is_superuser:
            return True
        return self.collaborators.filter(user=user).exists()

    def get_persons_count(self) -> int:
        """Получить количество персон в дереве."""
        return self.persons.count()


class TreeCollaborator(models.Model):
    """Соавтор дерева."""

    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="collaborators", verbose_name="Дерево")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tree_collaborations", verbose_name="Пользователь"
    )
    role = models.CharField(
        max_length=20,
        choices=CollaboratorRoleEnum.choices,
        default=CollaboratorRoleEnum.VIEWER,
        verbose_name="Роль",
    )
    can_invite = models.BooleanField(default=False, verbose_name="Может приглашать других")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    class Meta:
        verbose_name = "Соавтор дерева"
        verbose_name_plural = "Соавторы деревьев"
        constraints = [models.UniqueConstraint(fields=["tree", "user"], name="unique_collaborator_per_tree")]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.tree.name} ({self.get_role_display()})"
