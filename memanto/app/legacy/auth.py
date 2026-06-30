"""
Authentication and Authorization for MEMANTO
"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from memanto.app.config import settings


class AuthenticatedUser(BaseModel):
    """Authenticated user/tenant information"""

    tenant_id: str
    roles: list[str] = []
    scopes_allowed: list[str] = []
    auth_method: str  # "api_key" or "jwt"


class AuthService:
    """Authentication and authorization service"""

    def __init__(self):
        # In production, load from secure storage
        self.tenant_api_keys = {
            # Format: api_key -> tenant_info
            "tk_acme_prod_abc123": {
                "tenant_id": "acme",
                "roles": ["admin", "user"],
                "scopes_allowed": ["user", "workspace", "agent", "session"],
            },
            "tk_demo_test_xyz789": {
                "tenant_id": "demo",
                "roles": ["user"],
                "scopes_allowed": ["user", "agent"],
            },
        }

        # JWT configuration
        self.jwt_secret = getattr(settings, "JWT_SECRET", "dev-secret-change-in-prod")
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
