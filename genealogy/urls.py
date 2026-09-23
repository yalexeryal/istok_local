"""
URL-маршруты приложения genealogy.

Включает:
- Аутентификацию (вход, выход, смена пароля)
- Деревья (список, детали, API)
- Персоны (CRUD: создание, чтение, редактирование, удаление)
- Родственные связи (создание, удаление)
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

    # === Деревья ===
    path(
        'tree/<int:pk>/',
        views.TreeDetailView.as_view(),
        name='tree_detail'
    ),
    path(
        'api/tree/<int:pk>/data/',
        views.tree_data_api,
        name='tree_data_api'
    ),

    # === Персоны (CRUD) ===
    path(
        'tree/<int:tree_pk>/person/add/',
        views.PersonCreateView.as_view(),
        name='person_create'
    ),
    path(
        'person/<int:pk>/',
        views.PersonDetailView.as_view(),
        name='person_detail'
    ),
    path(
        'person/<int:pk>/edit/',
        views.PersonUpdateView.as_view(),
        name='person_update'
    ),
    path(
        'person/<int:pk>/delete/',
        views.PersonDeleteView.as_view(),
        name='person_delete'
    ),

    # === Родственные связи ===
    path(
        'tree/<int:tree_pk>/relationship/add/',
        views.RelationshipCreateView.as_view(),
        name='relationship_create'
    ),
    path(
        'relationship/<int:pk>/delete/',
        views.RelationshipDeleteView.as_view(),
        name='relationship_delete'
    ),
]