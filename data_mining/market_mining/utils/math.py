from __future__ import annotations


def safe_divide(a: float | int | None, b: float | int | None) -> float | None:
    """Return a / b, or None when the operation is not defined."""

    if a is None or b in (None, 0):
        return None
    return float(a) / float(b)


def pct_change(current: float | int | None, previous: float | int | None) -> float | None:
    """Return percentage change as a decimal fraction."""

    if current is None or previous is None:
        return None
    return safe_divide(float(current) - float(previous), previous)


def clip(value: float | int, lower: float | int, upper: float | int) -> float:
    """Clip value to the inclusive [lower, upper] range."""

    return float(max(lower, min(value, upper)))
