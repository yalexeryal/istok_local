"""
Views для работы с событиями жизни.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.generic import CreateView, DeleteView, UpdateView

from genealogy.forms import LifeEventForm
from genealogy.models import LifeEvent, Person


class LifeEventCreateView(LoginRequiredMixin, CreateView):
    """Создание события жизни для персоны."""

    model = LifeEvent
    form_class = LifeEventForm
    template_name = "genealogy/life_event_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.person = get_object_or_404(Person, pk=self.kwargs["person_pk"])
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для добавления событий в это дерево")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person"] = self.person
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = self.person
        context["tree"] = self.tree
        context["action"] = "Создание"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Событие "{self.object.get_event_type_display()}" успешно добавлено.',
        )
        return response

    def get_success_url(self):
        return reverse("genealogy:person_detail", kwargs={"pk": self.person.pk})


class LifeEventUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование события жизни."""

    model = LifeEvent
    form_class = LifeEventForm
    template_name = "genealogy/life_event_form.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для редактирования событий в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["person"] = self.person
        kwargs["tree"] = self.tree
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = self.person
        context["tree"] = self.tree
        context["action"] = "Редактирование"
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f'Событие "{self.object.get_event_type_display()}" успешно обновлено.',
        )
        return response

    def get_success_url(self):
        return reverse("genealogy:person_detail", kwargs={"pk": self.person.pk})


class LifeEventDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление события жизни с подтверждением."""

    model = LifeEvent
    template_name = "genealogy/life_event_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        self.object = self.get_object()
        self.person = self.object.person
        self.tree = self.person.tree
        if not self.tree.user_can_edit(request.user):
            return HttpResponseForbidden("У вас нет прав для удаления событий в этом дереве")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["person"] = self.person
        context["tree"] = self.tree
        return context

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        response = super().delete(request, *args, **kwargs)
        messages.success(
            request,
            f'Событие "{self.object.get_event_type_display()}" успешно удалено.',
        )
        return response

    def get_success_url(self):
        return reverse("genealogy:person_detail", kwargs={"pk": self.person.pk})
