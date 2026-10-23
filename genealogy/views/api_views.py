"""
API Views для приложения genealogy.
"""

from collections import defaultdict
from datetime import date

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views import View

from genealogy.models import GenderEnum, Person, Relationship, RelationshipTypeEnum, Tree


class TreeHierarchyAPI(LoginRequiredMixin, View):
    """
    API для получения данных дерева с поддержкой фильтрации по типу родства.
    """

    def get(self, request, tree_pk):
        from genealogy.utils.kinship import get_kinship_network

        tree = get_object_or_404(Tree, pk=tree_pk)
        if not tree.user_can_view(request.user):
            return JsonResponse({"error": "Access denied"}, status=403)

        scope = request.GET.get("scope", "relatives")
        center_person_id = request.GET.get("center_person")

        if center_person_id:
            center_person = get_object_or_404(Person, pk=center_person_id, tree=tree)
        else:
            center_person = tree.persons.order_by("id").first()
            if not center_person:
                return JsonResponse({"center_person": None, "nodes": [], "links": []})

        # 1. Определяем список ID персон в зависимости от выбранной области
        if scope == "all":
            person_ids = set(tree.persons.values_list("pk", flat=True))
        else:
            if scope == "blood_only":
                person_ids = get_kinship_network(
                    center_person, include_spouses=False, include_adoptive=True, include_ex_spouses=False
                )
            else:  # relatives (по умолчанию)
                person_ids = get_kinship_network(
                    center_person, include_spouses=True, include_adoptive=True, include_ex_spouses=True
                )

        # 2. Формируем узлы (только отфильтрованные персоны)
        persons_qs = Person.objects.filter(pk__in=person_ids).values(
            "pk",
            "first_name",
            "middle_name",
            "last_name",
            "maiden_name",
            "gender",
            "birth_date",
            "death_date",
            "is_birth_date_approx",
            "is_death_date_approx",
            "photo",
        )

        nodes = []
        for p in persons_qs:
            full_name = f"{p['last_name'] or ''} {p['first_name'] or ''} {p['middle_name'] or ''}".strip()

            photo_url = f"/media/{p['photo']}" if p["photo"] else None

            nodes.append(
                {
                    "id": str(p["pk"]),
                    "label": full_name or "Не указано",
                    "first_name": p["first_name"],
                    "middle_name": p["middle_name"] or "",
                    "last_name": p["last_name"] or "",
                    "maiden_name": p["maiden_name"] or "",
                    "gender": p["gender"],
                    "birth_date": p["birth_date"].isoformat() if p["birth_date"] else None,
                    "death_date": p["death_date"].isoformat() if p["death_date"] else None,
                    "is_birth_date_approx": p["is_birth_date_approx"],
                    "is_death_date_approx": p["is_death_date_approx"],
                    "photo_url": photo_url,
                }
            )

        # 3. Формируем связи (только между отфильтрованными персонами)
        links = []
        relationships = Relationship.objects.filter(from_person__in=person_ids, to_person__in=person_ids).values(
            "from_person_id", "to_person_id", "relationship_type"
        )

        for rel in relationships:
            # Жестко нормализуем: нижний регистр + замена пробелов и дефисов на подчеркивания
            rel_type = str(rel["relationship_type"]).lower().replace("-", "_").replace(" ", "_")

            links.append(
                {
                    "source": str(rel["from_person_id"]),
                    "target": str(rel["to_person_id"]),
                    "type": rel_type,
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


class TreeStatisticsAPI(LoginRequiredMixin, View):
    """API для получения статистики дерева с поддержкой фильтра 'только кровные'."""

    def get(self, request, tree_pk):
        tree = get_object_or_404(Tree, pk=tree_pk)
        if not tree.user_can_view(request.user):
            return JsonResponse({"error": "Access denied"}, status=403)

        # Определяем область фильтрации
        scope = request.GET.get("scope", "all")

        if scope in ["relatives", "blood_only"]:
            center_id = request.GET.get("center_person")
            if center_id:
                from genealogy.utils.kinship import get_kinship_network

                try:
                    center = Person.objects.get(pk=int(center_id), tree=tree)

                    # Разные параметры для разных режимов
                    if scope == "blood_only":
                        person_ids = get_kinship_network(
                            center_person=center,
                            include_spouses=False,  # Только кровные
                            include_adoptive=True,
                            include_ex_spouses=False,
                        )
                    else:  # relatives
                        person_ids = get_kinship_network(
                            center_person=center,
                            include_spouses=True,  # Кровные + супруги
                            include_adoptive=True,
                            include_ex_spouses=True,
                        )

                    persons = Person.objects.filter(pk__in=person_ids)
                except Person.DoesNotExist:
                    persons = tree.persons.all()
                    person_ids = set(persons.values_list("pk", flat=True))
            else:
                persons = tree.persons.all()
                person_ids = set(persons.values_list("pk", flat=True))
        else:
            persons = tree.persons.all()
            person_ids = set(persons.values_list("pk", flat=True))

        today = date.today()
        stats = {}

        # === 2. БАЗОВАЯ СТАТИСТИКА ===
        total = persons.count()
        alive = persons.filter(death_date__isnull=True).count()
        deceased = total - alive

        lifespans = []
        for p in persons.filter(death_date__isnull=False, birth_date__isnull=False):
            lifespan = p.death_date.year - p.birth_date.year
            if (p.death_date.month, p.death_date.day) < (p.birth_date.month, p.birth_date.day):
                lifespan -= 1
            if lifespan >= 0:
                lifespans.append(lifespan)
        avg_lifespan = round(sum(lifespans) / len(lifespans), 1) if lifespans else None

        ages = []
        for p in persons.filter(death_date__isnull=True, birth_date__isnull=False):
            age = today.year - p.birth_date.year
            if (today.month, today.day) < (p.birth_date.month, p.birth_date.day):
                age -= 1
            if age >= 0:
                ages.append(age)
        avg_age = round(sum(ages) / len(ages), 1) if ages else None

        stats["basic"] = {
            "total": total,
            "alive": alive,
            "deceased": deceased,
            "avg_lifespan": avg_lifespan,
            "avg_age": avg_age,
            "filtered_count": len(person_ids),
        }

        # === 3. РАСПРЕДЕЛЕНИЕ ПО ПОЛУ ===
        stats["gender"] = {
            "male": persons.filter(gender=GenderEnum.MALE).count(),
            "female": persons.filter(gender=GenderEnum.FEMALE).count(),
            "unknown": persons.filter(gender=GenderEnum.UNKNOWN).count(),
        }

        # === 4. ВОЗРАСТНЫЕ ГРУППЫ (живые) ===
        age_groups = {
            "0-10": 0,
            "11-20": 0,
            "21-30": 0,
            "31-40": 0,
            "41-50": 0,
            "51-60": 0,
            "61-70": 0,
            "71-80": 0,
            "81-90": 0,
            "90+": 0,
        }
        for age in ages:
            if age <= 10:
                age_groups["0-10"] += 1
            elif age <= 20:
                age_groups["11-20"] += 1
            elif age <= 30:
                age_groups["21-30"] += 1
            elif age <= 40:
                age_groups["31-40"] += 1
            elif age <= 50:
                age_groups["41-50"] += 1
            elif age <= 60:
                age_groups["51-60"] += 1
            elif age <= 70:
                age_groups["61-70"] += 1
            elif age <= 80:
                age_groups["71-80"] += 1
            elif age <= 90:
                age_groups["81-90"] += 1
            else:
                age_groups["90+"] += 1
        stats["age_groups"] = age_groups

        # === 5. ДЕСЯТИЛЕТИЯ РОЖДЕНИЯ ===
        decades = defaultdict(int)
        for p in persons.filter(birth_date__isnull=False):
            decade = (p.birth_date.year // 10) * 10
            decades[decade] += 1
        sorted_decades = sorted(decades.items())
        stats["birth_decades"] = {str(k): v for k, v in sorted_decades}

        # === 6. ТОП-10 МЕСТ РОЖДЕНИЯ ===
        places = defaultdict(int)
        for p in persons.filter(birth_place__isnull=False).exclude(birth_place=""):
            place = p.birth_place.split(",")[0].strip()
            if place:
                places[place] += 1
        top_places = sorted(places.items(), key=lambda x: -x[1])[:10]
        stats["top_birth_places"] = [{"place": p, "count": c} for p, c in top_places]

        # === 7. СТАТИСТИКА БРАКОВ ===
        spouse_rels = Relationship.objects.filter(
            from_person_id__in=person_ids,
            to_person_id__in=person_ids,
            relationship_type=RelationshipTypeEnum.SPOUSE,
        )
        marriage_count = spouse_rels.count()
        marriage_durations = []
        for rel in spouse_rels:
            if rel.start_date:
                end = rel.end_date or today
                duration = (end - rel.start_date).days / 365.25
                if duration >= 0:
                    marriage_durations.append(duration)

        stats["marriages"] = {
            "count": marriage_count,
            "avg_duration": round(sum(marriage_durations) / len(marriage_durations), 1) if marriage_durations else None,
            "max_duration": round(max(marriage_durations), 1) if marriage_durations else None,
            "min_duration": round(min(marriage_durations), 1) if marriage_durations else None,
            "divorces": spouse_rels.filter(end_date__isnull=False).count(),
        }

        # === 8. СТАТИСТИКА ДЕТЕЙ (ОПТИМИЗИРОВАНО: 1 запрос вместо N) ===
        children_counts_dict = defaultdict(int)
        child_rels = (
            Relationship.objects.filter(
                from_person_id__in=person_ids,
                to_person_id__in=person_ids,
                relationship_type__in=[RelationshipTypeEnum.BIOLOGICAL_PARENT, RelationshipTypeEnum.ADOPTIVE_PARENT],
            )
            .values("from_person_id")
            .annotate(count=Count("to_person_id"))
        )

        for item in child_rels:
            children_counts_dict[item["from_person_id"]] = item["count"]

        children_counts = [children_counts_dict.get(pid, 0) for pid in person_ids]

        stats["children"] = {
            "avg": round(sum(children_counts) / len(children_counts), 2) if children_counts else 0,
            "max": max(children_counts) if children_counts else 0,
            "min": min(children_counts) if children_counts else 0,
        }

        children_distribution = defaultdict(int)
        for count in children_counts:
            key = str(count) if count <= 5 else "6+"
            children_distribution[key] += 1
        stats["children_distribution"] = dict(children_distribution)

        return JsonResponse(stats)

    def _get_blood_relatives(self, tree, center_person_id):
        """
        Возвращает ID строго кровных родственников и их супругов.
        Использует единый сервис kinship для консистентности.
        """
        from genealogy.utils.kinship import get_kinship_network

        try:
            center = Person.objects.get(pk=center_person_id, tree=tree)
        except Person.DoesNotExist:
            return set(tree.persons.values_list("pk", flat=True))

        # Вызываем единый сервис с параметрами по умолчанию
        return get_kinship_network(
            center_person=center,
            include_spouses=True,  # Включаем зятьёв, невесток, жён/мужей
            include_adoptive=True,  # Включаем приёмных как кровных
            include_ex_spouses=True,  # Включаем бывших супругов
        )
