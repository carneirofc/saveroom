from dataclasses import dataclass
from typing import Optional, Type, TypedDict

from baserow.core.auth_provider.models import BaseAuthProviderModel

AuthProviderModelSubClass = Type[BaseAuthProviderModel]


class AuthProviderTypeDict(TypedDict):
    id: int
    type: str
    domain: str
    enabled: bool


@dataclass
class UserInfo:
    email: str
    name: str
    language: Optional[str] = None
    # True only when the identity provider explicitly vouches for the email.
    email_verified: bool = False
