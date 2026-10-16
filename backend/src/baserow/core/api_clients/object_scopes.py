from django.db.models import Q

from baserow.core.api_clients.models import ApiClient
from baserow.core.object_scopes import WorkspaceObjectScopeType
from baserow.core.registries import ObjectScopeType, object_scope_type_registry


class ApiClientObjectScopeType(ObjectScopeType):
    type = "api_client"
    model_class = ApiClient

    def get_parent_scope(self):
        return object_scope_type_registry.get("workspace")

    def get_filter_for_scope_type(self, scope_type, scopes):
        if scope_type.type == WorkspaceObjectScopeType.type:
            return Q(workspace__in=[s.id for s in scopes])

        raise TypeError("The given type is not handled.")
