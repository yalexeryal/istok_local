"""
Views для работы с деревьями.
"""

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
            return Tree.objects.all()
        return (
            Tree.objects.filter(Q(collaborators__user=user) | Q(is_public=True))
            .distinct()
            .annotate(
                persons_count=Count("persons", distinct=True),
                user_role=Q(collaborators__user=user),
            )
            .order_by("-updated_at")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        tree_roles = {}
        for tree in context["trees"]:
            collaborator = tree.collaborators.filter(user=user).first()
            tree_roles[tree.pk] = (
                collaborator.get_role_display() if collaborator else ("Гость" if tree.is_public else "—")
            )
        context["tree_roles"] = tree_roles
        context["total_trees"] = context["trees"].count()
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
        context["persons"] = tree.persons.all().prefetch_related(
            "relationships_from", "relationships_to", "life_events"
        )
        context["persons_count"] = context["persons"].count()
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
