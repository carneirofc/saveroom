"""
A self-contained fake OpenID Connect provider for tests.

It generates an RSA keypair, serves a discovery document, JWKS, token and userinfo
endpoints through the ``responses`` library, and can mint (optionally tampered) ID
tokens so the full authorization-code flow can be exercised without a real IdP.
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from baserow.core.sso.oidc.config import OIDCProviderConfig

ISSUER = "https://idp.example.com/realms/test"
KID = "test-key-1"


@dataclass
class FakeOIDCProvider:
    name: str = "keycloak"
    display_name: str = "Keycloak"
    client_id: str = "baserow"
    client_secret: str = "secret"  # nosec B107
    issuer: str = ISSUER
    email: str = "alice@example.com"
    full_name: str = "Alice Example"
    # The client roles the user holds, emitted the way Keycloak does.
    client_roles: Optional[List[str]] = None
    require_verified_email: bool = True
    link_existing_accounts: bool = False
    session_lifetime_minutes: Optional[int] = None
    private_key: rsa.RSAPrivateKey = field(default=None)

    def __post_init__(self):
        if self.private_key is None:
            self.private_key = rsa.generate_private_key(
                public_exponent=65537, key_size=2048
            )

    @property
    def config(self) -> OIDCProviderConfig:
        return OIDCProviderConfig(
            name=self.name,
            display_name=self.display_name,
            issuer=self.issuer,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=["openid", "email", "profile"],
            roles_claim=f"resource_access.{self.client_id}.roles",
            require_verified_email=self.require_verified_email,
            link_existing_accounts=self.link_existing_accounts,
            session_lifetime_minutes=self.session_lifetime_minutes,
        )

    def role_claims(self) -> Dict[str, Any]:
        """The `resource_access` claim Keycloak emits for this client's roles."""

        if self.client_roles is None:
            return {}
        return {"resource_access": {self.client_id: {"roles": self.client_roles}}}

    @property
    def discovery_url(self) -> str:
        return f"{self.issuer}/.well-known/openid-configuration"

    @property
    def authorization_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/auth"

    @property
    def token_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/token"

    @property
    def userinfo_endpoint(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/userinfo"

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer}/protocol/openid-connect/certs"

    def discovery_document(self) -> Dict[str, Any]:
        return {
            "issuer": self.issuer,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
        }

    def jwks(self) -> Dict[str, Any]:
        public_jwk = json.loads(RSAAlgorithm.to_jwk(self.private_key.public_key()))
        public_jwk["kid"] = KID
        public_jwk["alg"] = "RS256"
        public_jwk["use"] = "sig"
        return {"keys": [public_jwk]}

    def mint_id_token(
        self,
        nonce: Optional[str] = None,
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
        expires_in: int = 300,
        extra_claims: Optional[Dict[str, Any]] = None,
        sign_with: Optional[rsa.RSAPrivateKey] = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": issuer or self.issuer,
            "aud": audience or self.client_id,
            "sub": "user-subject-123",
            "iat": now,
            "exp": now + expires_in,
            "email": self.email,
            "name": self.full_name,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        claims.update(self.role_claims())
        if extra_claims:
            claims.update(extra_claims)
        return jwt.encode(
            claims,
            sign_with or self.private_key,
            algorithm="RS256",
            headers={"kid": KID},
        )

    def userinfo(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = {
            "sub": "user-subject-123",
            "email": self.email,
            "email_verified": True,
            "name": self.full_name,
        }
        data.update(self.role_claims())
        if extra:
            data.update(extra)
        return data

    def register_all(
        self,
        responses_mock,
        id_token: Optional[str] = None,
        nonce: Optional[str] = None,
        userinfo_extra: Optional[Dict[str, Any]] = None,
    ):
        """Registers discovery, JWKS, token and userinfo endpoints on the mock."""

        responses_mock.add(
            responses_mock.GET, self.discovery_url, json=self.discovery_document()
        )
        responses_mock.add(responses_mock.GET, self.jwks_uri, json=self.jwks())
        responses_mock.add(
            responses_mock.POST,
            self.token_endpoint,
            json={
                "access_token": "test-access-token",
                "token_type": "Bearer",
                "id_token": id_token
                if id_token is not None
                else self.mint_id_token(nonce=nonce),
            },
        )
        responses_mock.add(
            responses_mock.GET,
            self.userinfo_endpoint,
            json=self.userinfo(userinfo_extra),
        )
