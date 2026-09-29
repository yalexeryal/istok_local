"""
Views (обработчики запросов) приложения genealogy.

Этот модуль экспортирует все views для удобства импорта.
"""

from .api_views import TreeHierarchyAPI
from .auth_views import RegisterView, WelcomeView
from .event_views import (
    LifeEventCreateView,
    LifeEventDeleteView,
    LifeEventUpdateView,
)
from .export_views import (
    TreeExportResultView,
    TreeExportView,
    TreeImportView,
)
from .person_views import (
    LinkRelativeView,
    PersonCreateView,
    PersonDeleteView,
    PersonDetailView,
    PersonUpdateView,
)
from .relationship_views import (
    RelationshipCreateView,
    RelationshipDeleteView,
)
from .tree_views import (
    TreeCreateView,
    TreeDetailView,
    TreeListView,
    tree_data_api,
)

__all__ = [
    "TreeHierarchyAPI",
    "WelcomeView",
    "RegisterView",
    "TreeListView",
    "TreeCreateView",
    "TreeDetailView",
    "tree_data_api",
    "PersonCreateView",
    "PersonUpdateView",
    "PersonDeleteView",
    "PersonDetailView",
    "LinkRelativeView",
    "RelationshipCreateView",
    "RelationshipDeleteView",
    "LifeEventCreateView",
    "LifeEventUpdateView",
    "LifeEventDeleteView",
    "TreeExportView",
    "TreeExportResultView",
    "TreeImportView",
]
