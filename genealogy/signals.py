"""
Django signals для автоматического создания связанных объектов и логирования действий.
"""

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditLog, PrivacySettings, Tree, UserProfile, UserTierEnum


@receiver(post_save, sender=User)
def create_user_profile(sender: type, instance: User, created: bool, **kwargs) -> None:
    """
    Автоматически создает UserProfile при создании нового пользователя.
    """
    if created:
        UserProfile.objects.get_or_create(user=instance, defaults={"tier": UserTierEnum.FREE})


@receiver(post_save, sender=User)
def save_user_profile(sender: type, instance: User, **kwargs) -> None:
    """
    Сохраняет связанный UserProfile при сохранении пользователя.
    """
    if hasattr(instance, "profile"):
        instance.profile.save()


@receiver(post_save, sender=User)
def create_privacy_settings(sender: type, instance: User, created: bool, **kwargs) -> None:
    """
    Автоматически создает PrivacySettings при создании нового пользователя.
    """
    if created:
        PrivacySettings.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_privacy_settings(sender: type, instance: User, **kwargs) -> None:
    """
    Сохраняет связанный PrivacySettings при сохранении пользователя.
    """
    if hasattr(instance, "privacy_settings"):
        instance.privacy_settings.save()


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    """
    Логирует вход пользователя в систему во все доступные ему деревья.
    """
    # Находим деревья, где пользователь является соавтором ИЛИ дерево публичное
    accessible_trees = Tree.objects.filter(Q(collaborators__user=user) | Q(is_public=True)).distinct()

    # Получаем IP-адрес
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip_address = x_forwarded_for.split(",")[0].strip()
    else:
        ip_address = request.META.get("REMOTE_ADDR")

    # Получаем User-Agent (браузер и ОС)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:200]

    # Логируем вход в каждое доступное дерево
    for tree in accessible_trees:
        AuditLog.objects.create(
            tree=tree,
            user=user,
            action="LOGIN",
            entity_type="TREE",
            entity_name="Вход в систему",
            details={"user_agent": user_agent},
            ip_address=ip_address,
        )
