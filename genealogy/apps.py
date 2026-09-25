from django.apps import AppConfig


class GenealogyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "genealogy"
    verbose_name = "Генеалогия"

    def ready(self) -> None:
        """
        Подключаем сигналы при загрузке приложения.
        """
        # Импортируем signals, чтобы они зарегистрировались
        from . import signals  # noqa: F401
