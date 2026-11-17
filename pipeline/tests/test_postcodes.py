import pytest

from within_reach_pipeline.postcodes import is_northern_ireland, normalise_postcode


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CH1 1AA", "CH1 1AA"),
        ("ch11aa", "CH1 1AA"),
        ("  ll11   1aa ", "LL11 1AA"),
        ("EH1 1YZ", "EH1 1YZ"),
        ("W1A 0AX", "W1A 0AX"),
        ("M11AE", "M1 1AE"),
        ("GIR0AA", "GIR 0AA"),
    ],
)
def test_normalise_valid(raw: str, expected: str) -> None:
    assert normalise_postcode(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "CH1", "12345", "CH1 1A", "CHH1 1AA", "CH1 1AAA", "C"])
def test_normalise_invalid_returns_none(raw: str) -> None:
    assert normalise_postcode(raw) is None


@pytest.mark.parametrize(
    ("postcode", "expected"),
    [("BT1 1AA", True), ("bt481aa", True), ("B1 1AA", False), ("CH1 1AA", False)],
)
def test_is_northern_ireland(postcode: str, expected: bool) -> None:
    assert is_northern_ireland(postcode) is expected
