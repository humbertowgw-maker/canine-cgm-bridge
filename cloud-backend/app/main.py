import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import alerts, calibration, dogs, readings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Canine CGM Bridge — cloud-backend", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(dogs.router)
app.include_router(readings.router)
app.include_router(calibration.router)
app.include_router(alerts.router)
