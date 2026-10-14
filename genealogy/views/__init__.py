"""
Views (обработчики запросов) приложения genealogy.
"""

from .api_views import TreeAncestorsAPI, TreeHierarchyAPI, UpcomingEventsAPI
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
    "TreeAncestorsAPI",
    "TreeHierarchyAPI",
    "UpcomingEventsAPI",
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
    "PersonPhotoUploadView",
    "PersonPhotoDeleteView",
    "PersonPhotoSetPrimaryView",
    "RelationshipCreateView",
    "RelationshipDeleteView",
    "LifeEventCreateView",
    "LifeEventUpdateView",
    "LifeEventDeleteView",
    "TreeExportView",
    "TreeExportResultView",
    "TreeImportView",
    "ImportConflictResolutionView",
]
