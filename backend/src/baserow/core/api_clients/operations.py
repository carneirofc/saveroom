from abc import ABC

from baserow.core.api_clients.object_scopes import ApiClientObjectScopeType
from baserow.core.operations import WorkspaceCoreOperationType
from baserow.core.registries import OperationType


class ListApiClientsOperationType(WorkspaceCoreOperationType):
    type = "workspace.list_api_clients"


class CreateApiClientOperationType(WorkspaceCoreOperationType):
    type = "workspace.create_api_client"


class ApiClientOperationType(OperationType, ABC):
    context_scope_name = ApiClientObjectScopeType.type


class ReadApiClientOperationType(ApiClientOperationType):
    type = "workspace.api_client.read"


class UpdateApiClientOperationType(ApiClientOperationType):
    type = "workspace.api_client.update"


class DeleteApiClientOperationType(ApiClientOperationType):
    type = "workspace.api_client.delete"
