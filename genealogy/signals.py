"""
Django signals для автоматического создания UserProfile.
"""
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile, UserTierEnum


@receiver(post_save, sender=User)
def create_user_profile(sender: type, instance: User, created: bool, **kwargs) -> None:
    """
    Автоматически создает UserProfile при создании нового пользователя.

    Args:
        sender: Класс модели (User)
        instance: Экземпляр пользователя
        created: True, если пользователь только что создан
    """
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={'tier': UserTierEnum.FREE}
        )


@receiver(post_save, sender=User)
def save_user_profile(sender: type, instance: User, **kwargs) -> None:
    """
    Сохраняет связанный UserProfile при сохранении пользователя.
    """
    if hasattr(instance, 'profile'):
        instance.profile.save()