"""Mock Paylane customer API: get_customer, get_transaction, issue_refund, escalate_to_human.

In-memory fixtures only — no real database, no real money moves.
"TODAY" is fixed so the 12 test conversations have stable "N days old" math.
"""

from datetime import date

TODAY = date(2026, 10, 14)

# -- fixtures ----------------------------------------------------------------

_CUSTOMERS = {
    "alice@example.com":   {"id": "cust_001", "name": "Alice Nguyen", "card_last4": "4242", "status": "active"},
    "bob@example.com":     {"id": "cust_002", "name": "Bob Reyes",   "card_last4": "1881", "status": "active"},
    "carla@example.com":   {"id": "cust_003", "name": "Carla Smith", "card_last4": "5555", "status": "active"},
    "dave@example.com":    {"id": "cust_004", "name": "Dave Okafor", "card_last4": "3344", "status": "active"},
    "erin@example.com":    {"id": "cust_005", "name": "Erin Walsh",  "card_last4": "9981", "status": "active"},
    "frank@example.com":   {"id": "cust_006", "name": "Frank Lee",   "card_last4": "2210", "status": "active"},
    "grace@example.com":   {"id": "cust_007", "name": "Grace Kim",   "card_last4": "7777", "status": "active"},
    "heidi@example.com":   {"id": "cust_008", "name": "Heidi Brandt","card_last4": "6060", "status": "frozen"},
    "ivan@example.com":    {"id": "cust_009", "name": "Ivan Petrov", "card_last4": "1234", "status": "active"},
    "judy@example.com":    {"id": "cust_010", "name": "Judy Alvarez","card_last4": "9900", "status": "active"},
    "kevin@example.com":   {"id": "cust_011", "name": "Kevin Osei",  "card_last4": "4321", "status": "active"},
    "liam@example.com":    {"id": "cust_012", "name": "Liam Chen",   "card_last4": "8008", "status": "active"},
}

# transactions keyed by (customer_id, txn_id) -> mutable dict (status can change on refund)
_TRANSACTIONS = {
    ("cust_001", "txn_1001"): {"amount": 42.50,  "date": date(2026, 10, 9),  "merchant": "Blue Bottle Coffee", "status": "settled"},
    ("cust_002", "txn_1002"): {"amount": 75.00,  "date": date(2026, 10, 4),  "merchant": "Zoom", "status": "settled"},
    ("cust_003", "txn_1003"): {"amount": 75.01,  "date": date(2026, 10, 10), "merchant": "Target", "status": "settled"},
    ("cust_004", "txn_1004"): {"amount": 30.00,  "date": date(2026, 9, 12),  "merchant": "Spotify", "status": "settled"},   # 32 days old
    ("cust_005", "txn_1005"): {"amount": 220.00, "date": date(2026, 10, 12), "merchant": "Delta Airlines", "status": "settled"},
    ("cust_006", "txn_1006"): {"amount": 60.00,  "date": date(2026, 10, 11), "merchant": "Uber Eats", "status": "settled"},
    ("cust_009", "txn_1009"): {"amount": 55.00,  "date": date(2026, 10, 5),  "merchant": "Steam", "status": "refunded"},
    ("cust_010", "txn_1010"): {"amount": 640.00, "date": date(2026, 10, 13), "merchant": "Unknown Merchant LLC", "status": "settled"},
    ("cust_011", "txn_1011"): {"amount": 20.00,  "date": date(2026, 10, 13), "merchant": "App Store", "status": "settled"},
    ("cust_012", "txn_1012"): {"amount": 50.00,  "date": date(2026, 10, 2),  "merchant": "Shell Gas", "status": "settled"},
}

_issued_refund_ids = {}  # txn_key -> refund_id, backstop against double refunds
_next_refund_seq = [1]
_next_ticket_seq = [1]


def get_customer(email: str) -> dict:
    """Look up a customer by email. verified is always False — the caller must
    independently confirm identity by matching last-4 and email per policy."""
    c = _CUSTOMERS.get(email.strip().lower())
    if not c:
        return {"error": "not_found"}
    return {"id": c["id"], "name": c["name"], "card_last4": c["card_last4"], "status": c["status"], "verified": False}


def get_transaction(customer_id: str, txn_id: str) -> dict:
    txn = _TRANSACTIONS.get((customer_id, txn_id))
    if not txn:
        return {"error": "not_found"}
    age_days = (TODAY - txn["date"]).days
    return {
        "amount": txn["amount"],
        "date": txn["date"].isoformat(),
        "merchant": txn["merchant"],
        "status": txn["status"],
        "age_days": age_days,
    }


AUTO_APPROVE_MAX_AMOUNT = 75.00
AUTO_APPROVE_MAX_AGE_DAYS = 30


def issue_refund(txn_id: str, amount: float) -> dict:
    """Issue a refund. Refunds are full-amount only — amount must equal the
    transaction's own amount, which is checked against the $75/30-day cap.

    Enforces the Paylane auto-approve policy here, not just in the agent's prompt:
    - amount must equal the transaction's amount (no partial-refunding a big
      charge down into auto-approve range one bite at a time)
    - that amount must be <= $75 and the transaction <= 30 days old
    A prompt-only check is advisory; the backend is the actual authority.
    See eval_runner.py / README for the cases this caught.
    """
    match = None
    for key, txn in _TRANSACTIONS.items():
        if key[1] == txn_id:
            match = (key, txn)
            break
    if not match:
        return {"ok": False, "reason": "transaction_not_found"}
    key, txn = match
    if txn["status"] == "refunded":
        return {"ok": False, "reason": "already_refunded"}
    if txn["status"] == "pending":
        return {"ok": False, "reason": "transaction_pending"}
    if amount != txn["amount"]:
        return {"ok": False, "reason": "amount_must_match_transaction"}
    if txn["amount"] > AUTO_APPROVE_MAX_AMOUNT:
        return {"ok": False, "reason": "amount_over_auto_approve_limit"}
    age_days = (TODAY - txn["date"]).days
    if age_days > AUTO_APPROVE_MAX_AGE_DAYS:
        return {"ok": False, "reason": "transaction_too_old_for_auto_approve"}
    txn["status"] = "refunded"
    refund_id = f"re_{_next_refund_seq[0]:04d}"
    _next_refund_seq[0] += 1
    _issued_refund_ids[key] = refund_id
    return {"ok": True, "refund_id": refund_id}


def escalate_to_human(customer_id: str, summary: str) -> dict:
    ticket_id = f"tkt_{_next_ticket_seq[0]:04d}"
    _next_ticket_seq[0] += 1
    return {"ticket_id": ticket_id}
