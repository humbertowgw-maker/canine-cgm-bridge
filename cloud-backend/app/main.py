import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.deps import require_api_key
from app.routers import alerts, calibration, dogs, feedings, readings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
