"""
Модель Person и связанные методы.
"""

from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.utils import timezone

from .enums import (
    EventTypeEnum,
    GenderEnum,
    PersonStatusEnum,
    RelationshipTypeEnum,
)


class Person(models.Model):
    """Персона в генеалогическом дереве."""

    first_name = models.CharField(max_length=100, verbose_name="Имя")
    middle_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Отчество")
    last_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Фамилия")
    maiden_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Девичья фамилия")
    birth_date = models.DateField(blank=True, null=True, verbose_name="Дата рождения")
    is_birth_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата рождения")
    death_date = models.DateField(blank=True, null=True, verbose_name="Дата смерти")
    is_death_date_approx = models.BooleanField(default=False, verbose_name="Приблизительная дата смерти")
    birth_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место рождения")
    death_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место смерти")
    burial_place = models.CharField(max_length=255, blank=True, null=True, verbose_name="Место захоронения")
    gender = models.CharField(
        max_length=10,
        choices=GenderEnum.choices,
        default=GenderEnum.UNKNOWN,
        verbose_name="Пол",
    )
    culture = models.CharField(max_length=50, blank=True, null=True, verbose_name="Культура/Национальность")
    photo = models.ImageField(upload_to="persons/photos/%Y/%m/%d/", blank=True, null=True, verbose_name="Фотография")
    notes = models.TextField(blank=True, null=True, verbose_name="Заметки")
    tree = models.ForeignKey("Tree", on_delete=models.CASCADE, related_name="persons", verbose_name="Дерево")
    status = models.CharField(
        max_length=20,
        choices=PersonStatusEnum.choices,
        default=PersonStatusEnum.SANDBOX,
        verbose_name="Статус",
    )
    merged_into = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="merged_persons",
        verbose_name="Объединена с",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Дата обновления")
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="updated_persons",
        verbose_name="Кем обновлено",
    )
    sync_version = models.IntegerField(default=0, verbose_name="Версия синхронизации")
    last_synced_at = models.DateTimeField(null=True, blank=True, verbose_name="Последняя синхронизация")

    class Meta:
        verbose_name = "Персона"
        verbose_name_plural = "Персоны"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(fields=["first_name", "last_name", "tree"], name="unique_person_in_tree")
        ]
        indexes = [
            models.Index(fields=["last_name", "first_name"]),
            models.Index(fields=["tree", "status"]),
        ]

    def __str__(self) -> str:
        return self.full_name_display

    def get_absolute_url(self) -> str:
        return reverse("genealogy:person_detail", kwargs={"pk": self.pk})

    @property
    def full_name_display(self) -> str:
        """Полное имя для отображения."""
        parts = []
        if self.maiden_name and self.gender == GenderEnum.FEMALE:
            parts.append(f"{self.last_name} ({self.maiden_name})")
        elif self.last_name:
            parts.append(self.last_name)
        parts.append(self.first_name)
        if self.middle_name:
            parts.append(self.middle_name)
        return " ".join(parts)

    @property
    def age(self) -> int | None:
        """Возраст персоны."""
        if not self.birth_date:
            return None
        end_date = self.death_date or timezone.now().date()
        age = end_date.year - self.birth_date.year
        if (end_date.month, end_date.day) < (self.birth_date.month, self.birth_date.day):
            age -= 1
        return age

    @property
    def is_alive(self) -> bool:
        """Жива ли персона."""
        return self.death_date is None

    def get_parents(self):
        """Получить родителей персоны."""
        parent_relationships = self.relationships_to.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(relationships_from__in=parent_relationships).distinct()

    def get_children(self):
        """Получить детей персоны."""
        child_relationships = self.relationships_from.filter(
            relationship_type__in=[
                RelationshipTypeEnum.BIOLOGICAL_PARENT,
                RelationshipTypeEnum.ADOPTIVE_PARENT,
                RelationshipTypeEnum.STEP_PARENT,
            ]
        )
        return Person.objects.filter(relationships_to__in=child_relationships).distinct()

    def get_siblings(self):
        """Получить братьев и сестер."""
        parents = self.get_parents()
        if not parents.exists():
            return Person.objects.none()
        return (
            Person.objects.filter(
                tree=self.tree,
                relationships_to__from_person__in=parents,
                relationships_to__relationship_type__in=[
                    RelationshipTypeEnum.BIOLOGICAL_PARENT,
                    RelationshipTypeEnum.ADOPTIVE_PARENT,
                    RelationshipTypeEnum.STEP_PARENT,
                ],
            )
            .exclude(pk=self.pk)
            .distinct()
        )

    def get_spouses(self):
        """Получить всех супругов/партнеров персоны."""
        spouse_rels = models.Q(
            from_person=self,
            relationship_type__in=[
                RelationshipTypeEnum.SPOUSE,
                RelationshipTypeEnum.EX_SPOUSE,
                RelationshipTypeEnum.FIANCE,
            ],
        ) | models.Q(
            to_person=self,
            relationship_type__in=[
                RelationshipTypeEnum.SPOUSE,
                RelationshipTypeEnum.EX_SPOUSE,
                RelationshipTypeEnum.FIANCE,
            ],
        )

        from .relationships import Relationship

        relationships = Relationship.objects.filter(spouse_rels).distinct()

        spouses = []
        for rel in relationships:
            partner = rel.to_person if rel.from_person == self else rel.from_person
            spouses.append(
                {
                    "person": partner,
                    "relationship": rel,
                    "type": rel.relationship_type,
                }
            )
        return spouses

    def get_combined_timeline(self):
        """
        Собирает объединенную хронологию жизни персоны.

        Включает:
        - Собственные события (кроме BIRTH_OF_CHILD)
        - Браки и разводы из связей
        - Рождение детей
        - Смерть родителей

        НЕ включает:
        - События "Рождение ребенка" как события родственников (чтобы избежать задвоения)

        Сортировка браков без даты:
        - Если есть совместные дети — перед рождением первого ребенка
        - Иначе — в самом конце хронологии
        """
        timeline = []

        # 1. Собственные события (исключая BIRTH_OF_CHILD)
        for event in self.life_events.exclude(event_type=EventTypeEnum.BIRTH_OF_CHILD):
            timeline.append(
                {
                    "date": event.event_date,
                    "title": event.get_event_type_display(),
                    "description": event.description or "",
                    "location": event.location or "",
                    "type": "own",
                    "related_person": event.related_person,
                    "event_obj": event,
                    "has_date": event.event_date is not None,
                }
            )

        # 2. Браки и разводы из связей
        for spouse_info in self.get_spouses():
            rel = spouse_info["relationship"]
            partner = spouse_info["person"]

            if rel.relationship_type == RelationshipTypeEnum.SPOUSE:
                title = f"Брак с {partner.full_name_display}"
            elif rel.relationship_type == RelationshipTypeEnum.EX_SPOUSE:
                title = f"Развод с {partner.full_name_display}"
            else:
                title = f"Помолвка с {partner.full_name_display}"

            timeline.append(
                {
                    "date": rel.start_date,
                    "title": title,
                    "description": rel.description or "",
                    "location": "",
                    "type": "own",
                    "related_person": partner,
                    "event_obj": None,
                    "has_date": rel.start_date is not None,
                    "relationship_obj": rel,
                }
            )

        # 3. Рождение детей
        children_birth_dates = []
        for child in self.get_children():
            if child.birth_date:
                children_birth_dates.append(child.birth_date)
                timeline.append(
                    {
                        "date": child.birth_date,
                        "title": f"Рождение {'сына' if child.gender == 'male' else 'дочери'}: {child.full_name_display}",
                        "description": "",
                        "location": child.birth_place or "",
                        "type": "relative",
                        "related_person": child,
                        "event_obj": None,
                        "has_date": True,
                    }
                )

        # 4. Смерть родителей
        for parent in self.get_parents():
            if parent.death_date:
                timeline.append(
                    {
                        "date": parent.death_date,
                        "title": f"Смерть родителя: {parent.full_name_display}",
                        "description": "",
                        "location": parent.death_place or "",
                        "type": "relative",
                        "related_person": parent,
                        "event_obj": None,
                        "has_date": True,
                    }
                )

        # 5. Обработка событий без даты
        earliest_child_birth = min(children_birth_dates) if children_birth_dates else None

        no_date_events = [item for item in timeline if not item["has_date"]]
        dated_events = [item for item in timeline if item["has_date"]]

        dated_events.sort(key=lambda x: x["date"])

        marriages_no_date = [item for item in no_date_events if item.get("relationship_obj")]
        other_no_date = [item for item in no_date_events if not item.get("relationship_obj")]

        final_timeline = []

        if earliest_child_birth:
            for item in dated_events:
                if item["date"] < earliest_child_birth:
                    final_timeline.append(item)

            final_timeline.extend(marriages_no_date)

            for item in dated_events:
                if item["date"] >= earliest_child_birth:
                    final_timeline.append(item)
        else:
            final_timeline.extend(dated_events)

        final_timeline.extend(other_no_date)

        return final_timeline
