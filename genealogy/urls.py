"""
URL-маршруты приложения genealogy.

Включает:
- Аутентификацию (вход, выход, смена пароля)
- Главную страницу со списком деревьев
"""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = 'genealogy'

urlpatterns = [
    # === Главная страница ===
    path(
        '',
        views.TreeListView.as_view(),
        name='home'
    ),

    # === Аутентификация ===
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login'
    ),
    path(
        'accounts/logout/',
        auth_views.LogoutView.as_view(),
        name='logout'
    ),
    path(
        'accounts/password_change/',
        auth_views.PasswordChangeView.as_view(
            template_name='registration/password_change.html',
            success_url='/accounts/password_change/done/'
        ),
        name='password_change'
    ),
    path(
        'accounts/password_change/done/',
        auth_views.PasswordChangeDoneView.as_view(
            template_name='registration/password_change_done.html'
        ),
        name='password_change_done'
    ),
    # === Детальная страница дерева ===
    path(
        'tree/<int:pk>/',
        views.TreeDetailView.as_view(),
        name='tree_detail'
    ),

    # === API для получения данных дерева ===
    path(
        'api/tree/<int:pk>/data/',
        views.tree_data_api,
        name='tree_data_api'
    ),
]