# Security bounty #1852: fail-open remote deletion

## Summary

`DELETE /agents/{agent_id}?delete-backup-too=true` previously swallowed every exception raised while deleting the remote Moorcheh namespace. The handler then deleted the local session/agent metadata and returned a success message claiming that all namespace memories had been deleted.

This creates a security/privacy failure mode: an authentication error, backend outage, SDK failure, or other remote deletion error can leave sensitive memory data retained remotely while removing the local metadata needed to identify and retry cleanup.

## Reproduction

1. Create/activate an agent with a remote namespace.
2. Make the remote namespace delete operation fail (for example, use a client stub whose `namespaces.delete()` raises an exception).
3. Call `DELETE /agents/<id>?delete-backup-too=true`.
4. Before this patch, the exception is ignored, local metadata is deleted, and the API reports `successfully deleted with all namespace memories` even though the remote namespace still exists.

The regression test in `tests/test_security_remote_deletion.py` reproduces the failure deterministically without touching production infrastructure.

## Patch

The destructive operation now fails closed. If remote deletion fails, the API returns HTTP 502 and preserves local agent/session metadata so the deletion can be retried. Backend exception details are not exposed to the caller.

This keeps the local recovery handle until the requested remote deletion is confirmed instead of creating an orphaned sensitive-data namespace.