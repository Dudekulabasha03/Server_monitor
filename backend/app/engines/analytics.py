"""
Lightweight time-series analytics — downsampling, anomaly bands, linear forecast.
Pure Python/statistics (no heavy ML deps). Operates on (timestamp, value) pairs.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Dict, Any, Optional
import statistics

Point = Tuple[datetime, float]


def downsample(points: List[Point], max_points: int = 200) -> List[Dict[str, Any]]:
    """Bucket-average a series down to ~max_points, preserving time order."""
    pts = [(t, v) for t, v in points if v is not None]
    if not pts:
        return []
    if len(pts) <= max_points:
        return [{"t": t.isoformat(), "v": round(v, 2)} for t, v in pts]

    bucket = len(pts) / max_points
    out: List[Dict[str, Any]] = []
    i = 0.0
    idx = 0
    while idx < max_points:
        start = int(i)
        end = int(i + bucket) or start + 1
        chunk = pts[start:end]
        if chunk:
            avg = sum(v for _, v in chunk) / len(chunk)
            mid = chunk[len(chunk) // 2][0]
            out.append({"t": mid.isoformat(), "v": round(avg, 2)})
        i += bucket
        idx += 1
    return out


def rolling_band(points: List[Point], window: int = 12, sigma: float = 2.5) -> Dict[str, Any]:
    """
    Rolling mean ± sigma*std anomaly band.
    Returns actual series, expected (mean) line, upper/lower band, and flagged anomalies.
    """
    pts = [(t, v) for t, v in points if v is not None]
    actual, expected, upper, lower, anomalies = [], [], [], [], []
    vals = [v for _, v in pts]

    for i, (t, v) in enumerate(pts):
        lo = max(0, i - window)
        win = vals[lo:i + 1]
        if len(win) >= 3:
            m = statistics.fmean(win)
            sd = statistics.pstdev(win) or 0.0001
            up, dn = m + sigma * sd, m - sigma * sd
            z = abs(v - m) / sd
            ts = t.isoformat()
            expected.append({"t": ts, "v": round(m, 2)})
            upper.append({"t": ts, "v": round(up, 2)})
            lower.append({"t": ts, "v": round(dn, 2)})
            if v > up or v < dn:
                anomalies.append({"t": ts, "v": round(v, 2), "score": round(z, 2)})
        actual.append({"t": t.isoformat(), "v": round(v, 2)})

    max_score = max((a["score"] for a in anomalies), default=0.0)
    return {
        "actual": actual, "expected": expected, "upper": upper, "lower": lower,
        "anomalies": anomalies, "anomaly_score": round(max_score, 2),
    }


def linreg_forecast(points: List[Point], horizon_hours: int = 24,
                    step_minutes: int = 60, cap: Optional[float] = None) -> Dict[str, Any]:
    """
    Least-squares linear regression over history; project forward.
    Returns actual, forecast (dashed) points, slope/hour, and exhaustion estimate vs cap.
    """
    pts = [(t, v) for t, v in points if v is not None]
    if len(pts) < 3:
        return {"actual": [{"t": t.isoformat(), "v": round(v, 2)} for t, v in pts],
                "forecast": [], "slope_per_hour": 0.0, "exhaustion": None}

    t0 = pts[0][0]
    xs = [(t - t0).total_seconds() / 3600.0 for t, _ in pts]  # hours
    ys = [v for _, v in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1e-9
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
    intercept = my - slope * mx

    last_t = pts[-1][0]
    last_x = xs[-1]
    forecast = []
    steps = int(horizon_hours * 60 / step_minutes)
    for s in range(1, steps + 1):
        fx = last_x + (s * step_minutes / 60.0)
        fy = intercept + slope * fx
        ft = last_t + timedelta(minutes=s * step_minutes)
        forecast.append({"t": ft.isoformat(), "v": round(fy, 2)})

    exhaustion = None
    if cap is not None and slope > 1e-6:
        last_v = ys[-1]
        if last_v < cap:
            hours_to_cap = (cap - last_v) / slope
            exhaustion = (last_t + timedelta(hours=hours_to_cap)).isoformat()

    return {
        "actual": [{"t": t.isoformat(), "v": round(v, 2)} for t, v in pts],
        "forecast": forecast,
        "slope_per_hour": round(slope, 4),
        "exhaustion": exhaustion,
    }


def range_to_delta(rng: str) -> timedelta:
    return {
        "15m": timedelta(minutes=15), "1h": timedelta(hours=1), "6h": timedelta(hours=6),
        "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30),
    }.get(rng, timedelta(hours=24))
