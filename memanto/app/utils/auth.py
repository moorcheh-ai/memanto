"""
Authentication and Authorization for MEMANTO
"""

import json
import logging
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from memanto.app.config import settings

logger = logging.getLogger(__name__)

_REQUIRED_ENTRY_FIELDS = {"tenant_id", "roles", "scopes_allowed"}


def _load_tenant_api_keys() -> dict:
    """Load tenant API keys from the MEMANTO_TENANT_API_KEYS environment variable.

    Expected format (JSON):
      {
        "<api_key>": {
          "tenant_id": "<id>",
          "roles": ["admin", "user"],
          "scopes_allowed": ["user", "workspace", "agent", "session"]
        }
      }

    Returns an empty dict when the variable is unset so that the server starts
    in a restricted state rather than with demo credentials.
    """
    raw = os.getenv("MEMANTO_TENANT_API_KEYS", "")
    if not raw:
        logger.warning(
            "MEMANTO_TENANT_API_KEYS is not set — API-key authentication is disabled. "
            "Set this environment variable to enable tenant API keys."
        )
        return {}
    try:
        keys = json.loads(raw)
        if not isinstance(keys, dict):
            raise ValueError("must be a JSON object")
        for api_key, entry in keys.items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"entry for key '{api_key}' must be a JSON object"
                )
            if not api_key.startswith("tk_"):
                raise ValueError(
                    f"API key '{api_key[:8]}…' does not start with 'tk_' — "
                    "all keys in MEMANTO_TENANT_API_KEYS must use the 'tk_' prefix"
                )
            missing = _REQUIRED_ENTRY_FIELDS - entry.keys()
            if missing:
                raise ValueError(
                    f"entry for key '{api_key}' is missing required fields: {sorted(missing)}"
                )
        return keys
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(
            "MEMANTO_TENANT_API_KEYS is set but could not be parsed as JSON: "
            f"{exc}"
        ) from exc


def _load_jwt_secret() -> str:
    """Return the JWT signing secret from the environment.

    Raises RuntimeError on startup when no secret is configured so that the
    server never silently falls back to a publicly known default value.
    """
    secret = os.getenv("JWT_SECRET") or getattr(settings, "JWT_SECRET", None)
    if not secret or not secret.strip():
        raise RuntimeError(
            "JWT_SECRET is not configured. "
            "Set the JWT_SECRET environment variable to a strong random value."
        )
    return secret.strip()


class AuthenticatedUser(BaseModel):
    """Authenticated user/tenant information"""

    tenant_id: str
    roles: list[str] = []
    scopes_allowed: list[str] = []
    auth_method: str  # "api_key" or "jwt"


class AuthService:
    """Authentication and authorization service"""

    def __init__(self):
        self.tenant_api_keys = _load_tenant_api_keys()

        # JWT configuration — secret is mandatory; raises on missing config
        self.jwt_secret = _load_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.jwt_issuer = getattr(settings, "JWT_ISSUER", "memanto")

    def authenticate_api_key(self, api_key: str) -> AuthenticatedUser | None:
        """Authenticate using API key"""
        tenant_info = self.tenant_api_keys.get(api_key)
        if not tenant_info:
            return None

        return AuthenticatedUser(
            tenant_id=tenant_info["tenant_id"],
            roles=tenant_info["roles"],
            scopes_allowed=tenant_info["scopes_allowed"],
            auth_method="api_key",
        )

    def authenticate_jwt(self, token: str) -> AuthenticatedUser | None:
        """Authenticate using JWT"""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                issuer=self.jwt_issuer,
                options={"verify_exp": True},
            )

            return AuthenticatedUser(
                tenant_id=payload["tenant_id"],
                roles=payload.get("roles", []),
                scopes_allowed=payload.get("scopes_allowed", []),
                auth_method="jwt",
            )

        except jwt.InvalidTokenError:
            return None

    def authenticate(
        self, credentials: HTTPAuthorizationCredentials
    ) -> AuthenticatedUser:
        """Main authentication method"""
        token = credentials.credentials

        # Try API key first (starts with tk_)
        if token.startswith("tk_"):
            user = self.authenticate_api_key(token)
            if user:
                return user

        # Try JWT
        user = self.authenticate_jwt(token)
        if user:
            return user

        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )

    def authorize_scope(
        self, user: AuthenticatedUser, scope_type: str, scope_id: str
    ) -> bool:
        """Authorize access to specific scope"""
        # Check if scope type is allowed
        if scope_type not in user.scopes_allowed:
            return False

        # For user scopes, ensure user can only access their own data
        if scope_type == "user" and not scope_id.startswith(f"u_{user.tenant_id}_"):
            # Allow if scope_id matches tenant pattern or is generic
            if scope_id not in [f"u_{user.tenant_id}", user.tenant_id]:
                return False

        return True

    def validate_tenant_consistency(
        self, user: AuthenticatedUser, request_tenant_id: str
    ):
        """Validate that request tenant matches authenticated tenant"""
        if user.tenant_id != request_tenant_id:
            raise HTTPException(
                status_code=403,
                detail=f"Tenant mismatch: authenticated as {user.tenant_id}, requested {request_tenant_id}",
            )


# Global auth service
auth_service = AuthService()
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    """Dependency to get current authenticated user"""
    return auth_service.authenticate(credentials)


def require_scope_access(scope_type: str, scope_id: str):
    """Dependency factory for scope-based authorization"""

    def _check_scope(user: AuthenticatedUser = Depends(get_current_user)):
        if not auth_service.authorize_scope(user, scope_type, scope_id):
            raise HTTPException(
                status_code=403, detail=f"Access denied to {scope_type}:{scope_id}"
            )
        return user

    return _check_scope


def validate_request_tenant(user: AuthenticatedUser, request_tenant_id: str):
    """Validate tenant consistency - never trust request body for tenant"""
    auth_service.validate_tenant_consistency(user, request_tenant_id)


def extract_tenant_from_auth(authorization: str) -> str:
    """Extract tenant from Authorization header"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization")
    return authorization.replace("Bearer ", "")
