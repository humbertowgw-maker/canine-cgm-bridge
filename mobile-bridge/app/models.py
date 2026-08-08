from datetime import datetime

from pydantic import BaseModel


class TelemetryFrame(BaseModel):
    dog_id: int
    timestamp: datetime
    raw_value: float
    temperature_f: float
    battery_voltage: float | None = None


class PetProfileCreate(BaseModel):
    name: str
    breed: str
    weight_kg: float
    target_range_low_mg_dl: float | None = None
    target_range_high_mg_dl: float | None = None
    feeding_schedule: list[str] | None = None


class PetProfileUpdate(BaseModel):
    name: str | None = None
    breed: str | None = None
    weight_kg: float | None = None
    target_range_low_mg_dl: float | None = None
    target_range_high_mg_dl: float | None = None
    feeding_schedule: list[str] | None = None


class PetProfile(BaseModel):
    """Local mirror of the canonical Dog record held by cloud-backend."""

    dog_id: int
    name: str
    breed: str
    weight_kg: float
    target_range_low_mg_dl: float
    target_range_high_mg_dl: float
    feeding_schedule: list[str]


class CalibrationSubmission(BaseModel):
    dog_id: int
    reference_bg_mg_dl: float
    raw_value: float
    timestamp: datetime


class CalibrationCoefficients(BaseModel):
    dog_id: int
    slope: float
    intercept: float
    is_trusted: bool
    point_count: int
