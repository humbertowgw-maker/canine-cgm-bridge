#!/usr/bin/env python3
"""Generates a synthetic 24h diabetic-dog glucose curve, converts it to fake raw
sensor values, and streams it into mobile-bridge -- closing the loop with zero
physical hardware and $0 cost. See ~/canine-cgm-bridge/README.md for usage.
"""

import argparse
import asyncio
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

DURATION_HOURS = 24
INTERVAL_MINUTES = 5
NUM_POINTS = int(DURATION_HOURS * 60 / INTERVAL_MINUTES)  # 288

BASELINE_MG_DL = 220.0
FEEDING_TIMES = ["07:00", "17:00"]
MEAL_SPIKE_AMPLITUDE = (80.0, 150.0)
MEAL_SPIKE_SIGMA_MIN = 45.0
INSULIN_TROUGH_DELAY_MIN = 240.0
INSULIN_TROUGH_AMPLITUDE = (100.0, 160.0)
INSULIN_TROUGH_SIGMA_MIN = 90.0
NOISE_SIGMA = 5.0
CLIP_RANGE = (40.0, 450.0)
DRIFT_STEP_SIGMA = 1.5  # per-step random-walk increment (slow sensor/physiological drift)

# Hidden "ground truth" the calibration engine should learn to approximate.
# Deliberately different from the vet-preset bootstrap defaults (slope=1.0,
# intercept=0.0) so calibration convergence is visible in the demo.
TRUE_SLOPE = 9.5
TRUE_INTERCEPT = 15.0
BODY_TEMP_BASELINE_F = 101.5
TEMP_COEFF = 0.02
RAW_NOISE_SIGMA = 0.3

# Auto-submitted before streaming starts, mirroring a real sensor's warm-up
# calibration draws. Without this, the first streamed readings would be computed
# against the naive bootstrap defaults instead of TRUE_SLOPE/TRUE_INTERCEPT, and
# would look like a fake severe-hypoglycemia number instead of a real baseline.
WARMUP_CALIBRATION_POINTS = 5
WARMUP_INTERVAL_MINUTES = 2.0
WARMUP_REFERENCE_LEVELS = [140.0, 190.0, 230.0, 270.0, 310.0]


@dataclass
class CurvePoint:
    t_minutes: float
    timestamp: datetime
    true_glucose_mg_dl: float
    temperature_f: float
    raw_value: float


def _feeding_offsets_minutes() -> list[float]:
    offsets = []
    for t in FEEDING_TIMES:
        hour, minute = (int(x) for x in t.split(":"))
        offsets.append(hour * 60 + minute)
    return offsets


def _gaussian_bump(t_minutes: float, center: float, amplitude: float, sigma: float) -> float:
    return amplitude * math.exp(-((t_minutes - center) ** 2) / (2 * sigma**2))


def glucose_to_raw(glucose_mg_dl: float, temperature_f: float, rng: random.Random) -> float:
    """Inverse of the calibration formula, plus temperature compensation."""
    raw_base = (glucose_mg_dl - TRUE_INTERCEPT) / TRUE_SLOPE
    raw_adjusted = raw_base * (1 + TEMP_COEFF * (temperature_f - BODY_TEMP_BASELINE_F))
    return raw_adjusted + rng.gauss(0, RAW_NOISE_SIGMA)


def generate_curve(start_time: datetime, rng: random.Random) -> list[CurvePoint]:
    feeding_offsets = _feeding_offsets_minutes()
    points: list[CurvePoint] = []
    drift = 0.0

    for i in range(NUM_POINTS):
        t = i * INTERVAL_MINUTES
        value = BASELINE_MG_DL
        for meal_t in feeding_offsets:
            value += _gaussian_bump(
                t, meal_t, rng.uniform(*MEAL_SPIKE_AMPLITUDE), MEAL_SPIKE_SIGMA_MIN
            )
            value -= _gaussian_bump(
                t,
                meal_t + INSULIN_TROUGH_DELAY_MIN,
                rng.uniform(*INSULIN_TROUGH_AMPLITUDE),
                INSULIN_TROUGH_SIGMA_MIN,
            )

        drift += rng.gauss(0, DRIFT_STEP_SIGMA)
        value += drift
        value += rng.gauss(0, NOISE_SIGMA)
        value = max(CLIP_RANGE[0], min(CLIP_RANGE[1], value))

        temperature_f = BODY_TEMP_BASELINE_F + rng.gauss(0, 0.5)
        raw_value = glucose_to_raw(value, temperature_f, rng)

        points.append(
            CurvePoint(
                t_minutes=t,
                timestamp=start_time + timedelta(minutes=t),
                true_glucose_mg_dl=value,
                temperature_f=temperature_f,
                raw_value=raw_value,
            )
        )

    return points


def generate_warmup_points(
    start_time: datetime, rng: random.Random
) -> list[tuple[datetime, float, float]]:
    """[(timestamp, reference_bg_mg_dl, raw_value), ...], timestamped just before
    `start_time` so they precede the streamed curve."""
    levels = WARMUP_REFERENCE_LEVELS[:WARMUP_CALIBRATION_POINTS]
    points = []
    for i, ref_bg in enumerate(levels):
        ts = start_time - timedelta(minutes=(len(levels) - i) * WARMUP_INTERVAL_MINUTES)
        temperature_f = BODY_TEMP_BASELINE_F + rng.gauss(0, 0.3)
        raw = glucose_to_raw(ref_bg, temperature_f, rng)
        points.append((ts, ref_bg, raw))
    return points


async def submit_warmup(
    client: httpx.AsyncClient,
    mobile_bridge_url: str,
    dog_id: int,
    warmup_points: list[tuple[datetime, float, float]],
) -> None:
    print(f"-- Warming up calibration with {len(warmup_points)} reference points --")
    for timestamp, reference_bg, raw_value in warmup_points:
        resp = await client.post(
            f"{mobile_bridge_url}/calibration/submit",
            json={
                "dog_id": dog_id,
                "reference_bg_mg_dl": reference_bg,
                "raw_value": raw_value,
                "timestamp": timestamp.isoformat(),
            },
        )
        resp.raise_for_status()
        coeffs = resp.json()
        print(
            f"  ref={reference_bg:6.1f} mg/dL  raw={raw_value:6.2f}  -> "
            f"slope={coeffs['slope']:.3f} intercept={coeffs['intercept']:.2f} "
            f"trusted={coeffs['is_trusted']} (n={coeffs['point_count']})"
        )


async def stream_http(
    client: httpx.AsyncClient,
    mobile_bridge_url: str,
    dog_id: int,
    points: list[CurvePoint],
    real_seconds_per_point: float,
) -> None:
    for point in points:
        payload = {
            "dog_id": dog_id,
            "timestamp": point.timestamp.isoformat(),
            "raw_value": point.raw_value,
            "temperature_f": point.temperature_f,
        }
        resp = await client.post(f"{mobile_bridge_url}/telemetry/frame", json=payload)
        resp.raise_for_status()
        _print_point(point, resp.json())
        if real_seconds_per_point > 0:
            await asyncio.sleep(real_seconds_per_point)


async def stream_ws(
    mobile_bridge_url: str,
    dog_id: int,
    points: list[CurvePoint],
    real_seconds_per_point: float,
) -> None:
    import websockets

    ws_url = (
        mobile_bridge_url.replace("http://", "ws://").replace("https://", "wss://")
        + "/telemetry/stream"
    )
    async with websockets.connect(ws_url) as ws:
        for point in points:
            payload = {
                "dog_id": dog_id,
                "timestamp": point.timestamp.isoformat(),
                "raw_value": point.raw_value,
                "temperature_f": point.temperature_f,
            }
            await ws.send(json.dumps(payload))
            ack = json.loads(await ws.recv())
            if ack.get("status") == "error":
                print(f"  [WS ERROR] {ack.get('detail')}")
            else:
                _print_point(point, ack)
            if real_seconds_per_point > 0:
                await asyncio.sleep(real_seconds_per_point)


def _print_point(point: CurvePoint, response_body: dict) -> None:
    mobile_est = response_body.get("mobile_estimated_glucose_mg_dl")
    cloud_est = response_body.get("cloud_estimated_glucose_mg_dl")
    mobile_str = f"{mobile_est:.1f}" if mobile_est is not None else "n/a"
    cloud_str = f"{cloud_est:.1f}" if cloud_est is not None else "n/a"
    print(
        f"[{point.timestamp.strftime('%H:%M')}] true={point.true_glucose_mg_dl:6.1f} mg/dL  "
        f"raw={point.raw_value:6.2f}  temp={point.temperature_f:5.1f}F  -> "
        f"mobile_est={mobile_str:>6} cloud_est={cloud_str:>6}"
    )


def _dry_run(points: list[CurvePoint], warmup_points: list[tuple[datetime, float, float]]) -> None:
    print("-- Dry run: no network calls --")
    print(f"{len(warmup_points)} warm-up calibration points, {len(points)} curve points\n")

    values = [p.true_glucose_mg_dl for p in points]
    assert not any(math.isnan(v) for v in values), "NaN in generated curve"
    assert all(CLIP_RANGE[0] <= v <= CLIP_RANGE[1] for v in values), "curve value out of range"

    print("timestamp,true_glucose_mg_dl,raw_value,temperature_f")
    for p in points:
        print(f"{p.timestamp.isoformat()},{p.true_glucose_mg_dl:.2f},{p.raw_value:.3f},{p.temperature_f:.2f}")

    print(
        f"\nmin={min(values):.1f} max={max(values):.1f} mean={sum(values)/len(values):.1f} "
        f"(all within {CLIP_RANGE}, no NaNs) -- OK"
    )


async def _main_async(args: argparse.Namespace) -> None:
    rng = random.Random(args.seed)
    start_time = datetime.now(timezone.utc) if args.start_now else datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )

    warmup_points = generate_warmup_points(start_time, rng)
    curve_points = generate_curve(start_time, rng)

    if args.dry_run:
        _dry_run(curve_points, warmup_points)
        return

    real_seconds_per_point = INTERVAL_MINUTES * 60 / args.speed_factor

    async with httpx.AsyncClient(timeout=10.0) as client:
        await submit_warmup(client, args.mobile_bridge_url, args.dog_id, warmup_points)

        print(
            f"\n-- Streaming {len(curve_points)} points over "
            f"~{len(curve_points) * real_seconds_per_point / 60:.1f} real minutes "
            f"(mode={args.mode}, speed_factor={args.speed_factor}) --"
        )
        if args.mode == "http":
            await stream_http(
                client, args.mobile_bridge_url, args.dog_id, curve_points, real_seconds_per_point
            )
        else:
            await stream_ws(
                args.mobile_bridge_url, args.dog_id, curve_points, real_seconds_per_point
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dog-id", type=int, required=True)
    parser.add_argument("--mobile-bridge-url", default="http://localhost:9000")
    parser.add_argument("--mode", choices=["http", "ws"], default="http")
    parser.add_argument(
        "--speed-factor",
        type=float,
        default=60.0,
        help="Simulated minutes streamed per real second's worth of wall-clock "
        "compression, e.g. 60 streams 24h in ~24 real minutes (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated curve without making any network calls",
    )
    parser.add_argument(
        "--start-now",
        action="store_true",
        help="Use the real current UTC time as the curve's start instead of a fixed date",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()
