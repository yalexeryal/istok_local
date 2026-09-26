"""
URL-маршруты приложения genealogy.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "genealogy"

urlpatterns = [
    path("", views.WelcomeView.as_view(), name="welcome"),
    path("accounts/register/", views.RegisterView.as_view(), name="register"),
    path("accounts/login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password_change/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change.html", success_url="/accounts/password_change/done/"
        ),
        name="password_change",
    ),
    path(
        "accounts/password_change/done/",
        auth_views.PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
    path("trees/", views.TreeListView.as_view(), name="tree_list"),
    path("tree/add/", views.TreeCreateView.as_view(), name="tree_create"),
    path("tree/<int:pk>/", views.TreeDetailView.as_view(), name="tree_detail"),
    path("api/tree/<int:pk>/data/", views.tree_data_api, name="tree_data_api"),
    path("tree/<int:pk>/export/", views.TreeExportView.as_view(), name="tree_export"),
    path("tree/<int:pk>/export/result/<int:task_pk>/", views.TreeExportResultView.as_view(), name="tree_export_result"),
    path("import/", views.TreeImportView.as_view(), name="tree_import"),
    path("tree/<int:tree_pk>/person/add/", views.PersonCreateView.as_view(), name="person_create"),
    path("person/<int:pk>/", views.PersonDetailView.as_view(), name="person_detail"),
    path("person/<int:pk>/edit/", views.PersonUpdateView.as_view(), name="person_update"),
    path("person/<int:pk>/delete/", views.PersonDeleteView.as_view(), name="person_delete"),
    path("tree/<int:tree_pk>/link-relative/", views.LinkRelativeView.as_view(), name="link_relative"),
    path("person/<int:person_pk>/event/add/", views.LifeEventCreateView.as_view(), name="life_event_create"),
    path("event/<int:pk>/edit/", views.LifeEventUpdateView.as_view(), name="life_event_update"),
    path("event/<int:pk>/delete/", views.LifeEventDeleteView.as_view(), name="life_event_delete"),
    path("tree/<int:tree_pk>/relationship/add/", views.RelationshipCreateView.as_view(), name="relationship_create"),
    path("relationship/<int:pk>/delete/", views.RelationshipDeleteView.as_view(), name="relationship_delete"),
]
