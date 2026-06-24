"""Parser for range values like "50 ± 10 ms" or "12.5 V".

Real-world parameters are written in many ways:
  "50 ms"
  "50 ± 10 ms"
  "50 +/- 10 ms"
  "50..60 ms"
  "12.5 V"
  "10-20 Hz"
  "0.1 s"

The parser returns a dict with keys: nominal, min, max, unit,
tolerance. Unparseable input returns a string-typed value.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# Match "X" (a single value, possibly with unit)
_RE_SINGLE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*([A-Za-zμΩ°%/]+|ms|us|ns|s|min|h|Hz|kHz|MHz|Hz|V|mV|kV|A|mA|kA|W|kW|VA|kVA|kWh|Wh|°C|C|F|N|kN|kg|g|m|cm|mm|km|rpm|MPa|kPa|bar|psi|dB|%)?\s*$"
)

# Match "X ± Y unit" (with ± or +/- sign, possibly Unicode)
# Note: we allow optional whitespace around the sign, but the
# sign itself is a literal char (not a regex char class). This
# avoids pitfalls where `+` in a char class becomes a quantifier
# of the previous group.
_RE_TOLERANCE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:±|\+/-)\s*([+-]?\d+(?:\.\d+)?)\s*"
    r"([A-Za-zμΩ°%/]+|ms|us|ns|s|min|h|Hz|kHz|MHz|V|mV|kV|A|mA|kA|W|kW|VA|kVA|kWh|Wh|°C|C|F|N|kN|kg|g|m|cm|mm|km|rpm|MPa|kPa|bar|psi|dB|%)?\s*$"
)

# Match "X..Y unit" or "X-Y unit" (range)
_RE_RANGE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*(?:\.\.|–|—|-)\s*([+-]?\d+(?:\.\d+)?)\s*"
    r"([A-Za-zμΩ°%/]+|ms|us|ns|s|min|h|Hz|kHz|MHz|V|mV|kV|A|mA|kA|W|kW|VA|kVA|kWh|Wh|°C|C|F|N|kN|kg|g|m|cm|mm|km|rpm|MPa|kPa|bar|psi|dB|%)?\s*$"
)


@dataclass(frozen=True)
class RangeValue:
    """A parsed range / tolerance value."""
    nominal: float
    min: Optional[float]
    max: Optional[float]
    unit: Optional[str]
    tolerance: Optional[float]


def parse_range_value(text: str) -> RangeValue | None:
    """Parse a string like ``"50 ± 10 ms"`` into a ``RangeValue``.

    Returns None if the input is not a parseable numeric value.

    Rules:
      - ``"50 ± 10 ms"``   -> nominal=50, min=40, max=60, unit=ms, tol=10
      - ``"50 ms"``         -> nominal=50, min=max=50, unit=ms, tol=0
      - ``"10..20 Hz"``      -> nominal=15, min=10, max=20, unit=Hz, tol=None
      - ``"12.5 V"``        -> nominal=12.5, min=max=12.5, unit=V
      - ``"50+/-10 ms"``    -> tolerance form (ASCII ±)
    """
    if not text:
        return None
    s = text.strip()
    if not s:
        return None

    # Try tolerance form first (more specific)
    m = _RE_TOLERANCE.match(s)
    if m:
        nominal = float(m.group(1))
        tol = float(m.group(2))
        unit = m.group(3) or None
        return RangeValue(
            nominal=nominal,
            min=nominal - tol,
            max=nominal + tol,
            unit=unit,
            tolerance=tol,
        )

    # Range form
    m = _RE_RANGE.match(s)
    if m:
        lo = float(m.group(1))
        hi = float(m.group(2))
        unit = m.group(3) or None
        return RangeValue(
            nominal=(lo + hi) / 2,
            min=lo,
            max=hi,
            unit=unit,
            tolerance=None,
        )

    # Single value
    m = _RE_SINGLE.match(s)
    if m:
        return RangeValue(
            nominal=float(m.group(1)),
            min=float(m.group(1)),
            max=float(m.group(1)),
            unit=m.group(2) or None,
            tolerance=0.0,
        )

    return None
