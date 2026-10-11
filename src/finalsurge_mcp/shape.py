"""Приведение ответов API Final Surge к компактному виду для модели.

Сырые ответы содержат десятки служебных полей (статусы синхронизаций, права, цвета, URL карты)
и покруговые данные в каждом списке — ~10 КБ на тренировку. Здесь остаётся только то,
что нужно для анализа тренировок: план, факт, круги (в деталях), зоны.
Формат полей сверен с ответами API для тренировок из Garmin, см. tests/test_shape.py.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

ZONE_TYPES = {"H": "heart_rate", "P": "pace", "W": "power"}
# ключевые отрезки кривой мощности, секунды
POWER_CURVE_PERIODS = (5, 15, 30, 60, 300, 600, 1200, 1800, 3600)


def hms(seconds: float | None) -> str | None:
    """3725.4 -> "1:02:05", 95 -> "1:35"."""
    if seconds is None:
        return None
    s = int(seconds + 0.5)  # не round(): банковское округление даёт 5250.5 -> 5250
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def _num(v: Any) -> float | None:
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _round(v: Any, nd: int = 1) -> float | int | None:
    v = _num(v)
    if v is None:
        return None
    r = round(v, nd)
    return int(r) if r == int(r) else r


def amount(value: Any, unit: str | None) -> str | None:
    v = _round(value, 2)
    if not v:
        return None
    return f"{v} {(unit or '').strip()}".strip()


def pace(display: Any, unit: str | None) -> str | None:
    if not display:
        return None
    return f"{display} {(unit or '').strip()}".strip()


def ymd(v: Any) -> str | None:
    return v[:10] if isinstance(v, str) and len(v) >= 10 else None


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Убирает пустое; 0 — тоже (в Final Surge 0 почти всегда значит «нет данных»)."""
    return {k: v for k, v in d.items() if v not in (None, "", [], {}, 0)}


def _val(v: Any) -> Any:
    """Число (в т.ч. строкой "120") -> округлённое число, иначе как есть."""
    try:
        return _round(float(v))
    except (TypeError, ValueError):
        return v


# ----------------------------------------------------------------------------- activities / laps

def planned_part(a: dict[str, Any]) -> dict[str, Any]:
    return _clean({
        "duration": hms(_num(a.get("planned_duration"))),
        "distance": amount(a.get("planned_amount"), a.get("planned_amount_type")),
        "pace": pace(a.get("planned_pace_display"), a.get("planned_pace_display_type"))
        or _pace_range(a),
    })


def _pace_range(a: dict[str, Any]) -> str | None:
    lo, hi = a.get("planned_pace_low"), a.get("planned_pace_high")
    if lo and hi:
        return f"{lo}–{hi} {(a.get('planned_pace_low_type') or '').strip()}".strip()
    return None


def actual_part(a: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
    duration = _num(a.get("duration"))
    moving = _num(a.get("time_moving"))
    elapsed = _num(a.get("time_elapsed"))
    out: dict[str, Any] = {
        "duration": hms(duration),
        "moving": hms(moving) if moving and duration and abs(moving - duration) > 30 else None,
        "elapsed": hms(elapsed) if elapsed and duration and elapsed - duration > 60 else None,
        "distance": amount(a.get("amount"), a.get("amount_type")),
        "pace": pace(a.get("pace_display"), a.get("pace_display_type")),
        "hr_avg": _round(a.get("hr_avg")),
        "hr_max": _round(a.get("hr_max")),
        "power_avg": _round(a.get("power_avg")),
        "power_np": _round(a.get("weighted_power")),
        "cadence_avg": _round(a.get("cadence_avg") or a.get("rpm_avg")),
        "elevation_gain_m": _round(a.get("elevation_gain")),
        "calories": _round(a.get("calories")),
    }
    if detailed:
        out.update({
            "power_max": _round(a.get("power_max")),
            "power_variability": _round(a.get("variability"), 2),
            "power_best_30s": _round(a.get("meanmax_power_30")),
            "power_balance_lr": (
                f"{_round(a.get('left_power_pct_avg'))}/{_round(a.get('right_power_pct_avg'))}"
                if a.get("left_power_pct_avg") and a.get("right_power_pct_avg") else None
            ),
            "cadence_max": _round(a.get("cadence_max") or a.get("rpm_max")),
            "speed_max_kmh": _round(_num(a.get("speed_max")) * 3.6) if _num(a.get("speed_max")) else None,
            "elevation_loss_m": _round(a.get("elevation_loss")),
            # беговая динамика: в FIT/Final Surge — мм и мс
            "ground_contact_ms": _round(a.get("ground_contact_time_avg"), 0),
            "ground_contact_balance_pct": _round(a.get("ground_contact_balance_avg")),
            "vertical_oscillation_cm": _round(_num(a.get("vertical_oscillation_avg")) / 10)
            if _num(a.get("vertical_oscillation_avg")) else None,
            "vertical_ratio_pct": _round(a.get("vertical_ratio_avg")),
            "stride_length_m": _round(_num(a.get("stride_length_avg")) / 1000, 2)
            if _num(a.get("stride_length_avg")) else None,
            "intensity": _round(a.get("intensity"), 2),
        })
    return _clean(out)


def activity(a: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
    sport = a.get("activity_type_name")
    if a.get("activity_sub_type_name"):
        sport = f"{sport} / {a['activity_sub_type_name']}"
    laps = a.get("Laps") or []
    eq = a.get("equipment")
    out = {
        "sport": sport,
        "planned": planned_part(a),
        "actual": actual_part(a, detailed=detailed),
        "equipment": (eq.get("name") if isinstance(eq, dict) else eq) or None,
    }
    if detailed:
        out["laps"] = [lap(x) for x in laps if isinstance(x, dict)]
    elif len(laps) > 1:
        out["laps_count"] = len(laps)
    return _clean(out)


def lap(x: dict[str, Any]) -> dict[str, Any]:
    return _clean({
        "n": x.get("number"),
        "time": hms(_num(x.get("duration"))),
        "distance": amount(x.get("amount"), x.get("amount_type")),
        "pace": pace(x.get("pace_display"), x.get("pace_display_type")),
        "hr_avg": _round(x.get("hr_avg")),
        "hr_max": _round(x.get("hr_max")),
        "power_avg": _round(x.get("power_avg")),
        "cadence_avg": _round(x.get("cadence_avg") or x.get("rpm_avg")),
        "elevation_gain_m": _round(x.get("elevation_gain")),
    })


# ----------------------------------------------------------------------------- workouts

def workout(w: dict[str, Any], *, detailed: bool = False) -> dict[str, Any]:
    out = {
        "workout_key": w.get("key"),
        "date": ymd(w.get("workout_date")),
        "time": (w.get("workout_time") or "")[:5] or None,
        "status": w.get("workout_status_text"),
        "name": w.get("name"),
        "description": w.get("description"),
        "race": _race(w),
        "felt": w.get("felt"),
        "effort": w.get("effort"),
        "notes": w.get("post_workout_notes"),
        "coach": w.get("coach_name"),
        "comments": w.get("CommentCount") or None,
        "structured": True if w.get("has_structured_workout") else None,
        "activities": [activity(a, detailed=detailed) for a in (w.get("Activities") or []) if isinstance(a, dict)],
    }
    if detailed:
        out.update({
            "warm_up": w.get("warm_up"),
            "cool_down": w.get("cool_down"),
            "location": ", ".join(filter(None, (w.get(k) for k in (
                "location_name", "location_city", "location_state", "location_country")))) or None,
            "weather": _weather(w),
            "source": w.get("external_data_source"),
            "pain_points": w.get("pain_point_records") or None,
            "plan": w.get("plan_instance_info") or None,
        })
    return _clean(out)


def _race(w: dict[str, Any]) -> dict[str, Any] | None:
    if not w.get("is_race"):
        return None
    return {"place_overall": w.get("race_place_overall"), "age_group": w.get("race_age_group")}


def _weather(w: dict[str, Any]) -> str | None:
    if w.get("weather_temperature") is None:
        return None
    unit = "°C" if w.get("weather_is_celsius") else "°F"
    conds = [k.removeprefix("weather_") for k in (
        "weather_sunny", "weather_partly_sunny", "weather_cloudy", "weather_lightrain",
        "weather_rain", "weather_snow", "weather_windy") if w.get(k)]
    hum = f", {w['weather_humidity']}% humidity" if w.get("weather_humidity") else ""
    return f"{w['weather_temperature']}{unit}{hum}" + (f", {', '.join(conds)}" if conds else "")


# ----------------------------------------------------------------------------- statistics / zones

def zone_rows(zones: list[dict[str, Any]] | None, *, time_key: str = "time") -> list[dict[str, Any]]:
    zones = [z for z in zones or [] if isinstance(z, dict)]
    total = sum(_num(z.get(time_key)) or 0 for z in zones)
    rows = []
    for z in zones:
        t = _num(z.get(time_key)) or 0
        lo = z.get("unit_low", z.get("zone_low"))
        hi = z.get("unit_high", z.get("zone_high"))
        unit = z.get("unity_label") or ""
        rows.append(_clean({
            "zone": z.get("name") or z.get("zone_name"),
            "range": f"{_val(lo)}–{_val(hi)} {unit}".strip(),
            "time": hms(t) or "0:00",
            "pct": round(100 * t / total) if total else None,
        }))
    return rows


def statistics(st: dict[str, Any] | None) -> dict[str, Any]:
    if not st:
        return {}
    out: dict[str, Any] = {}
    for key, name in (("zone_heartrate", "heart_rate"), ("zone_pace", "pace"), ("zone_power", "power")):
        if st.get(key):
            out[f"time_in_zones_{name}"] = zone_rows(st[key])
    curve = {p.get("period"): p.get("value") for p in st.get("max_power") or [] if isinstance(p, dict)}
    best = {hms(p): _round(curve[p], 0) for p in POWER_CURVE_PERIODS if curve.get(p)}
    if best:
        out["best_power_w"] = best
    return out


def zones(zone_list: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out = []
    for z in zone_list or []:
        if not isinstance(z, dict):
            continue
        n = 1
        rows = []
        while f"zone_{n}_low" in z or f"zone_{n}_high" in z:
            if z.get(f"zone_{n}_low") is not None or z.get(f"zone_{n}_high") is not None:
                rows.append({"zone": z.get(f"zone_{n}_name") or f"Zone {n}",
                             "low": _round(z.get(f"zone_{n}_low")), "high": _round(z.get(f"zone_{n}_high"))})
            n += 1
        out.append(_clean({
            "sport": z.get("activity_type_name"),
            "type": ZONE_TYPES.get(z.get("zone_type"), z.get("zone_type")),
            "threshold": _round(z.get("zone_threshold")),
            "max": _round(z.get("zone_max")),
            "updated": ymd(z.get("zone_last_modified")),
            "zones": rows,
        }))
    return out


# ----------------------------------------------------------------------------- history

def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def training_summary(days: list[dict[str, Any]] | None, group_by: str = "week") -> dict[str, Any]:
    """WorkoutHistory (по дням и видам спорта) -> итоги за период + разбивка по неделям/дням."""
    def bucket():
        return defaultdict(lambda: {"count": 0, "duration": 0.0, "distance_m": 0.0, "calories": 0.0})

    totals = bucket()
    groups: dict[str, Any] = defaultdict(bucket)
    for day in days or []:
        d = ymd(day.get("workout_date"))
        if not d:
            continue
        key = {"day": d, "month": d[:7]}.get(group_by) or _week_start(date.fromisoformat(d)).isoformat()
        for t in day.get("type_data") or []:
            for b in (totals[t.get("activity_type_name")], groups[key][t.get("activity_type_name")]):
                b["count"] += t.get("count") or 0
                b["duration"] += _num(t.get("total_duration")) or 0
                b["distance_m"] += _num(t.get("total_amount")) or 0
                b["calories"] += _num(t.get("total_calories")) or 0

    def fmt(b):
        return {sport: _clean({
            "count": v["count"],
            "duration": hms(v["duration"]),
            "distance_km": _round(v["distance_m"] / 1000, 1) if v["distance_m"] else None,
            "calories": _round(v["calories"], 0),
        }) for sport, v in sorted(b.items(), key=lambda kv: -kv[1]["duration"])}

    def overall(b):
        return _clean({"count": sum(v["count"] for v in b.values()),
                       "duration": hms(sum(v["duration"] for v in b.values()))})

    out: dict[str, Any] = {"total": overall(totals), "by_sport": fmt(totals)}
    if group_by in ("week", "day", "month"):
        label = {"week": "week_start", "day": "date", "month": "month"}[group_by]
        out[f"by_{group_by}"] = [{label: k, **overall(v), "by_sport": fmt(v)} for k, v in sorted(groups.items())]
    return out


def zone_history(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[dict[str, Any]]:
    out = []
    for z, h in entries:
        if not isinstance(h, dict) or not h.get("zone_data"):
            continue
        unit = h.get("zone_label") or ""
        rows = zone_rows([{**r, "unity_label": unit} for r in h["zone_data"]], time_key="zone_time")
        out.append({
            "sport": z.get("activity_type_name"),
            "type": ZONE_TYPES.get(z.get("zone_type"), z.get("zone_type")),
            "total": hms(_num(h.get("total_time"))),
            "zones": rows,
        })
    return out


def activity_types(types: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [_clean({"name": t.get("name"), "sub_types": [s.get("name") for s in t.get("sub_types") or []]})
            for t in types or [] if isinstance(t, dict)]
