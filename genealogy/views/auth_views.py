"""
Views для аутентификации и регистрации.
"""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView


class WelcomeView(TemplateView):
    """Публичная страница приветствия."""

    template_name = "genealogy/welcome.html"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("genealogy:tree_list")
        return super().get(request, *args, **kwargs)


class RegisterView(CreateView):
    """Страница регистрации нового пользователя."""

    form_class = UserCreationForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("genealogy:tree_list")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("genealogy:tree_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            f"Добро пожаловать, {self.object.username}! Ваш аккаунт успешно создан.",
        )
        return response
