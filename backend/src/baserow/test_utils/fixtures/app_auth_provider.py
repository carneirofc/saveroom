from baserow.core.app_auth_providers.registries import app_auth_provider_type_registry


class AppAuthProviderFixtures:
    def create_app_auth_provider_with_first_type(self, **kwargs):
        types = list(app_auth_provider_type_registry.get_all())
        if not types:
            import pytest

            pytest.skip("No app auth provider type is registered (needs a plugin).")
        return self.create_app_auth_provider(types[0].model_class, **kwargs)

    def create_app_auth_provider(
        self, model_class, user=None, user_source=None, **kwargs
    ):
        if not user_source:
            user_source_args = kwargs.pop("user_source_args", {})
            user_source = self.create_user_source_with_first_type(
                user=user, **user_source_args
            )

        user_source = model_class.objects.create(user_source=user_source, **kwargs)

        return user_source
