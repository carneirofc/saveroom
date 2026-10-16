from baserow.core.api_clients.handler import ApiClientHandler
from baserow.core.api_clients.models import ApiClient
from baserow.core.api_clients.scopes import ALL_SCOPES


class ApiClientFixtures:
    def create_api_client(self, **kwargs):
        if "name" not in kwargs:
            kwargs["name"] = self.fake.name()

        if "user" not in kwargs:
            kwargs["user"] = self.create_user()

        if "workspace" not in kwargs:
            kwargs["workspace"] = self.create_workspace(user=kwargs["user"])

        if "scopes" not in kwargs:
            kwargs["scopes"] = list(ALL_SCOPES)

        return ApiClient.objects.create(**kwargs)

    def create_api_client_key(self, api_client=None, **kwargs):
        """
        Issues a key for a client and returns the `(key, raw_key)` tuple. The raw key
        is the only way to authenticate, it is not recoverable afterwards.
        """

        if api_client is None:
            api_client = self.create_api_client(**kwargs)

        return ApiClientHandler().create_key(api_client.user, api_client)

    def create_api_client_and_key(self, **kwargs):
        """
        Convenience for tests that need a usable credential: returns the
        `(api_client, raw_key)` tuple.
        """

        api_client = self.create_api_client(**kwargs)
        _, raw_key = ApiClientHandler().create_key(api_client.user, api_client)
        return api_client, raw_key
