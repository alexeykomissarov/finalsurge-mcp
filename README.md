# Final Surge MCP

[![CI](https://github.com/alexeykomissarov/finalsurge-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/alexeykomissarov/finalsurge-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

A read-only [Model Context Protocol](https://modelcontextprotocol.io) server for [Final Surge](https://www.finalsurge.com),
the training calendar for runners, cyclists and triathletes. It lets an AI assistant (Claude, etc.) read your
training plan, completed workouts, zones and training volume.

> **Unofficial.** Final Surge has no public API. This server talks to the same internal web API that the
> Final Surge web app uses, so it may break when Final Surge changes it. Not affiliated with Final Surge.

## Features

- **Read-only by design** — every tool is annotated `readOnlyHint`; nothing on your calendar is ever changed.
- **Compact output** — raw API responses are reshaped into small, model-friendly JSON (plan next to actual,
  `h:mm:ss` durations, empty fields dropped), so a month of workouts fits easily in the context window.
- **No stored password** — `finalsurge-mcp-login` exchanges your email and password for a session token once;
  only the token is saved (file mode `0600`).
- **Streamable HTTP** transport (`/mcp`), stateless, plus a `/healthz` endpoint for container health checks.
- Small, non-root Docker image with dependencies pinned by `uv.lock`.

## Tools

| Tool | What it returns |
|---|---|
| `list_workouts(start_date, end_date, completed_only=False)` | Planned and completed workouts between two dates: plan vs actual per activity |
| `get_upcoming_workouts(days=7)` | The plan for the next N days (max 60) plus today's completed workouts |
| `get_workout(workout_key)` | One workout in detail: plan vs actual, laps, power, running dynamics, weather, notes |
| `get_workout_structure(workout_key)` | Structured steps of a planned workout: warm-up, intervals, repeats, pace/HR/power targets |
| `get_workout_comments(workout_key)` | Coach and athlete comments |
| `get_workout_statistics(workout_key)` | Time in HR/pace/power zones and best power from 5 s to 60 min |
| `get_training_summary(start_date, end_date, group_by="week")` | Volume by sport, broken down by `week`, `month`, `day` or `total` (up to 366 days) |
| `get_zones()` | Training zones per sport: heart rate, pace and power, with threshold and max |
| `get_zone_history(start_date, end_date)` | Time spent in each zone over a period |
| `get_calendar_labels(start_date, end_date)` | Races, events and training phases marked on the calendar |
| `get_athlete_notes()` | Athlete notes |
| `get_activity_types()` | Sports and sub-types available in the account |
| `get_profile()` | Athlete profile: name, units, weight, location |

Dates are `YYYY-MM-DD`.

## Quick start (Docker)

```bash
docker build -t finalsurge-mcp https://github.com/alexeykomissarov/finalsurge-mcp.git#v0.1.0
docker volume create finalsurge-data

# one-time login: asks for your Final Surge email and password, stores only the session token
docker run --rm -it -v finalsurge-data:/data --entrypoint finalsurge-mcp-login finalsurge-mcp
docker run --rm -v finalsurge-data:/data --entrypoint finalsurge-mcp-login finalsurge-mcp --verify

# run the server on localhost
docker run -d --name finalsurge-mcp --restart unless-stopped \
  -p 127.0.0.1:8000:8000 -v finalsurge-data:/data --read-only --tmpfs /tmp --cap-drop ALL finalsurge-mcp
```

Connect a client to `http://127.0.0.1:8000/mcp`, for example Claude Code:

```bash
claude mcp add --transport http finalsurge http://127.0.0.1:8000/mcp
```

If the session token expires, the tools answer that a login is required — run `finalsurge-mcp-login` again.

## Running without Docker

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/alexeykomissarov/finalsurge-mcp.git && cd finalsurge-mcp
uv sync --frozen
export FINALSURGE_TOKEN_FILE=$PWD/token.json
uv run finalsurge-mcp-login
uv run finalsurge-mcp          # Streamable HTTP on 0.0.0.0:8000/mcp
```

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FINALSURGE_TOKEN_FILE` | `/data/token.json` | Session token written by `finalsurge-mcp-login` |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | Listen address of the Streamable HTTP server |

## Security

The server itself has **no authentication**: anyone who can reach the port can read your training data.
Keep it on `127.0.0.1` or a private network, or put it behind an authenticating reverse proxy
(for example an OAuth 2.1 proxy such as [mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy)) before
exposing it to the internet. The token file grants access to your Final Surge account — keep it private.

## Development

```bash
uv sync --frozen
uv run pytest -q                 # or: docker build --target test .
```

Test fixtures mirror the shape of real API responses; all values in them are synthetic.
Code comments and server messages are in Russian; tool descriptions (what the model sees) are in English.

## License

[MIT](LICENSE)
