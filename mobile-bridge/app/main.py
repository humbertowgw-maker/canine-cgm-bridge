import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from app import calibration, forwarder, parser, pet_profile
from app.models import (
    CalibrationCoefficients,
    CalibrationSubmission,
    PetProfile,
    PetProfileCreate,
    PetProfileUpdate,
    TelemetryFrame,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Canine CGM Bridge — mobile-bridge")


@app.get("/health")
def health():
    return {"status": "ok"}


async def process_frame(frame: TelemetryFrame) -> dict:
    """Shared by the HTTP and WS ingestion paths: compute a local live estimate
    from cached coefficients, then forward the reading to cloud-backend (the
    canonical source of truth) for the final, authoritative estimate."""
    coefficients = calibration.get_cached_coefficients(frame.dog_id)
    local_estimate = calibration.apply_calibration(
        frame.raw_value, coefficients.slope, coefficients.intercept
    )

    remote = await forwarder.forward_reading(
        {
            "dog_id": frame.dog_id,
            "timestamp": frame.timestamp.isoformat(),
            "raw_value": frame.raw_value,
            "temperature_f": frame.temperature_f,
            "mobile_estimated_glucose_mg_dl": local_estimate,
            "source": "simulator",
        }
    )

    if remote is None:
        logger.error(
            "Reading for dog_id=%s dropped: cloud-backend unreachable after retries",
            frame.dog_id,
        )
        return {
            "status": "error",
            "detail": "cloud-backend unreachable",
            "mobile_estimated_glucose_mg_dl": local_estimate,
        }

    return {
        "status": "ok",
        "reading_id": remote["reading"]["id"],
        "cloud_estimated_glucose_mg_dl": remote["reading"]["estimated_glucose_mg_dl"],
        "mobile_estimated_glucose_mg_dl": local_estimate,
    }


@app.post("/telemetry/frame")
async def receive_frame(payload: dict):
    try:
        frame = parser.parse_frame(payload)
    except parser.FrameParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await process_frame(frame)


@app.websocket("/telemetry/stream")
async def telemetry_stream(websocket: WebSocket):
    """Same frame schema as POST /telemetry/frame, one JSON message per frame.
    Replies per-message with {"status":"ok","reading_id":...} or
    {"status":"error","detail":...}; a parse error keeps the socket open (client
    can retry the next frame). Client sends frames sequentially, awaiting each ack
    before the next — simple backpressure. Forwarding to cloud-backend happens
    synchronously inside this same handler, consistent with the no-queue scope
    decision used throughout the project."""
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                frame = parser.parse_frame(payload)
            except parser.FrameParseError as exc:
                await websocket.send_json({"status": "error", "detail": str(exc)})
                continue

            result = await process_frame(frame)
            if result["status"] == "ok":
                await websocket.send_json(
                    {"status": "ok", "reading_id": result["reading_id"]}
                )
            else:
                await websocket.send_json(
                    {"status": "error", "detail": result["detail"]}
                )
    except WebSocketDisconnect:
        logger.info("Telemetry WS stream disconnected")


@app.post("/profile", response_model=PetProfile, status_code=201)
async def create_profile(profile_in: PetProfileCreate):
    remote = await forwarder.forward_profile(
        {
            "name": profile_in.name,
            "breed": profile_in.breed,
            "weight_kg": profile_in.weight_kg,
            "target_range_low_mg_dl": profile_in.target_range_low_mg_dl,
            "target_range_high_mg_dl": profile_in.target_range_high_mg_dl,
            "feeding_schedule": profile_in.feeding_schedule,
        }
    )
    if remote is None:
        raise HTTPException(status_code=502, detail="cloud-backend unreachable; could not create dog")

    profile = PetProfile(
        dog_id=remote["id"],
        name=remote["name"],
        breed=remote["breed"],
        weight_kg=remote["weight_kg"],
        target_range_low_mg_dl=remote["target_range_low_mg_dl"],
        target_range_high_mg_dl=remote["target_range_high_mg_dl"],
        feeding_schedule=remote["feeding_schedule"],
    )
    pet_profile.save_profile(profile)
    await calibration.refresh_cache_from_cloud(profile.dog_id)
    return profile


@app.get("/profile/{dog_id}", response_model=PetProfile)
def get_profile(dog_id: int):
    profile = pet_profile.get_profile(dog_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Pet profile not found locally")
    return profile


@app.put("/profile/{dog_id}", response_model=PetProfile)
async def update_profile(dog_id: int, update_in: PetProfileUpdate):
    existing = pet_profile.get_profile(dog_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Pet profile not found locally")

    updates = update_in.model_dump(exclude_unset=True)
    remote = await forwarder.forward_profile_update(dog_id, updates)
    if remote is None:
        raise HTTPException(status_code=502, detail="cloud-backend unreachable; could not update dog")

    updated = pet_profile.update_profile(
        dog_id,
        name=remote["name"],
        breed=remote["breed"],
        weight_kg=remote["weight_kg"],
        target_range_low_mg_dl=remote["target_range_low_mg_dl"],
        target_range_high_mg_dl=remote["target_range_high_mg_dl"],
        feeding_schedule=remote["feeding_schedule"],
    )
    return updated


@app.post("/calibration/submit", response_model=CalibrationCoefficients)
async def submit_calibration(submission: CalibrationSubmission):
    return await calibration.submit_calibration_point(submission)


@app.get("/calibration/current/{dog_id}", response_model=CalibrationCoefficients)
def get_current_calibration(dog_id: int):
    return calibration.get_cached_coefficients(dog_id)
