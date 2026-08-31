from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import billing as billing_service
from app import models, schemas
from app.database import get_db
from app.user_auth import get_current_user_id

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status", response_model=schemas.SubscriptionStatusOut)
def status(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    sub = db.query(models.Subscription).filter(models.Subscription.user_id == user_id).first()
    return schemas.SubscriptionStatusOut(status=sub.status if sub else "none")


@router.post("/checkout", response_model=schemas.CheckoutOut)
def checkout(
    body: schemas.CheckoutRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="not found")
    sub = db.query(models.Subscription).filter(models.Subscription.user_id == user_id).first()

    try:
        session = billing_service.create_checkout_session(
            user_id=user.id,
            email=user.email,
            customer_id=sub.stripe_customer_id if sub else None,
            return_url=body.return_url,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return schemas.CheckoutOut(url=session.url)


# Mounted without require_api_key (see main.py) — Stripe's own signature
# check on the raw body is this route's auth.
@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    try:
        event = billing_service.verify_webhook_event(payload, signature)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature verification failed: {e}")

    obj = event["data"]["object"]

    if event["type"] == "checkout.session.completed":
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.user_id == int(obj["client_reference_id"]))
            .first()
        )
        if sub:
            sub.stripe_customer_id = obj["customer"]
            sub.stripe_subscription_id = obj["subscription"]
            sub.status = "active"
            db.commit()
    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        new_status = "canceled" if event["type"] == "customer.subscription.deleted" else obj["status"]
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.stripe_subscription_id == obj["id"])
            .first()
        )
        if sub:
            sub.status = new_status
            db.commit()

    return {"received": True}
