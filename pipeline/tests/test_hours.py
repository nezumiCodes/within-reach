import pytest

from within_reach_pipeline.pharmacies.hours import parse_day_hours


@pytest.mark.parametrize("value", ["CLOSED", "Closed", " closed "])
def test_closed(value: str) -> None:
    assert parse_day_hours(value) == ()


def test_single_range() -> None:
    assert parse_day_hours("09:00-17:00") == (("09:00", "17:00"),)


@pytest.mark.parametrize("value", ["09:00-13:00,14:00-17:30", "09:00-13:00; 14:00-17:30"])
def test_two_ranges(value: str) -> None:
    assert parse_day_hours(value) == (("09:00", "13:00"), ("14:00", "17:30"))


@pytest.mark.parametrize("value", ["ASK", "", "25:00-26:00", "09:00", "17:00-09:00x"])
def test_unparseable_is_unknown(value: str) -> None:
    assert parse_day_hours(value) is None
