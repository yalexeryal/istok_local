"""
Views для работы с деревьями.
"""

import json
from contextlib import suppress

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.generic import CreateView, DetailView, ListView

from genealogy.models import (
    CollaboratorRoleEnum,
    Tree,
    TreeCollaborator,
)


class TreeListView(LoginRequiredMixin, ListView):
    """Список деревьев, доступных пользователю."""

    model = Tree
    template_name = "genealogy/tree_list.html"
    context_object_name = "trees"

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Tree.objects.annotate(persons_count=Count("persons", distinct=True)).order_by("-updated_at")

        return (
            Tree.objects.filter(Q(collaborators__user=user) | Q(is_public=True))
            .distinct()
            .annotate(persons_count=Count("persons", distinct=True))
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        trees_with_roles = []
        for tree in context["trees"]:
            collaborator = tree.collaborators.filter(user=user).first()
            if collaborator:
                role = collaborator.get_role_display()
            elif tree.is_public:
                role = "Гость"
            else:
                role = "—"

            trees_with_roles.append({"tree": tree, "role": role})

        context["trees_with_roles"] = trees_with_roles
        context["total_trees"] = len(trees_with_roles)
        return context


class TreeCreateView(LoginRequiredMixin, CreateView):
    """Создание нового дерева."""

    model = Tree
    fields = ["name", "description", "is_public"]
    template_name = "genealogy/tree_form.html"

    def get_success_url(self):
        from django.urls import reverse_lazy

        return reverse_lazy("genealogy:tree_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        TreeCollaborator.objects.create(
            tree=self.object,
            user=self.request.user,
            role=CollaboratorRoleEnum.OWNER,
        )
        messages.success(self.request, f'Дерево "{self.object.name}" успешно создано.')
        return response


class TreeDetailView(LoginRequiredMixin, DetailView):
    """Детальная страница дерева с визуализацией графа."""

    model = Tree
    template_name = "genealogy/tree_detail.html"
    context_object_name = "tree"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not self.object.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет доступа к этому дереву")
        return self.render_to_response(self.get_context_data(object=self.object))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.object
        user = self.request.user

        # Берем все персоны дерева (фильтрация будет мгновенной на фронтенде через Alpine.js)
        persons_qs = tree.persons.all().prefetch_related("relationships_from", "relationships_to", "life_events")

        # Формируем список словарей для передачи в JSON
        persons_list = []
        for p in persons_qs.order_by("last_name", "first_name"):
            persons_list.append(
                {
                    "id": p.pk,
                    "full_name": p.full_name_display,
                    "gender": p.get_gender_display(),
                    "birth_date": p.birth_date.strftime("%d.%m.%Y") if p.birth_date else None,
                    "age": p.age,
                    "is_alive": p.is_alive,
                    "last_name": p.last_name or "",
                }
            )

        context["persons_count"] = persons_qs.count()
        # Передаем данные в шаблон как JSON-строку
        context["persons_json"] = json.dumps(persons_list)

        collaborator = tree.collaborators.filter(user=user).first()
        if collaborator:
            context["user_role"] = collaborator.get_role_display()
            context["can_edit"] = tree.user_can_edit(user)
        elif user.is_superuser:
            context["user_role"] = "Администратор"
            context["can_edit"] = True
        else:
            context["user_role"] = "Гость"
            context["can_edit"] = False

        return context


@login_required
def tree_data_api(request, pk):
    """API endpoint для получения данных дерева в JSON формате."""
    tree = get_object_or_404(Tree, pk=pk)

    if not tree.user_can_view(request.user):
        return JsonResponse({"error": "Access denied"}, status=403)

    persons = tree.persons.all()

    nodes = [
        {
            "data": {
                "id": str(p.pk),
                "label": p.full_name_display,
                "first_name": p.first_name,
                "last_name": p.last_name or "",
                "gender": p.gender,
                "birth_date": p.birth_date.isoformat() if p.birth_date else None,
                "death_date": p.death_date.isoformat() if p.death_date else None,
                "is_alive": p.is_alive,
                "age": p.age,
                "photo_url": p.photo.url if p.photo else None,
            }
        }
        for p in persons
    ]

    edges = []
    for p in persons:
        for rel in p.relationships_from.all():
            edges.append(
                {
                    "data": {
                        "id": f"{rel.from_person_id}-{rel.to_person_id}-{rel.relationship_type}",
                        "source": str(rel.from_person_id),
                        "target": str(rel.to_person_id),
                        "relationship_type": rel.relationship_type,
                        "label": rel.get_relationship_type_display(),
                    }
                }
            )

    return JsonResponse(
        {
            "tree": {"id": tree.pk, "name": tree.name, "description": tree.description},
            "nodes": nodes,
            "edges": edges,
        }
    )


class TreeStatisticsView(LoginRequiredMixin, DetailView):
    """Страница статистики дерева."""

    model = Tree
    template_name = "genealogy/tree_statistics.html"
    context_object_name = "tree"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.object

        if not tree.user_can_view(self.request.user):
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("У вас нет прав для просмотра этого дерева")

        # Безопасное определение роли (если метода get_user_role нет в модели)
        if hasattr(tree, "get_user_role"):
            context["user_role"] = tree.get_user_role(self.request.user)
        else:
            # Простая проверка: если пользователь совпадает с владельцем дерева
            context["user_role"] = "Владелец" if getattr(tree, "owner", None) == self.request.user else "Участник"

        # Центральная персона для фильтра "только кровные"
        context["center_person"] = tree.persons.order_by("id").first()
        return context


class TreeAuditLogView(LoginRequiredMixin, DetailView):
    """Страница истории изменений дерева."""

    model = Tree
    template_name = "genealogy/tree_audit_log.html"
    context_object_name = "tree"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from genealogy.models import AuditLog

        context = super().get_context_data(**kwargs)
        tree = self.object

        if not tree.user_can_view(self.request.user):
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("У вас нет прав для просмотра этого дерева")

        # Фильтры
        action_filter = self.request.GET.get("action", "")
        entity_type_filter = self.request.GET.get("entity_type", "")
        user_filter = self.request.GET.get("user", "")

        logs = AuditLog.objects.filter(tree=tree).select_related("user")

        if action_filter:
            logs = logs.filter(action=action_filter)
        if entity_type_filter:
            logs = logs.filter(entity_type=entity_type_filter)
        if user_filter:
            logs = logs.filter(user_id=user_filter)

        context["logs"] = logs[:200]  # Ограничиваем 200 последними записями
        context["total_count"] = AuditLog.objects.filter(tree=tree).count()
        context["action_filter"] = action_filter
        context["entity_type_filter"] = entity_type_filter
        context["user_filter"] = user_filter

        # Список пользователей для фильтра
        context["users"] = (
            AuditLog.objects.filter(tree=tree, user__isnull=False)
            .values_list("user__id", "user__username")
            .distinct()
            .order_by("user__username")
        )

        # Роль пользователя
        collaborator = tree.collaborators.filter(user=self.request.user).first()
        context["user_role"] = (
            collaborator.get_role_display()
            if collaborator
            else ("Администратор" if self.request.user.is_superuser else "Гость")
        )

        return context


class TreeSearchView(LoginRequiredMixin, DetailView):
    """Расширенный поиск персон в дереве."""

    model = Tree
    template_name = "genealogy/tree_search.html"
    context_object_name = "tree"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login

            return redirect_to_login(request.get_full_path())
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.object

        if not tree.user_can_view(self.request.user):
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("У вас нет прав для просмотра этого дерева")

        # Получаем параметры поиска и приводим к нижнему регистру
        query = self.request.GET.get("q", "").strip()
        gender = self.request.GET.get("gender", "")
        alive_status = self.request.GET.get("alive_status", "")
        birth_year_from = self.request.GET.get("birth_year_from", "")
        birth_year_to = self.request.GET.get("birth_year_to", "")
        death_year_from = self.request.GET.get("death_year_from", "")
        death_year_to = self.request.GET.get("death_year_to", "")
        birth_place = self.request.GET.get("birth_place", "").strip()
        death_place = self.request.GET.get("death_place", "").strip()
        culture = self.request.GET.get("culture", "").strip()

        # Начинаем с базового queryset
        persons = tree.persons.all()

        # Применяем фильтры
        # Для SQLite используем фильтрацию в Python для регистронезависимого поиска с кириллицей

        if query:
            query_lower = query.lower()
            # Фильтруем в Python для корректной работы с кириллицей
            matching_ids = []
            for p in tree.persons.all():
                if (
                    query_lower in (p.first_name or "").lower()
                    or query_lower in (p.middle_name or "").lower()
                    or query_lower in (p.last_name or "").lower()
                    or query_lower in (p.maiden_name or "").lower()
                ):
                    matching_ids.append(p.pk)
            persons = persons.filter(pk__in=matching_ids)

        if gender:
            persons = persons.filter(gender=gender)

        if alive_status == "alive":
            persons = persons.filter(death_date__isnull=True)
        elif alive_status == "deceased":
            persons = persons.filter(death_date__isnull=False)

        with suppress(ValueError):
            if birth_year_from:
                persons = persons.filter(birth_date__year__gte=int(birth_year_from))

        with suppress(ValueError):
            if birth_year_to:
                persons = persons.filter(birth_date__year__lte=int(birth_year_to))

        with suppress(ValueError):
            if death_year_from:
                persons = persons.filter(death_date__year__gte=int(death_year_from))

        with suppress(ValueError):
            if death_year_to:
                persons = persons.filter(death_date__year__lte=int(death_year_to))

        if birth_place:
            birth_place_lower = birth_place.lower()
            matching_ids = [p.pk for p in persons if birth_place_lower in (p.birth_place or "").lower()]
            persons = persons.filter(pk__in=matching_ids)

        if death_place:
            death_place_lower = death_place.lower()
            matching_ids = [p.pk for p in persons if death_place_lower in (p.death_place or "").lower()]
            persons = persons.filter(pk__in=matching_ids)

        if culture:
            culture_lower = culture.lower()
            matching_ids = [p.pk for p in persons if culture_lower in (p.culture or "").lower()]
            persons = persons.filter(pk__in=matching_ids)

        # Сортировка
        persons = persons.order_by("last_name", "first_name", "middle_name")

        # Передаём в контекст
        context["persons"] = persons
        context["results_count"] = persons.count()
        context["total_count"] = tree.persons.count()

        # Сохраняем параметры для формы
        context["query"] = query
        context["gender"] = gender
        context["alive_status"] = alive_status
        context["birth_year_from"] = birth_year_from
        context["birth_year_to"] = birth_year_to
        context["death_year_from"] = death_year_from
        context["death_year_to"] = death_year_to
        context["birth_place"] = birth_place
        context["death_place"] = death_place
        context["culture"] = culture

        # Роль пользователя
        collaborator = tree.collaborators.filter(user=self.request.user).first()
        context["user_role"] = (
            collaborator.get_role_display()
            if collaborator
            else ("Администратор" if self.request.user.is_superuser else "Гость")
        )

        return context
