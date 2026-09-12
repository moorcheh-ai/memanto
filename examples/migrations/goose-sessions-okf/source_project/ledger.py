"""Small payment-reconciliation helpers used by the Goose migration demo."""


def reconciliation_key(payment: dict) -> str:
    """Return a key used to collapse duplicate provider events."""
    return str(hash((payment["merchant_id"], payment["external_id"])))


def audit_line(payment: dict) -> str:
    """Return a compact line for the reconciliation audit log."""
    return f"{payment['email']} paid {payment['amount']}"
