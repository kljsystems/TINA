"""TINA Tool — Stripe: revenue, subscriptions, and payment data."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import STRIPE_SECRET_KEY

DEFINITIONS = [
    {
        "name": "stripe_overview",
        "description": (
            "Get a live Stripe business overview — MRR, active subscription count, "
            "past-due subscriptions, and recent 30-day revenue. Use for quick financial health checks."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "stripe_revenue",
        "description": "Get total revenue collected via Stripe over the last N days.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back. Defaults to 30.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "stripe_subscriptions",
        "description": "List Stripe subscriptions filtered by status. Returns customer, plan, amount, and dates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "past_due", "canceled", "trialing", "unpaid"],
                    "description": "Filter by subscription status. Defaults to active.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results. Defaults to 20.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "stripe_failed_payments",
        "description": "List recent failed Stripe charges — useful for identifying churn risk and payment issues.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max results. Defaults to 10.",
                },
            },
            "required": [],
        },
    },
]


def _get(endpoint: str, params: list = None) -> dict:
    import httpx
    if not STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY not set in .env")
    with httpx.Client(timeout=20) as client:
        resp = client.get(
            f"https://api.stripe.com/v1/{endpoint}",
            headers={"Authorization": f"Bearer {STRIPE_SECRET_KEY}"},
            params=params or [],
        )
        resp.raise_for_status()
        return resp.json()


def _calc_mrr(subs: list) -> float:
    mrr = 0.0
    for sub in subs:
        for item in sub.get("items", {}).get("data", []):
            price = item.get("price", {})
            amount = (price.get("unit_amount") or 0) / 100
            qty = item.get("quantity", 1)
            interval = price.get("recurring", {}).get("interval", "month")
            interval_count = price.get("recurring", {}).get("interval_count", 1)
            if interval == "month":
                mrr += amount * qty / interval_count
            elif interval == "year":
                mrr += amount * qty / (12 * interval_count)
            elif interval == "week":
                mrr += amount * qty * (52 / 12) / interval_count
    return mrr


def handle(name: str, inputs: dict) -> str:
    try:
        if name == "stripe_overview":
            active = _get("subscriptions", [
                ("status", "active"), ("limit", "100"),
                ("expand[]", "data.items"), ("expand[]", "data.customer"),
            ])
            past_due = _get("subscriptions", [("status", "past_due"), ("limit", "100")])
            since_30d = int(time.time()) - (30 * 86400)
            charges = _get("charges", [
                ("created[gte]", str(since_30d)), ("limit", "100"), ("paid", "true"),
            ])

            active_list = active.get("data", [])
            mrr = _calc_mrr(active_list)
            revenue_30d = sum(c.get("amount", 0) / 100 for c in charges.get("data", []))

            lines = ["STRIPE OVERVIEW\n"]
            lines.append(f"  MRR (est.):          ${mrr:,.2f}")
            lines.append(f"  Active subscriptions: {len(active_list)}")
            lines.append(f"  Past-due:             {len(past_due.get('data', []))}")
            lines.append(f"  Revenue (30d):        ${revenue_30d:,.2f}")

            if active_list:
                lines.append("\nRECENT ACTIVE SUBSCRIPTIONS:")
                for sub in active_list[:5]:
                    customer = sub.get("customer", {})
                    email = customer.get("email", sub.get("customer", "?")) if isinstance(customer, dict) else sub.get("customer", "?")
                    items = sub.get("items", {}).get("data", [])
                    plan_name = items[0].get("price", {}).get("nickname") or items[0].get("price", {}).get("id", "?") if items else "?"
                    amount = sum(
                        (i.get("price", {}).get("unit_amount", 0) / 100) * i.get("quantity", 1)
                        for i in items
                    )
                    lines.append(f"  {email}  —  {plan_name}  ${amount:.2f}/mo")

            return "\n".join(lines)

        if name == "stripe_revenue":
            days = int(inputs.get("days", 30))
            since = int(time.time()) - (days * 86400)
            charges = _get("charges", [
                ("created[gte]", str(since)), ("limit", "100"), ("paid", "true"),
            ])
            refunds = _get("refunds", [("created[gte]", str(since)), ("limit", "100")])

            gross = sum(c.get("amount", 0) / 100 for c in charges.get("data", []))
            refunded = sum(r.get("amount", 0) / 100 for r in refunds.get("data", []))
            net = gross - refunded
            count = len(charges.get("data", []))

            lines = [f"STRIPE REVENUE — last {days} days\n"]
            lines.append(f"  Gross:     ${gross:,.2f}")
            lines.append(f"  Refunds:   ${refunded:,.2f}")
            lines.append(f"  Net:       ${net:,.2f}")
            lines.append(f"  Payments:  {count}")
            if count:
                lines.append(f"  Avg:       ${gross/count:,.2f}")
            return "\n".join(lines)

        if name == "stripe_subscriptions":
            status = inputs.get("status", "active")
            limit = int(inputs.get("limit", 20))
            subs = _get("subscriptions", [
                ("status", status), ("limit", str(limit)),
                ("expand[]", "data.customer"), ("expand[]", "data.items"),
            ])
            data = subs.get("data", [])
            if not data:
                return f"No {status} subscriptions found."

            lines = [f"STRIPE SUBSCRIPTIONS — {status.upper()} ({len(data)})\n"]
            for sub in data:
                customer = sub.get("customer", {})
                email = customer.get("email", "?") if isinstance(customer, dict) else "?"
                items = sub.get("items", {}).get("data", [])
                plan = items[0].get("price", {}).get("nickname") or items[0].get("price", {}).get("id", "?") if items else "?"
                amount = sum(
                    (i.get("price", {}).get("unit_amount", 0) / 100) * i.get("quantity", 1)
                    for i in items
                )
                created = sub.get("current_period_start", 0)
                from datetime import datetime
                date_str = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d") if created else "?"
                lines.append(f"  {email}  —  {plan}  ${amount:.2f}  (since {date_str})")
            return "\n".join(lines)

        if name == "stripe_failed_payments":
            limit = int(inputs.get("limit", 10))
            charges = _get("charges", [
                ("limit", str(limit)), ("paid", "false"),
                ("expand[]", "data.customer"),
            ])
            data = charges.get("data", [])
            if not data:
                return "No failed payments found."

            lines = [f"STRIPE FAILED PAYMENTS ({len(data)})\n"]
            for charge in data:
                customer = charge.get("customer", {})
                email = customer.get("email", "?") if isinstance(customer, dict) else "?"
                amount = charge.get("amount", 0) / 100
                reason = charge.get("failure_message") or charge.get("failure_code") or "unknown"
                from datetime import datetime
                date_str = datetime.utcfromtimestamp(charge.get("created", 0)).strftime("%Y-%m-%d")
                lines.append(f"  [{date_str}] {email}  ${amount:.2f}  — {reason}")
            return "\n".join(lines)

        return f"Unknown tool: {name}"

    except Exception as e:
        return f"Stripe error: {e}"
