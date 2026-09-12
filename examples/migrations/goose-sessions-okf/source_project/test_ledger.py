import re
import unittest

from ledger import audit_line, reconciliation_key

PAYMENT = {
    "merchant_id": "shop-42",
    "external_id": "evt_901",
    "email": "alex@example.com",
    "amount": "49.00 EUR",
}


class LedgerTests(unittest.TestCase):
    def test_reconciliation_key_is_stable_sha256(self):
        key = reconciliation_key(PAYMENT)
        self.assertRegex(key, re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(key, reconciliation_key(dict(PAYMENT)))

    def test_audit_line_does_not_store_customer_email(self):
        line = audit_line(PAYMENT)
        self.assertNotIn(PAYMENT["email"], line)
        self.assertIn("a***@example.com", line)
        self.assertIn(PAYMENT["amount"], line)


if __name__ == "__main__":
    unittest.main()
