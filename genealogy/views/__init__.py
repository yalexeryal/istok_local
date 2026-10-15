"""
Views (обработчики запросов) приложения genealogy.
"""

from .api_views import TreeAncestorsAPI, TreeHierarchyAPI, TreeStatisticsAPI, UpcomingEventsAPI
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
    TreeAuditLogView,
    TreeCreateView,
    TreeDetailView,
    TreeListView,
    TreeSearchView,
    TreeStatisticsView,
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
    "TreeAuditLogView",
    "TreeCreateView",
    "TreeDetailView",
    "TreeExportResultView",
    "TreeExportView",
    "TreeHierarchyAPI",
    "TreeImportView",
    "TreeListView",
    "TreeSearchView",
    "TreeStatisticsAPI",
    "TreeStatisticsView",
    "UpcomingEventsAPI",
    "WelcomeView",
    "tree_data_api",
]
