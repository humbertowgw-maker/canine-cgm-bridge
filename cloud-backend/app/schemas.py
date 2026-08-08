from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---- Dogs ----


class DogCreate(BaseModel):
    name: str
    breed: str
    weight_kg: float
    target_range_low_mg_dl: float | None = None
    target_range_high_mg_dl: float | None = None
    feeding_schedule: list[str] | None = None


class DogUpdate(BaseModel):
    name: str | None = None
    breed: str | None = None
    weight_kg: float | None = None
    target_range_low_mg_dl: float | None = None
    target_range_high_mg_dl: float | None = None
    feeding_schedule: list[str] | None = None


class DogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    breed: str
    weight_kg: float
    target_range_low_mg_dl: float
    target_range_high_mg_dl: float
    feeding_schedule: list[str]
    created_at: datetime
    updated_at: datetime


# ---- Calibration ----


class CalibrationEventCreate(BaseModel):
    reference_bg_mg_dl: float
    raw_value: float
    timestamp: datetime


class CalibrationCoefficientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dog_id: int
    slope: float
    intercept: float
    r_squared: float
    point_count: int
    is_active: bool
    is_trusted: bool
    computed_at: datetime


# ---- Readings ----


class ReadingCreate(BaseModel):
    dog_id: int
    timestamp: datetime
    raw_value: float
    temperature_f: float
    mobile_estimated_glucose_mg_dl: float | None = None
    source: str = "live"


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dog_id: int
    timestamp: datetime
    raw_value: float
    temperature_f: float
    estimated_glucose_mg_dl: float
    mobile_estimated_glucose_mg_dl: float | None
    calibration_coefficient_id: int
    source: str
    created_at: datetime


# ---- Alerts ----


class VelocityAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dog_id: int
    glucose_reading_id: int
    timestamp: datetime
    velocity_mg_dl_per_min: float
    is_hypo_drop_flag: bool
    severity: str
    created_at: datetime


class ReadingResponse(BaseModel):
    reading: ReadingOut
    alert: VelocityAlertOut | None = None


class VelocityOut(BaseModel):
    dog_id: int
    velocity_mg_dl_per_min: float | None
    as_of: datetime | None
    message: str | None = Field(
        default=None, description="Set when there isn't enough history to compute velocity"
    )
