import pytest

from app.parser import FrameParseError, parse_frame


def test_parse_valid_frame():
    payload = {
        "dog_id": 1,
        "timestamp": "2026-01-01T07:00:00+00:00",
        "raw_value": 21.6,
        "temperature_f": 101.5,
        "battery_voltage": 3.7,
    }
    frame = parse_frame(payload)
    assert frame.dog_id == 1
    assert frame.raw_value == 21.6
    assert frame.temperature_f == 101.5
    assert frame.battery_voltage == 3.7


def test_parse_valid_frame_without_optional_battery_voltage():
    payload = {
        "dog_id": 1,
        "timestamp": "2026-01-01T07:00:00+00:00",
        "raw_value": 21.6,
        "temperature_f": 101.5,
    }
    frame = parse_frame(payload)
    assert frame.battery_voltage is None


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing everything
        {"dog_id": 1, "timestamp": "2026-01-01T07:00:00+00:00", "raw_value": 21.6},  # missing temperature_f
        {
            "dog_id": "not-an-int",
            "timestamp": "2026-01-01T07:00:00+00:00",
            "raw_value": 21.6,
            "temperature_f": 101.5,
        },
        {
            "dog_id": 1,
            "timestamp": "not-a-timestamp",
            "raw_value": 21.6,
            "temperature_f": 101.5,
        },
    ],
)
def test_parse_invalid_frame_raises(payload):
    with pytest.raises(FrameParseError):
        parse_frame(payload)
