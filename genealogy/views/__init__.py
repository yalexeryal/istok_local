"""
Views (обработчики запросов) приложения genealogy.
"""

from .api_views import TreeAncestorsAPI, TreeHierarchyAPI
from .auth_views import RegisterView, WelcomeView
from .event_views import (
    LifeEventCreateView,
    LifeEventDeleteView,
    LifeEventUpdateView,
)
from .export_views import (
    ImportConflictResolutionView,
    TreeExportResultView,
    TreeExportView,
    TreeImportView,
)
from .person_views import (
    LinkRelativeView,
    PersonCreateView,
    PersonDeleteView,
    PersonDetailView,
    PersonPhotoDeleteView,
    PersonPhotoSetPrimaryView,
    PersonPhotoUploadView,
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
    "ImportConflictResolutionView",
    "LifeEventCreateView",
    "LifeEventDeleteView",
    "LifeEventUpdateView",
    "LinkRelativeView",
    "PersonCreateView",
    "PersonDeleteView",
    "PersonDetailView",
    "PersonPhotoDeleteView",
    "PersonPhotoSetPrimaryView",
    "PersonPhotoUploadView",
    "PersonUpdateView",
    "RegisterView",
    "RelationshipCreateView",
    "RelationshipDeleteView",
    "TreeAncestorsAPI",
    "TreeCreateView",
    "TreeDetailView",
    "TreeExportResultView",
    "TreeExportView",
    "TreeHierarchyAPI",
    "TreeImportView",
    "TreeListView",
    "WelcomeView",
    "tree_data_api",
]
