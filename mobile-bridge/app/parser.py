from pydantic import ValidationError

from app.models import TelemetryFrame


class FrameParseError(ValueError):
    """Raised when a telemetry frame payload fails validation."""


def parse_frame(payload: dict) -> TelemetryFrame:
    try:
        return TelemetryFrame.model_validate(payload)
    except ValidationError as exc:
        raise FrameParseError(str(exc)) from exc
