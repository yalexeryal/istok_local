"""
API Views для приложения genealogy.
"""

from collections import deque

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
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
                    "last_name": p.last_name or "",
                    "gender": p.gender,
                    "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                    "death_date": p.death_date.isoformat() if p.death_date else None,
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
                    "last_name": center_person.last_name or "",
                    "gender": center_person.gender,
                    "birth_date": center_person.birth_date.isoformat() if center_person.birth_date else None,
                    "death_date": center_person.death_date.isoformat() if center_person.death_date else None,
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
                                "last_name": parent.last_name or "",
                                "gender": parent.gender,
                                "birth_date": parent.birth_date.isoformat() if parent.birth_date else None,
                                "death_date": parent.death_date.isoformat() if parent.death_date else None,
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
