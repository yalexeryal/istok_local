"""
Django signals для автоматического создания связанных объектов.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PrivacySettings, UserProfile, UserTierEnum


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
