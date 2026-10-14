"""
API Views для приложения genealogy.
"""

from collections import deque

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from genealogy.models import Person, Relationship, RelationshipTypeEnum, Tree


class TreeHierarchyAPI(LoginRequiredMixin, View):
    """
    API для получения иерархии дерева вокруг центральной персоны.
    """

    def get(self, request, tree_pk):
        tree = get_object_or_404(Tree, pk=tree_pk)
        if not tree.user_can_view(request.user):
            return JsonResponse({"error": "Access denied"}, status=403)

        center_person_id = request.GET.get("center_person")
        if center_person_id:
            center_person = get_object_or_404(Person, pk=center_person_id, tree=tree)
        else:
            # По умолчанию центральная фигура — самая первая персона, созданная в дереве.
            center_person = tree.persons.order_by("id").first()
            if not center_person:
                return JsonResponse({"center_person": None, "nodes": [], "links": []})

        max_depth = 3

        visited_persons = set()
        queue = deque([(center_person, 0)])
        visited_persons.add(center_person.pk)

        relevant_persons = {center_person.pk: center_person}

        while queue:
            current_person, current_depth = queue.popleft()

            if current_depth >= max_depth:
                continue

            rels = Relationship.objects.filter(
                models.Q(from_person=current_person) | models.Q(to_person=current_person)
            ).select_related("from_person", "to_person")

            for rel in rels:
                partner = rel.to_person if rel.from_person == current_person else rel.from_person
                if partner.pk not in visited_persons:
                    visited_persons.add(partner.pk)
                    relevant_persons[partner.pk] = partner
                    queue.append((partner, current_depth + 1))

        nodes = []
        for p in relevant_persons.values():
            nodes.append(
                {
                    "id": str(p.pk),
                    "label": p.full_name_display,
                    "first_name": p.first_name,
                    "middle_name": p.middle_name or "",
                    "last_name": p.last_name or "",
                    "maiden_name": p.maiden_name or "",
                    "gender": p.gender,
                    "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                    "death_date": p.death_date.isoformat() if p.death_date else None,
                    "is_birth_date_approx": p.is_birth_date_approx,
                    "is_death_date_approx": p.is_death_date_approx,
                    "photo_url": p.photo.url if p.photo else None,
                }
            )

        links = []
        rel_pks = [p.pk for p in relevant_persons.values()]
        relationships = Relationship.objects.filter(from_person__in=rel_pks, to_person__in=rel_pks)
        for rel in relationships:
            links.append(
                {
                    "source": str(rel.from_person_id),
                    "target": str(rel.to_person_id),
                    "type": rel.relationship_type,
                    "label": rel.get_relationship_type_display(),
                }
            )

        return JsonResponse(
            {
                "center_person": str(center_person.pk),
                "nodes": nodes,
                "links": links,
            }
        )


class TreeAncestorsAPI(LoginRequiredMixin, View):
    """
    API для получения предков выбранной персоны (веерная диаграмма).
    """

    def get(self, request, tree_pk):
        tree = get_object_or_404(Tree, pk=tree_pk)
        if not tree.user_can_view(request.user):
            return JsonResponse({"error": "Access denied"}, status=403)

        center_person_id = request.GET.get("center_person")
        if center_person_id:
            center_person = get_object_or_404(Person, pk=center_person_id, tree=tree)
        else:
            # По умолчанию центральная фигура — самая первая персона, созданная в дереве.
            center_person = tree.persons.order_by("id").first()
            if not center_person:
                return JsonResponse({"center_person": None, "generations": []})

        max_generations = 6
        generations = []

        generations.append(
            [
                {
                    "id": str(center_person.pk),
                    "label": center_person.full_name_display,
                    "first_name": center_person.first_name,
                    "middle_name": center_person.middle_name or "",
                    "last_name": center_person.last_name or "",
                    "maiden_name": center_person.maiden_name or "",
                    "gender": center_person.gender,
                    "birth_date": center_person.birth_date.isoformat() if center_person.birth_date else None,
                    "death_date": center_person.death_date.isoformat() if center_person.death_date else None,
                    "is_birth_date_approx": center_person.is_birth_date_approx,
                    "is_death_date_approx": center_person.is_death_date_approx,
                    "photo_url": center_person.photo.url if center_person.photo else None,
                    "generation": 0,
                }
            ]
        )

        current_generation_persons = [center_person]

        for gen in range(1, max_generations + 1):
            next_generation_persons = []
            gen_data = []

            for person in current_generation_persons:
                parent_rels = Relationship.objects.filter(
                    to_person=person,
                    relationship_type__in=[
                        RelationshipTypeEnum.BIOLOGICAL_PARENT,
                        RelationshipTypeEnum.ADOPTIVE_PARENT,
                    ],
                ).select_related("from_person")

                for rel in parent_rels:
                    parent = rel.from_person
                    if parent not in next_generation_persons:
                        next_generation_persons.append(parent)
                        gen_data.append(
                            {
                                "id": str(parent.pk),
                                "label": parent.full_name_display,
                                "first_name": parent.first_name,
                                "middle_name": parent.middle_name or "",
                                "last_name": parent.last_name or "",
                                "maiden_name": parent.maiden_name or "",
                                "gender": parent.gender,
                                "birth_date": parent.birth_date.isoformat() if parent.birth_date else None,
                                "death_date": parent.death_date.isoformat() if parent.death_date else None,
                                "is_birth_date_approx": parent.is_birth_date_approx,
                                "is_death_date_approx": parent.is_death_date_approx,
                                "photo_url": parent.photo.url if parent.photo else None,
                                "generation": gen,
                                "parent_of": str(person.pk),
                            }
                        )

            if gen_data:
                generations.append(gen_data)
                current_generation_persons = next_generation_persons
            else:
                break

        return JsonResponse(
            {
                "center_person": str(center_person.pk),
                "generations": generations,
            }
        )


class UpcomingEventsAPI(LoginRequiredMixin, View):
    """
    API для получения списка ближайших событий (дни рождения, юбилеи свадеб и смертей)
    в пределах следующих 10 дней для текущего дерева.
    """

    def get(self, request, tree_pk):
        tree = get_object_or_404(Tree, pk=tree_pk)
        if not tree.user_can_view(request.user):
            return JsonResponse({"error": "Access denied"}, status=403)

        today = timezone.now().date()
        events = []

        # 1. Дни рождения (ежегодно для всех персон в дереве)
        for person in tree.persons.filter(birth_date__isnull=False):
            next_date = self._get_next_anniversary(today, person.birth_date)
            days_until = (next_date - today).days
            if 0 <= days_until <= 10:
                age = next_date.year - person.birth_date.year
                events.append(
                    {
                        "type": "birthday",
                        "emoji": "🎂",
                        "date": next_date.strftime("%d.%m"),
                        "years": age,
                        "person_id": person.pk,
                        "person_name": person.full_name_display,
                        "days_until": days_until,
                    }
                )

        # 2. Годовщины свадеб (только юбилеи: 1 год или кратно 5)
        spouse_rels = Relationship.objects.filter(
            from_person__tree=tree, relationship_type=RelationshipTypeEnum.SPOUSE, start_date__isnull=False
        )
        for rel in spouse_rels:
            years_married = today.year - rel.start_date.year
            if years_married == 1 or years_married % 5 == 0:
                next_date = self._get_next_anniversary(today, rel.start_date)
                days_until = (next_date - today).days
                if 0 <= days_until <= 10:
                    events.append(
                        {
                            "type": "wedding",
                            "emoji": "💍",
                            "date": next_date.strftime("%d.%m"),
                            "years": years_married,
                            "person_id": rel.from_person.pk,
                            "person_name": f"{rel.from_person.full_name_display} и {rel.to_person.full_name_display}",
                            "days_until": days_until,
                        }
                    )

        # 3. Годовщины смерти (только юбилеи: 1 год или кратно 5)
        for person in tree.persons.filter(death_date__isnull=False):
            years_since = today.year - person.death_date.year
            if years_since == 1 or years_since % 5 == 0:
                next_date = self._get_next_anniversary(today, person.death_date)
                days_until = (next_date - today).days
                if 0 <= days_until <= 10:
                    events.append(
                        {
                            "type": "death",
                            "emoji": "✝️",
                            "date": next_date.strftime("%d.%m"),
                            "years": years_since,
                            "person_id": person.pk,
                            "person_name": person.full_name_display,
                            "days_until": days_until,
                        }
                    )

        # Сортируем по близости события и берём максимум 5
        events.sort(key=lambda x: x["days_until"])

        return JsonResponse({"events": events[:5]})

    def _get_next_anniversary(self, today, original_date):
        """Возвращает следующую дату годовщины (в этом или следующем году)."""
        try:
            next_date = original_date.replace(year=today.year)
            if next_date < today:
                next_date = original_date.replace(year=today.year + 1)
            return next_date
        except ValueError:
            # Обработка 29 февраля для невисокосных годов
            next_date = original_date.replace(year=today.year, day=28)
            if next_date < today:
                next_date = original_date.replace(year=today.year + 1, day=28)
            return next_date
