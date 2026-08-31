import stripe

from app.config import STRIPE_PRICE_ID_PRO, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET


def _client() -> stripe.StripeClient:
    if not STRIPE_SECRET_KEY:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    return stripe.StripeClient(STRIPE_SECRET_KEY)


def create_checkout_session(user_id: int, email: str, customer_id: str | None, return_url: str):
    client = _client()
    if not STRIPE_PRICE_ID_PRO:
        raise RuntimeError("STRIPE_PRICE_ID_PRO is not configured")
    params = {
        "mode": "subscription",
        "client_reference_id": str(user_id),
        "line_items": [{"price": STRIPE_PRICE_ID_PRO, "quantity": 1}],
        "subscription_data": {"trial_period_days": 14},
        "success_url": f"{return_url}?checkout=success",
        "cancel_url": f"{return_url}?checkout=canceled",
    }
    if customer_id:
        params["customer"] = customer_id
    else:
        params["customer_email"] = email
    return client.v1.checkout.sessions.create(params)


def verify_webhook_event(payload: bytes, signature: str | None):
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured")
    return stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
