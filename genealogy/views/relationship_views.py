"""
Views для работы с родственными связями.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DeleteView

from genealogy.forms import RelationshipForm
from genealogy.models import Relationship, Tree


class RelationshipCreateView(LoginRequiredMixin, CreateView):
    """Создание родственной связи между двумя персонами."""

    model = Relationship
    form_class = RelationshipForm
    template_name = "genealogy/relationship_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.tree = get_object_or_404(Tree, pk=self.kwargs["tree_pk"])
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления связей в это дерево")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Связь между "{self.object.from_person.full_name_display}" и '
            f'"{self.object.to_person.full_name_display}" успешно создана.',
        )
        return response

    def get_success_url(self):
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})


class RelationshipDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление родственной связи с подтверждением."""

    model = Relationship
    template_name = "genealogy/relationship_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.tree = self.object.from_person.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления связей в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tree"] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(
            request,
            f'Связь между "{self.object.from_person.full_name_display}" и '
            f'"{self.object.to_person.full_name_display}" успешно удалена.',
        )
        return response

    def get_success_url(self):
        return reverse("genealogy:tree_detail", kwargs={"pk": self.tree.pk})
