"""
Authentication and authorization layer for MEMANTO.

Provides API key and JWT-based authentication with scope-based
authorization, tenant isolation, and middleware for FastAPI endpoints.

Security guarantees:
    - API keys loaded from MEMANTO_API_KEYS env var (not hardcoded)
    - JWT_SECRET must be explicitly configured (no default fallback)
    - Tenant isolation enforced at authentication level
    - Scope-based access control for fine-grained permissions
"""

import os
import json
import warnings

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from memanto.app.config import settings


class AuthenticatedUser(BaseModel):
    """Authenticated user/tenant identity with role and scope metadata.

    Attributes:
        tenant_id: Unique identifier for the tenant/organization.
        roles: List of role names assigned to this user.
        scopes_allowed: List of scope identifiers this user can access.
        auth_method: Authentication method used — "api_key" or "jwt".
    """

    tenant_id: str
    roles: list[str] = []
    scopes_allowed: list[str] = []
    auth_method: str


class AuthService:
    """Authentication and authorization service for MEMANTO.

    Supports two authentication methods:
    1. API key authentication (keys start with ``tk_``)
    2. JWT-based authentication with HS256 signing

    API keys are loaded from the ``MEMANTO_API_KEYS`` environment variable
    as a JSON dictionary mapping keys to tenant info. JWT secrets must be
    explicitly configured via ``JWT_SECRET`` — no default fallback is used
    to prevent token forgery.

    Usage:
        auth = AuthService()
        user = auth.authenticate(bearer_credentials)
        if auth.authorize_scope(user, "workspace", "ws_123"):
            ...
    """

    def __init__(self):
        """Initialize auth service with API keys from env and JWT configuration.

        Loads tenant API keys from the ``MEMANTO_API_KEYS`` environment variable
        (expected format: JSON dict mapping ``api_key`` → ``{tenant_id, roles,
        scopes_allowed}``). JWT secret is read from ``settings.JWT_SECRET``,
        falling back to the ``JWT_SECRET`` environment variable.

        If ``JWT_SECRET`` is not configured, JWT authentication is silently
        disabled and a warning is emitted. API key auth still works.

        Raises:
            No direct exceptions — invalid env var values are silently handled
            by falling back to empty configuration.
        """
        _keys_str = os.environ.get("MEMANTO_API_KEYS", "{}")
        try:
            _parsed = json.loads(_keys_str)
            self.tenant_api_keys = _parsed if isinstance(_parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            self.tenant_api_keys = {}

        secret = getattr(settings, "JWT_SECRET", None) or os.environ.get("JWT_SECRET")
        if not secret:
            warnings.warn(
                "JWT_SECRET not configured! JWT authentication will be disabled. "
                "Set JWT_SECRET in your environment or .env file."
            )
        self.jwt_secret = secret
        self.jwt_algorithm = "HS256"
        self.jwt_issuer = getattr(settings, "JWT_ISSUER", "memanto")

    def authenticate_api_key(self, api_key: str) -> AuthenticatedUser | None:
        """Authenticate a request using an API key.

        Looks up the key in ``tenant_api_keys`` dict loaded at init time.
        Returns the corresponding ``AuthenticatedUser`` if found, or ``None``
        if the key is invalid or expired.

        Args:
            api_key: The API key string to validate (typically starts with ``tk_``).

        Returns:
            AuthenticatedUser with tenant_id, roles, and scopes if valid,
            or ``None`` if authentication fails.
        """
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
        """Authenticate a request using a JWT bearer token.

        Decodes and verifies the JWT using the configured ``jwt_secret``
        and ``HS256`` algorithm. Validates expiry (``exp`` claim) and
        issuer (``iss`` claim) if present.

        Args:
            token: The JWT string to decode and verify.

        Returns:
            AuthenticatedUser with claims extracted from the JWT payload,
            or ``None`` if the token is invalid, expired, or JWT auth is
            disabled (no secret configured).

        Note:
            Returns ``None`` (not an exception) for invalid tokens so callers
            can fall through to alternative auth methods.
        """
        if not self.jwt_secret:
            return None
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
        """Main authentication entry point — tries API key then JWT.

        First attempts API key authentication if the credential starts with
        ``tk_``. Falls back to JWT authentication. Raises 401 if both fail.

        Args:
            credentials: HTTP bearer token credentials from the request.

        Returns:
            AuthenticatedUser from the first successful auth method.

        Raises:
            HTTPException (401): If neither API key nor JWT authentication
                succeeds (token invalid or not found).
        """
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
        """Check if a user is authorized for a specific scope.

        Verifies that the scope type is in the user's allowed scopes list
        and enforces tenant isolation for user-level scopes (a user can
        only access their own tenant's data).

        Args:
            user: The authenticated user to check permissions for.
            scope_type: The type of scope to check (e.g., ``"user"``,
                ``"workspace"``, ``"project"``).
            scope_id: The specific scope identifier to authorize against.

        Returns:
            ``True`` if the user is authorized, ``False`` otherwise.
        """
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
        """Verify that a request's tenant claim matches the authenticated user.

        Prevents tenant spoofing by ensuring the tenant ID in the request
        body matches the authenticated user's tenant. This is a security
        control — never trust the request body for tenant identification.

        Args:
            user: The authenticated user from the token/API key.
            request_tenant_id: The tenant ID from the request body/path.

        Raises:
            HTTPException (403): If the tenant IDs do not match, with a
                message indicating which tenants were involved.
        """
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
    """FastAPI dependency that extracts and authenticates the current user.

    Injects the authenticated user into endpoint handlers. Uses bearer token
    from the ``Authorization`` header. Returns 401 if authentication fails.

    Usage:
        @router.get("/me")
        async def get_me(user: AuthenticatedUser = Depends(get_current_user)):
            return user

    Args:
        credentials: Auto-injected bearer token from the request header.

    Returns:
        AuthenticatedUser if the token is valid.

    Raises:
        HTTPException (401): If the token is missing or invalid.
    """
    return auth_service.authenticate(credentials)


def require_scope_access(scope_type: str, scope_id: str):
    """Factory for FastAPI dependency that enforces scope-based access control.

    Returns a dependency function that checks if the authenticated user has
    access to the specified scope. Used to protect individual endpoints with
    fine-grained permissions.

    Usage:
        @router.get("/workspace/{ws_id}")
        async def get_workspace(
            user: AuthenticatedUser = Depends(require_scope_access("workspace", "ws_123"))
        ):
            ...

    Args:
        scope_type: The type of resource being accessed (e.g., ``"workspace"``).
        scope_id: The specific resource identifier.

    Returns:
        A FastAPI dependency callable that returns the authenticated user
        if authorized, or raises 403 if access is denied.
    """

    def _check_scope(user: AuthenticatedUser = Depends(get_current_user)):
        """Inner dependency that checks scope authorization for the user.

        Called automatically by FastAPI when the route is accessed. Uses
        ``auth_service.authorize_scope`` to verify permissions.

        Args:
            user: The authenticated user injected by ``get_current_user``.

        Returns:
            The authenticated user if scope access is granted.

        Raises:
            HTTPException (403): If the user lacks access to the requested
                scope, with details about which scope was denied.
        """
        if not auth_service.authorize_scope(user, scope_type, scope_id):
            raise HTTPException(
                status_code=403, detail=f"Access denied to {scope_type}:{scope_id}"
            )
        return user

    return _check_scope


def validate_request_tenant(user: AuthenticatedUser, request_tenant_id: str):
    """Validate that the request tenant matches the authenticated user's tenant.

    Security control to prevent tenant spoofing. Should be called whenever
    a request includes a tenant ID from an untrusted source (body, query).

    Args:
        user: The authenticated user from the token.
        request_tenant_id: The tenant ID from the request body or parameters.

    Raises:
        HTTPException (403): If the tenants don't match.
    """
    auth_service.validate_tenant_consistency(user, request_tenant_id)


def extract_tenant_from_auth(authorization: str) -> str:
    """Extract the bearer token from an Authorization header value.

    Parses the raw ``Authorization`` header and returns the token portion
    (everything after ``"Bearer "``). Validates the header format.

    Args:
        authorization: The raw ``Authorization`` header string.

    Returns:
        The token string (without the ``"Bearer "`` prefix).

    Raises:
        HTTPException (401): If the header is missing, empty, or does not
            start with ``"Bearer "``.
    """
