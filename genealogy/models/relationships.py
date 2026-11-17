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

    def clean(self):
        """
        Валидация на уровне модели для обеспечения целостности связей.
        """
        from django.core.exceptions import ValidationError

        from .enums import RelationshipTypeEnum

        super().clean()

        if self.from_person and self.to_person:
            # 1. Запрет связи с самим собой
            if self.from_person.pk == self.to_person.pk:
                raise ValidationError("Нельзя создать связь персоны с самой собой.")

            # 2. Запрет связей между разными деревьями
            if self.from_person.tree_id != self.to_person.tree_id:
                raise ValidationError("Обе персоны должны принадлежать одному и тому же дереву.")

            # 3. Запрет циклов в родительских связях
            parent_types = [
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]

            if self.relationship_type in parent_types:
                # Мы добавляем: from_person (родитель) -> to_person (ребенок).
                # Цикл возникнет, если from_person УЖЕ является потомком to_person.
                # Ищем всех предков from_person. Если среди них есть to_person, это цикл.
                visited = set()
                queue = [self.from_person]

                while queue:
                    current = queue.pop(0)
                    if current.pk == self.to_person.pk:
                        raise ValidationError(
                            f"Невозможно создать связь: это создаст цикл в генеалогическом дереве. "
                            f'"{self.from_person.full_name_display}" уже является потомком '
                            f'"{self.to_person.full_name_display}".'
                        )

                    if current.pk in visited:
                        continue
                    visited.add(current.pk)

                    # Находим родителей текущей персоны
                    parent_rels = Relationship.objects.filter(to_person=current, relationship_type__in=parent_types)
                    for rel in parent_rels:
                        queue.append(rel.from_person)
