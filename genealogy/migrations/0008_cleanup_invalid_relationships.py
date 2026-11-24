"""
Data migration для очистки некорректных связей:
- Связи персоны с самой собой
- Связи между разными деревьями
"""

from django.db import migrations, models


def cleanup_invalid_relationships(apps, schema_editor):
    """Удаляет все связи, которые нарушают правила целостности."""
    Relationship = apps.get_model("genealogy", "Relationship")

    # 1. Удаляем связи персоны с самой собой
    self_refs = Relationship.objects.filter(from_person_id=models.F("to_person_id"))
    self_refs_count = self_refs.count()
    self_refs.delete()

    # 2. Удаляем связи между разными деревьями
    cross_tree = Relationship.objects.exclude(
        from_person__tree_id=models.F("to_person__tree_id")
    )
    cross_tree_count = cross_tree.count()
    cross_tree.delete()

    print(f"\n🧹 Очищено некорректных связей:")
    print(f"   - Связей с самим собой: {self_refs_count}")
    print(f"   - Связей между разными деревьями: {cross_tree_count}")


def reverse_cleanup(apps, schema_editor):
    """Обратная миграция не нужна — данные уже удалены."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("genealogy", "0007_auditlog"),
    ]

    operations = [
        migrations.RunPython(cleanup_invalid_relationships, reverse_cleanup),
    ]