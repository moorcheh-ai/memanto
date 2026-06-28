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
                raise NamespaceError(f"Failed to create namespace: {e}")

        return namespace

    def list_namespaces(self) -> list[str]:
        """List all MEMANTO namespaces"""
        try:
            all_namespaces = self.client.namespaces.list()

            entries = (
                all_namespaces.get("namespaces", [])
                if isinstance(all_namespaces, dict)
                else all_namespaces
            )
            if isinstance(entries, str):
                entries = [entries]
            if not isinstance(entries, (list, tuple)):
                entries = []

            namespace_list: list[str] = []
            for entry in entries:
                if isinstance(entry, str):
                    namespace_name = entry
                elif isinstance(entry, dict):
                    raw_name = entry.get("namespace_name")
                    if not isinstance(raw_name, str) or not raw_name:
                        raw_name = entry.get("name")
                    if not isinstance(raw_name, str) or not raw_name:
                        continue
                    namespace_name = raw_name
                else:
                    continue

                if namespace_name.startswith("memanto_"):
                    namespace_list.append(namespace_name)

            return namespace_list

        except Exception as e:
            raise NamespaceError(f"Failed to list namespaces: {e}")

    def delete_namespace(self, scope_type: ScopeType, scope_id: str) -> bool:
        """Delete a namespace"""
        try:
            scope = create_memory_scope(scope_type, scope_id)
            namespace = scope.to_namespace()

            self.client.namespaces.delete(namespace)
            return True

        except Exception as e:
            raise NamespaceError(f"Failed to delete namespace: {e}")

    def namespace_exists(self, scope_type: ScopeType, scope_id: str) -> bool:
        """Check if namespace exists"""
        try:
            scope = create_memory_scope(scope_type, scope_id)
            namespace = scope.to_namespace()

            namespaces = self.list_namespaces()
            return namespace in namespaces

        except Exception:
            return False
