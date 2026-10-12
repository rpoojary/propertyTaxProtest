"""Safe parsing of raw county values and summary statistics."""
from datetime import datetime


def to_float(value):
    """Parse '1,234.50', ' 12 ', 12 -> float; blank or junk -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace(",", "").replace("$", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_int(value):
    """Parse '3', '3.0', ' 3 ' -> 3; blank or junk -> None."""
    f = to_float(value)
    return None if f is None else int(f)


def parse_date(value, fmt):
    """Parse a county date string with strptime format `fmt` -> 'YYYY-MM-DD'.

    A trailing time part ('2005-12-29 0:00:00') is ignored. Blank, invalid and
    placeholder dates (year <= 1900) return None.
    """
    if not value:
        return None
    s = str(value).strip().split()[0] if str(value).strip() else ""
    try:
        d = datetime.strptime(s, fmt)
    except ValueError:
        return None
    if d.year <= 1900:
        return None
    return d.strftime("%Y-%m-%d")


def median(values):
    """True median: mean of the two middle values for an even count."""
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2


def summarize(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "median": median(vals),
        "average": sum(vals) / len(vals),
        "low": min(vals),
        "high": max(vals),
    }
