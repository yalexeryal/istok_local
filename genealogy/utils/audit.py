"""
Утилиты для логирования действий.
"""

from genealogy.models import AuditLog


def log_action(
    tree,
    user,
    action,
    entity_type,
    entity_id=None,
    entity_name="",
    details=None,
    ip_address=None,
):
    """
    Создаёт запись в логе действий.

    Args:
        tree: Дерево, к которому относится действие
        user: Пользователь, совершивший действие
        action: Тип действия (CREATE/UPDATE/DELETE)
        entity_type: Тип сущности (PERSON/EVENT/RELATIONSHIP/PHOTO)
        entity_id: ID сущности (опционально)
        entity_name: Название сущности для отображения
        details: Словарь с дополнительными деталями
        ip_address: IP-адрес пользователя
    """
    AuditLog.objects.create(
        tree=tree,
        user=user,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name[:255],
        details=details or {},
        ip_address=ip_address,
    )


def get_client_ip(request):
    """Извлекает IP-адрес клиента из запроса."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
