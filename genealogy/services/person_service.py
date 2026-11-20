"""
Сервис для создания связей между персонами.

Централизует логику создания Relationship, логирования и LifeEvent-событий.
Убирает дублирование из PersonCreateView и LinkRelativeView.
"""

import logging
from dataclasses import dataclass

from django.db import transaction
from django.db.models import Q

from genealogy.models import EventTypeEnum, LifeEvent, Person, Relationship, RelationshipTypeEnum
from genealogy.utils.audit import get_client_ip, log_action

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersonLinkResult:
    """Результат привязки родственной персоны."""

    success: bool
    message: str
    relationship: Relationship | None = None
    created_events: int = 0


def _get_current_spouse(person: Person) -> Person | None:
    """Возвращает текущего супруга персоны по приоритету."""
    spouse_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True)
        | Q(to_person=person, relationship_type=RelationshipTypeEnum.SPOUSE, is_current=True),
    ).first()

    if spouse_rel:
        return spouse_rel.to_person if spouse_rel.from_person == person else spouse_rel.from_person

    # Fallback: помолвка
    fiance_rel = Relationship.objects.filter(
        Q(from_person=person, relationship_type=RelationshipTypeEnum.FIANCE)
        | Q(to_person=person, relationship_type=RelationshipTypeEnum.FIANCE),
    ).first()

    if fiance_rel:
        return fiance_rel.to_person if fiance_rel.from_person == person else fiance_rel.from_person

    return None


def _log_relationship(
    tree,
    user,
    rel: Relationship,
    action: str,
    person_a: Person,
    person_b: Person,
    request=None,
) -> None:
    """Логирование операции с Relationship."""
    ip = get_client_ip(request) if request else None
    log_action(
        tree=tree,
        user=user,
        action=action,
        entity_type="RELATIONSHIP",
        entity_id=rel.pk,
        entity_name=f"{person_a.full_name_display} → {person_b.full_name_display}",
        details={"type": rel.get_relationship_type_display()},
        ip_address=ip,
    )


def _create_birth_of_child_events(parent: Person, child: Person, user, request) -> int:
    """Создаёт событие BirthOfChild для родителя при рождении ребёнка."""
    if not child.birth_date:
        return 0

    _event, created = LifeEvent.objects.get_or_create(
        person=parent,
        event_type=EventTypeEnum.BIRTH_OF_CHILD,
        event_date=child.birth_date,
        related_person=child,
        defaults={
            "location": child.birth_place,
            "description": f"Рождение {'сына' if child.gender == 'male' else 'дочери'}: {child.full_name_display}",
            "created_by": user,
        },
    )
    return 1 if created else 0


def create_child_relationship(
    parent: Person,
    child: Person,
    relation_type: str,
    tree,
    user,
    request,
) -> PersonLinkResult:
    """
    Создаёт связь родитель→ребёнок и второго супруга родителя.

    Пример: создаём сына → parent→child + spouse(parent)→child.
    """
    is_biological = relation_type in ("son", "daughter")
    rel_enum = RelationshipTypeEnum.BIOLOGICAL_PARENT if is_biological else RelationshipTypeEnum.ADOPTIVE_PARENT

    with transaction.atomic():
        rel, created = Relationship.objects.get_or_create(
            from_person=parent,
            to_person=child,
            relationship_type=rel_enum,
            defaults={"created_by": user},
        )
        if created:
            _log_relationship(tree, user, rel, "CREATE", parent, child, request)

        spouse = _get_current_spouse(parent)
        if spouse:
            rel2, created2 = Relationship.objects.get_or_create(
                from_person=spouse,
                to_person=child,
                relationship_type=rel_enum,
                defaults={"created_by": user},
            )
            if created2:
                _log_relationship(tree, user, rel2, "CREATE", spouse, child, request)

        events = _create_birth_of_child_events(parent, child, user, request)
        if spouse:
            events += _create_birth_of_child_events(spouse, child, user, request)

    return PersonLinkResult(
        success=True,
        message=f'Персона "{child.full_name_display}" успешно добавлена как {relation_type}.',
        relationship=rel,
        created_events=events,
    )


def create_parent_relationship(
    child: Person,
    new_parent: Person,
    relation_type: str,
    tree,
    user,
    request,
) -> PersonLinkResult:
    """
    Создаёт связь новый_родитель→ребёнок.

    Пример: создаём отца → new_parent→child с BIOLOGICAL_PARENT.
    """
    with transaction.atomic():
        rel, created = Relationship.objects.get_or_create(
            from_person=new_parent,
            to_person=child,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
            defaults={"created_by": user},
        )
        if created:
            _log_relationship(tree, user, rel, "CREATE", new_parent, child, request)

    return PersonLinkResult(
        success=True,
        message=f'Родитель "{new_parent.full_name_display}" успешно создан.',
        relationship=rel,
    )


def create_spouse_relationship(
    person_a: Person,
    person_b: Person,
    marriage_date: str | None = None,
    marriage_place: str | None = None,
    tree=None,
    user=None,
    request=None,
) -> PersonLinkResult:
    """
    Создаёт связь супруги + автоматическое событие МАРРИДЖ.
    """
    with transaction.atomic():
        rel, created = Relationship.objects.get_or_create(
            from_person=person_a,
            to_person=person_b,
            relationship_type=RelationshipTypeEnum.SPOUSE,
            defaults={"created_by": user, "is_current": True, "start_date": marriage_date or None},
        )
        if created:
            _log_relationship(tree, user, rel, "CREATE", person_a, person_b, request)

        for spouse, related in [(person_a, person_b), (person_b, person_a)]:
            LifeEvent.objects.get_or_create(
                person=spouse,
                event_type=EventTypeEnum.MARRIAGE,
                event_date=marriage_date or None,
                related_person=related,
                defaults={
                    "location": marriage_place or "",
                    "description": f"Брак с {related.full_name_display}",
                    "created_by": user,
                },
            )

    return PersonLinkResult(
        success=True,
        message=f'Супруг(а) "{person_b.full_name_display}" успешно создан(а).',
        relationship=rel,
    )


def create_parent_for_child_relationship(
    new_parent: Person,
    child: Person,
    tree,
    user,
    request,
) -> PersonLinkResult:
    """
    Создаёт связь когда создаём родителя от лица уже созданного ребёнка.
    """
    with transaction.atomic():
        rel, created = Relationship.objects.get_or_create(
            from_person=new_parent,
            to_person=child,
            relationship_type=RelationshipTypeEnum.BIOLOGICAL_PARENT,
            defaults={"created_by": user},
        )
        if created:
            _log_relationship(tree, user, rel, "CREATE", new_parent, child, request)

    return PersonLinkResult(
        success=True,
        message=f'Родитель "{new_parent.full_name_display}" успешно создан.',
        relationship=rel,
    )
