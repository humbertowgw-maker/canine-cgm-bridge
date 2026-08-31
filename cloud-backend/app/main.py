import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, init_db
from app.deps import require_api_key
from app.routers import (
    alerts,
    billing,
    calibration,
    dogs,
    dose_guidance,
    feedings,
    photo_capture,
    readings,
    user_accounts,
)
from app.seed_demo import seed_demo_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Canine CGM Bridge — cloud-backend", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(dogs.router, dependencies=[Depends(require_api_key)])
app.include_router(readings.router, dependencies=[Depends(require_api_key)])
app.include_router(calibration.router, dependencies=[Depends(require_api_key)])
app.include_router(alerts.router, dependencies=[Depends(require_api_key)])
app.include_router(feedings.router, dependencies=[Depends(require_api_key)])
app.include_router(photo_capture.router, dependencies=[Depends(require_api_key)])
app.include_router(dose_guidance.router, dependencies=[Depends(require_api_key)])

# White-label billing scaffolding — its own JWT/Stripe-signature auth (see
# user_auth.py and app/billing.py), not the CGM_SHARED_SECRET gate above.
app.include_router(user_accounts.router)
app.include_router(billing.router)

app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
