from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dog(Base):
    __tablename__ = "dogs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    breed: Mapped[str] = mapped_column(String, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    target_range_low_mg_dl: Mapped[float] = mapped_column(Float, nullable=False)
    target_range_high_mg_dl: Mapped[float] = mapped_column(Float, nullable=False)
    feeding_schedule: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )

    calibration_coefficients: Mapped[list["CalibrationCoefficient"]] = relationship(
        back_populates="dog", foreign_keys="CalibrationCoefficient.dog_id"
    )
    calibration_events: Mapped[list["CalibrationEvent"]] = relationship(back_populates="dog")
    readings: Mapped[list["GlucoseReading"]] = relationship(
        back_populates="dog", foreign_keys="GlucoseReading.dog_id"
    )
    alerts: Mapped[list["VelocityAlert"]] = relationship(back_populates="dog")


class CalibrationCoefficient(Base):
    __tablename__ = "calibration_coefficients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"), nullable=False, index=True)
    slope: Mapped[float] = mapped_column(Float, nullable=False)
    intercept: Mapped[float] = mapped_column(Float, nullable=False)
    r_squared: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    point_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    dog: Mapped["Dog"] = relationship(back_populates="calibration_coefficients", foreign_keys=[dog_id])


class CalibrationEvent(Base):
    __tablename__ = "calibration_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reference_bg_mg_dl: Mapped[float] = mapped_column(Float, nullable=False)
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    dog: Mapped["Dog"] = relationship(back_populates="calibration_events")


class GlucoseReading(Base):
    __tablename__ = "glucose_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    raw_value: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_f: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_glucose_mg_dl: Mapped[float] = mapped_column(Float, nullable=False)
    mobile_estimated_glucose_mg_dl: Mapped[float | None] = mapped_column(Float, nullable=True)
    calibration_coefficient_id: Mapped[int] = mapped_column(
        ForeignKey("calibration_coefficients.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String, nullable=False, default="live")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    dog: Mapped["Dog"] = relationship(back_populates="readings", foreign_keys=[dog_id])
    calibration_coefficient: Mapped["CalibrationCoefficient"] = relationship()


class VelocityAlert(Base):
    __tablename__ = "velocity_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dog_id: Mapped[int] = mapped_column(ForeignKey("dogs.id"), nullable=False, index=True)
    glucose_reading_id: Mapped[int] = mapped_column(
        ForeignKey("glucose_readings.id"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    velocity_mg_dl_per_min: Mapped[float] = mapped_column(Float, nullable=False)
    is_hypo_drop_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    dog: Mapped["Dog"] = relationship(back_populates="alerts")
    reading: Mapped["GlucoseReading"] = relationship()
