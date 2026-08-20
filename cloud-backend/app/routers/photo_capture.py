import base64
import json
import logging
import re

import httpx
from dateutil import parser as dateutil_parser
from fastapi import APIRouter, HTTPException, UploadFile

from app import schemas
from app.config import OLLAMA_BASE_URL, OLLAMA_VISION_MODEL

logger = logging.getLogger(__name__)
router = APIRouter(tags=["photo-capture"])

EXTRACTION_PROMPT = (
    "This is a photo of a glucometer or continuous glucose monitor display. "
    "Extract the glucose reading value and any visible date/time text. "
    "Respond with ONLY a JSON object, no other text, in this exact shape: "
    '{"glucose_mg_dl": <number or null>, "datetime_text": "<exact text as shown on the '
    'display, or null if none is visible>"}'
)

# A vision model wraps JSON in prose or ```json fences more often than not —
# pull out the first {...} block rather than trust the whole response is bare JSON.
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


@router.post("/readings/photo-extract", response_model=schemas.PhotoExtractResponse)
async def extract_reading_from_photo(photo: UploadFile):
    """Best-effort glucose value + timestamp extraction from an uploaded photo,
    via a local Ollama vision model (no cloud API, no per-call cost, no key to
    manage). Deliberately does NOT create a reading — the extracted value must
    be reviewed (and corrected if needed) by the caller before a separate
    POST /readings/manual, since a misread digit here would otherwise land
    straight in the hypo-drop alert engine unverified."""
    image_bytes = await photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty photo upload")

    image_b64 = base64.b64encode(image_bytes).decode()

    payload = {
        "model": OLLAMA_VISION_MODEL,
        "prompt": EXTRACTION_PROMPT,
        "images": [image_b64],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not reach local Ollama at {OLLAMA_BASE_URL} — is `ollama serve` "
                "running? (`ollama list` should show it, and the vision model must be "
                f"pulled: `ollama pull {OLLAMA_VISION_MODEL}`)"
            ),
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Ollama returned an error: {exc.response.text}"
        ) from exc

    model_text = resp.json().get("response", "")

    match = _JSON_BLOCK_RE.search(model_text)
    if not match:
        logger.warning("Photo extraction: no JSON found in model response: %r", model_text)
        return schemas.PhotoExtractResponse(
            glucose_mg_dl=None,
            datetime_text=None,
            parsed_timestamp=None,
            warning="Couldn't parse a reading from this photo — enter it manually below.",
        )

    try:
        extracted = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Photo extraction: malformed JSON from model: %r", match.group(0))
        return schemas.PhotoExtractResponse(
            glucose_mg_dl=None,
            datetime_text=None,
            parsed_timestamp=None,
            warning="Couldn't parse a reading from this photo — enter it manually below.",
        )

    glucose_mg_dl = extracted.get("glucose_mg_dl")
    datetime_text = extracted.get("datetime_text")

    parsed_timestamp = None
    if datetime_text:
        try:
            parsed_timestamp = dateutil_parser.parse(datetime_text, fuzzy=True)
        except (ValueError, OverflowError):
            parsed_timestamp = None

    warning = None
    if glucose_mg_dl is None:
        warning = "No glucose value found in this photo — enter it manually below."
    elif not (20 <= glucose_mg_dl <= 800):
        warning = (
            f"Extracted value ({glucose_mg_dl} mg/dL) is outside a plausible range — "
            "double-check it before submitting."
        )

    return schemas.PhotoExtractResponse(
        glucose_mg_dl=glucose_mg_dl,
        datetime_text=datetime_text,
        parsed_timestamp=parsed_timestamp,
        warning=warning,
    )
