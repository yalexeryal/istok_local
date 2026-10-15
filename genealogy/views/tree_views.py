"""
Views для работы с деревьями.
"""

import csv
import json
from contextlib import suppress
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
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

    def _get_filtered_persons(self, tree, request):
        """
        Возвращает отфильтрованный queryset персон на основе параметров поиска.

        Args:
            tree: Дерево для поиска
            request: HTTP запрос с параметрами фильтрации

        Returns:
            QuerySet: Отфильтрованный и отсортированный queryset персон
        """
        # Получаем параметры поиска
        query = request.GET.get("q", "").strip()
        gender = request.GET.get("gender", "")
        alive_status = request.GET.get("alive_status", "")
        birth_year_from = request.GET.get("birth_year_from", "")
        birth_year_to = request.GET.get("birth_year_to", "")
        death_year_from = request.GET.get("death_year_from", "")
        death_year_to = request.GET.get("death_year_to", "")
        birth_place = request.GET.get("birth_place", "").strip()
        death_place = request.GET.get("death_place", "").strip()
        culture = request.GET.get("culture", "").strip()

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
        return persons.order_by("last_name", "first_name", "middle_name")

    def get(self, request, *args, **kwargs):
        # Проверяем, запрошен ли экспорт в CSV
        if request.GET.get("export") == "csv":
            return self.export_to_csv(request)
        return super().get(request, *args, **kwargs)

    def export_to_csv(self, request):
        tree = self.get_object()
        if not tree.user_can_view(request.user):
            return HttpResponseForbidden("У вас нет прав для просмотра этого дерева")

        # Получаем отфильтрованных персон через общий метод
        persons = self._get_filtered_persons(tree, request)

        # Создаем умное имя файла на основе параметров поиска
        search_parts = []

        query = request.GET.get("q", "").strip()
        gender = request.GET.get("gender", "")
        alive_status = request.GET.get("alive_status", "")
        birth_year_from = request.GET.get("birth_year_from", "")
        birth_year_to = request.GET.get("birth_year_to", "")
        death_year_from = request.GET.get("death_year_from", "")
        death_year_to = request.GET.get("death_year_to", "")
        birth_place = request.GET.get("birth_place", "").strip()
        death_place = request.GET.get("death_place", "").strip()
        culture = request.GET.get("culture", "").strip()

        if query:
            search_parts.append(query[:30])

        if gender:
            gender_display = {"male": "Мужчины", "female": "Женщины", "unknown": "Неизвестно"}.get(gender, gender)
            search_parts.append(gender_display)

        if alive_status:
            status_display = {"alive": "Живые", "deceased": "Умершие"}.get(alive_status, alive_status)
            search_parts.append(status_display)

        if birth_year_from or birth_year_to:
            year_range = f"{birth_year_from or '...'}-{birth_year_to or '...'}"
            search_parts.append(f"Род.{year_range}")

        if death_year_from or death_year_to:
            year_range = f"{death_year_from or '...'}-{death_year_to or '...'}"
            search_parts.append(f"Ум.{year_range}")

        if birth_place:
            search_parts.append(birth_place[:20])

        if death_place:
            search_parts.append(death_place[:20])

        if culture:
            search_parts.append(culture[:20])

        # Если нет фильтров — используем имя дерева как основу
        safe_tree_name = "".join(ch if ch.isalnum() else "_" for ch in tree.name).strip("_")[:30] or "tree"
        date_str = timezone.now().strftime("%Y%m%d")

        if not search_parts:
            search_parts.append("Все_персоны")

        # Собираем имя файла
        search_description = "_".join(search_parts)

        # Финальное имя файла (с ограничением длины)
        filename = f"Поиск_{search_description}_{safe_tree_name}_{date_str}.csv"

        # Убираем недопустимые символы до формирования заголовка
        for char in '<>:"/\\|?*':
            filename = filename.replace(char, "_")

        # Оставляем запас под .csv, чтобы не отрезать расширение
        filename = filename[:100]

        response = HttpResponse(content_type="text/csv; charset=utf-8")

        ascii_filename = f"search_export_{date_str}.csv"
        encoded_filename = quote(filename, safe="")

        response["Content-Disposition"] = (
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{encoded_filename}"
        )

        # BOM (Byte Order Mark) для корректного отображения кириллицы в Excel
        response.write("\ufeff")

        writer = csv.writer(response)
        # Заголовки столбцов
        writer.writerow(
            [
                "Фамилия",
                "Имя",
                "Отчество",
                "Девичья фамилия",
                "Пол",
                "Дата рождения",
                "Место рождения",
                "Дата смерти",
                "Место смерти",
                "Статус",
                "Культура",
            ]
        )

        # Данные
        for p in persons:
            writer.writerow(
                [
                    p.last_name or "",
                    p.first_name or "",
                    p.middle_name or "",
                    p.maiden_name or "",
                    p.get_gender_display(),
                    p.birth_date.strftime("%d.%m.%Y") if p.birth_date else "",
                    p.birth_place or "",
                    p.death_date.strftime("%d.%m.%Y") if p.death_date else "",
                    p.death_place or "",
                    "Жив(а)" if p.is_alive else "Умер(ла)",
                    p.culture or "",
                ]
            )

        # Логируем действие в Audit Log
        from genealogy.utils.audit import get_client_ip, log_action

        log_action(
            tree=tree,
            user=request.user,
            action="EXPORT",
            entity_type="PERSON",
            entity_name=f"Экспорт поиска ({persons.count()} записей)",
            ip_address=get_client_ip(request),
        )

        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tree = self.object

        if not tree.user_can_view(self.request.user):
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("У вас нет прав для просмотра этого дерева")

        # Получаем отфильтрованных персон через общий метод
        persons = self._get_filtered_persons(tree, self.request)

        # Передаём в контекст
        context["persons"] = persons
        context["results_count"] = persons.count()
        context["total_count"] = tree.persons.count()

        # Сохраняем параметры для формы
        context["query"] = self.request.GET.get("q", "").strip()
        context["gender"] = self.request.GET.get("gender", "")
        context["alive_status"] = self.request.GET.get("alive_status", "")
        context["birth_year_from"] = self.request.GET.get("birth_year_from", "")
        context["birth_year_to"] = self.request.GET.get("birth_year_to", "")
        context["death_year_from"] = self.request.GET.get("death_year_from", "")
        context["death_year_to"] = self.request.GET.get("death_year_to", "")
        context["birth_place"] = self.request.GET.get("birth_place", "").strip()
        context["death_place"] = self.request.GET.get("death_place", "").strip()
        context["culture"] = self.request.GET.get("culture", "").strip()

        # Роль пользователя
        collaborator = tree.collaborators.filter(user=self.request.user).first()
        context["user_role"] = (
            collaborator.get_role_display()
            if collaborator
            else ("Администратор" if self.request.user.is_superuser else "Гость")
        )

        return context
