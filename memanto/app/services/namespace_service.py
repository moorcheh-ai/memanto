"""
Namespace Service
"""

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from moorcheh_sdk import MoorchehClient

from memanto.app.constants import ScopeType
from memanto.app.core import create_memory_scope, validate_namespace_format
from memanto.app.utils.errors import NamespaceError


class NamespaceService:
    def __init__(self, moorcheh_client: "MoorchehClient"):
        self.client = moorcheh_client

    def create_namespace(self, scope_type: ScopeType, scope_id: str) -> str:
        """Create a new namespace, returning it whether new or already existing."""
        scope = create_memory_scope(scope_type, scope_id)
        namespace = cast(str, scope.to_namespace())

        # Validate format before hitting the API
        if not validate_namespace_format(namespace):
            raise NamespaceError(f"Invalid namespace format: {namespace}")

        try:
            # Create in Moorcheh
            self.client.namespaces.create(namespace, type="text")
        except Exception as e:
            # Check for conflict (409) in message or type
            msg = str(e).lower()
            if "conflict" in msg or "409" in msg:
                # Namespace already exists
                pass
            else:
                raise NamespaceError(f"Failed to create namespace: {e}") from e

        return namespace

    def list_namespaces(self) -> list[str]:
        """List all MEMANTO namespaces"""
        try:
            all_namespaces = self.client.namespaces.list()

            # Extract namespace names from response
            if isinstance(all_namespaces, dict) and "namespaces" in all_namespaces:
                namespace_list = [
                    ns["namespace_name"] for ns in all_namespaces["namespaces"]
                ]
            else:
                namespace_list = all_namespaces

            # Filter MEMANTO namespaces
            memanto_namespaces = [
                ns for ns in namespace_list if ns.startswith("memanto_")
            ]

            return memanto_namespaces

        except Exception as e:
            raise NamespaceError(f"Failed to list namespaces: {e}") from e

    def delete_namespace(self, scope_type: ScopeType, scope_id: str) -> bool:
        """Delete a namespace"""
        try:
            scope = create_memory_scope(scope_type, scope_id)
            namespace = scope.to_namespace()

            self.client.namespaces.delete(namespace)
            return True

        except Exception as e:
            raise NamespaceError(f"Failed to delete namespace: {e}") from e

    def namespace_exists(self, scope_type: ScopeType, scope_id: str) -> bool:
        """Check if namespace exists"""
        try:
            scope = create_memory_scope(scope_type, scope_id)
            namespace = scope.to_namespace()

            namespaces = self.list_namespaces()
            return namespace in namespaces

        except Exception:
            return False
