"""MCP-сервер Final Surge: только чтение (календарь тренировок, детали, зоны, сводки).

Переменные окружения:
  FINALSURGE_TOKEN_FILE  файл сессии (по умолчанию /data/token.json), создаётся finalsurge-mcp-login
  MCP_HOST / MCP_PORT    адрес Streamable HTTP (по умолчанию 0.0.0.0:8000, путь /mcp)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import shape
from .client import AuthRequired, FinalSurgeClient, FinalSurgeError

MAX_RANGE_DAYS = 366
LIST_RANGE_DAYS = 120
MAX_OUTPUT_CHARS = 60_000
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)

mcp = FastMCP(
    "Final Surge",
    instructions=(
        "Read-only access to the user's Final Surge training calendar. Planned workouts carry the plan "
        "(name, description such as 'Z1-Z2', planned duration/distance); completed ones are synced from the watch "
        "and keep the planned target next to the actual result. "
        "Use list_workouts / get_upcoming_workouts for dates, get_training_summary for volume over weeks/months, "
        "get_workout(workout_key) for laps and running dynamics, get_workout_statistics for time in zones. "
        "Dates are YYYY-MM-DD; durations are h:mm:ss."
    ),
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8000")),
    stateless_http=True,
    json_response=True,
)

client = FinalSurgeClient(Path(os.getenv("FINALSURGE_TOKEN_FILE", "/data/token.json")))


# ----------------------------------------------------------------------------- helpers

def compact(obj: Any) -> Any:
    """Убирает пустые значения (None, "", [], {}), чтобы не тратить контекст модели."""
    if isinstance(obj, dict):
        out = {k: compact(v) for k, v in obj.items()}
        return {k: v for k, v in out.items() if v not in (None, "", [], {})}
    if isinstance(obj, list):
        return [compact(v) for v in obj if v not in (None, "", [], {})]
    return obj


def dump(obj: Any) -> str:
    text = json.dumps(compact(obj), ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + f"... [обрезано: ответ {len(text)} символов, сузьте запрос]"
    return text


def date_range(start_date: str, end_date: str, max_days: int = MAX_RANGE_DAYS) -> tuple[str, str]:
    try:
        s, e = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Даты в формате YYYY-MM-DD") from exc
    if e < s:
        raise ValueError("end_date раньше start_date")
    if (e - s).days > max_days:
        raise ValueError(f"Диапазон не больше {max_days} дней")
    return s.isoformat(), e.isoformat()


async def call(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return await client.get(endpoint, params)
    except AuthRequired as e:
        raise RuntimeError(
            f"Final Surge: требуется вход ({e}). Администратору: заново выполнить `finalsurge-mcp-login` в контейнере сервера."
        ) from e
    except FinalSurgeError as e:
        raise RuntimeError(str(e)) from e


# ----------------------------------------------------------------------------- tools

@mcp.tool(annotations=READ_ONLY)
async def get_profile() -> str:
    """Profile of the Final Surge athlete: name, gender, birthday, weight, location, units."""
    p = await call("Profile", {"user_key": client.user_key}) or {}
    return dump({k: v for k, v in p.items() if not k.endswith("_key")})


@mcp.tool(annotations=READ_ONLY)
async def list_workouts(start_date: str, end_date: str, completed_only: bool = False) -> str:
    """Workouts on the Final Surge calendar between two dates (inclusive): planned and completed.

    Each workout: date, status (Planned/Completed/...), name/description (the plan), and per activity
    the planned target next to the actual result (duration, distance, pace, HR, power, cadence).
    Range up to 120 days; for longer periods use get_training_summary.
    Use workout_key with get_workout for laps and running dynamics.
    """
    s, e = date_range(start_date, end_date, max_days=LIST_RANGE_DAYS)
    data = await call(
        "WorkoutList",
        {"scope": "USER", "scopekey": client.user_key, "startdate": s, "enddate": e,
         "ishistory": False, "completedonly": completed_only},
    )
    return dump([shape.workout(w) for w in data or []])


@mcp.tool(annotations=READ_ONLY)
async def get_upcoming_workouts(days: int = 7) -> str:
    """Workouts from today for the next N days (default 7, max 60): the plan, plus today's already completed ones."""
    days = max(1, min(days, 60))
    today = date.today()
    data = await call(
        "WorkoutList",
        {"scope": "USER", "scopekey": client.user_key, "startdate": today.isoformat(),
         "enddate": (today + timedelta(days=days)).isoformat(), "ishistory": False, "completedonly": False},
    )
    return dump([shape.workout(w) for w in data or []])


@mcp.tool(annotations=READ_ONLY)
async def get_workout(workout_key: str) -> str:
    """One workout in detail: plan vs actual, laps, power details, running dynamics, weather, notes."""
    w = await call("WorkoutPlannedCompleted", {"key": workout_key, "scope": "USER", "scopekey": client.user_key})
    if not w:
        return "Тренировка не найдена"
    return dump(shape.workout(w, detailed=True))


@mcp.tool(annotations=READ_ONLY)
async def get_workout_structure(workout_key: str) -> str:
    """Structured steps of a planned workout (warm-up, intervals, targets by pace/HR/power, repeats).

    Only for workouts built in the Final Surge workout builder (list_workouts shows structured=true).
    """
    data = await call(
        "WorkoutBuilderGet",
        {"scope": "USER", "scopekey": client.user_key, "workout_key": workout_key, "array": True, "newobject": True},
    )
    if not data:
        return "У этой тренировки нет структурированных шагов — план задан только названием и описанием."
    return dump(data)


@mcp.tool(annotations=READ_ONLY)
async def get_workout_comments(workout_key: str) -> str:
    """Comments on a workout (coach and athlete)."""
    data = await call("WorkoutComment", {"scope": "USER", "scopeKey": client.user_key, "key": workout_key})
    if not data:
        return "Комментариев нет"
    return dump(data)


@mcp.tool(annotations=READ_ONLY)
async def get_workout_statistics(workout_key: str) -> str:
    """Analysis of a completed workout's file: time in HR/pace/power zones and best power for 5s…60min."""
    data = await call(
        "WorkoutStatistics",
        {"key": workout_key, "scope": "USER", "scopekey": client.user_key, "includejson": False, "zonesonly": False},
    )
    out = shape.statistics(data)
    return dump(out) if out else "Статистики нет (тренировка без файла с данными)"


@mcp.tool(annotations=READ_ONLY)
async def get_training_summary(start_date: str, end_date: str, group_by: str = "week") -> str:
    """Training volume for a period: totals by sport (count, duration, distance, calories),
    plus a breakdown by group_by: "week" (default, weeks start on Monday), "month", "day" or "total" (no breakdown).
    Up to 366 days.
    """
    if group_by not in ("week", "month", "day", "total"):
        raise ValueError('group_by: "week", "month", "day" или "total"')
    s, e = date_range(start_date, end_date)
    data = await call("WorkoutHistory", {"userkey": client.user_key, "startdate": s, "enddate": e})
    return dump({"period": f"{s}..{e}", **shape.training_summary(data, group_by)})


@mcp.tool(annotations=READ_ONLY)
async def get_zones() -> str:
    """Athlete's training zones per sport (heart rate / pace / power): threshold, max and zone ranges."""
    return dump(shape.zones(await call("ZoneList", {"user_key": client.user_key})))


@mcp.tool(annotations=READ_ONLY)
async def get_zone_history(start_date: str, end_date: str) -> str:
    """Time spent in each training zone over a period, per sport and zone type (with % of total)."""
    s, e = date_range(start_date, end_date)
    entries = []
    for z in await call("ZoneList", {"user_key": client.user_key}) or []:
        if isinstance(z, dict) and z.get("zone_key"):
            h = await call("ZoneHistory", {"userkey": client.user_key, "zonekey": z["zone_key"], "startdate": s, "enddate": e})
            entries.append((z, h))
    out = shape.zone_history(entries)
    return dump(out) if out else "За период нет данных по зонам"


@mcp.tool(annotations=READ_ONLY)
async def get_calendar_labels(start_date: str, end_date: str) -> str:
    """Calendar labels between dates — races, events, training phases marked on the calendar."""
    s, e = date_range(start_date, end_date)
    data = await call("CalendarLabelList", {"scope": "USER", "scopekey": client.user_key, "startdate": s, "enddate": e})
    return dump(data) if data else "Меток в календаре за период нет"


@mcp.tool(annotations=READ_ONLY)
async def get_athlete_notes() -> str:
    """Athlete notes (subject, text, date)."""
    data = await call("AthleteNoteList", {"user_key": client.user_key})
    return dump(data) if data else "Заметок нет"


@mcp.tool(annotations=READ_ONLY)
async def get_activity_types() -> str:
    """Sports available in the account and their sub-types (e.g. Run: Long Run, Tempo, Intervals)."""
    return dump(shape.activity_types(await call("ActivityTypeList", {"user_key": client.user_key})))


# ----------------------------------------------------------------------------- http

@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    # жив процесс и есть токен; сам Final Surge не дёргаем, чтобы не ловить rate limit
    try:
        client.session
        return JSONResponse({"status": "ok", "auth": True})
    except AuthRequired:
        return JSONResponse({"status": "ok", "auth": False})


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
