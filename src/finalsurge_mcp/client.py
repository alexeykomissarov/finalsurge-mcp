"""Клиент внутреннего JSON API веб-приложения Final Surge (beta.finalsurge.com/api).

Официального API нет: эндпоинты и параметры взяты из бандла веб-приложения
(https://beta.finalsurge.com/dist/build.js). Ответы имеют вид
{"success": bool, "data": ..., "error_description": str}.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://beta.finalsurge.com/api"
USER_AGENT = "Mozilla/5.0 (finalsurge-mcp)"


class FinalSurgeError(RuntimeError):
    """Ошибка API Final Surge."""


class AuthRequired(FinalSurgeError):
    """Нет токена или он истёк — нужен повторный вход."""


@dataclass
class Session:
    token: str
    user_key: str
    obtained_at: float

    @classmethod
    def load(cls, path: Path) -> Session | None:
        try:
            raw = json.loads(path.read_text())
            return cls(token=raw["token"], user_key=raw["user_key"], obtained_at=raw.get("obtained_at", 0))
        except (FileNotFoundError, KeyError, ValueError):
            return None

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(self), f)
        tmp.replace(path)


async def login(email: str, password: str, *, http: httpx.AsyncClient | None = None) -> Session:
    """POST /login -> bearer-токен и user_key."""
    payload = {
        "email": email,
        "password": password,
        "deviceManufacturer": "",
        "deviceModel": "finalsurge-mcp",
        "deviceOperatingSystem": "Linux",
        "deviceUniqueIdentifier": "",
    }
    own = http is None
    http = http or httpx.AsyncClient(base_url=BASE_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    try:
        r = await http.post("/login", json=payload)
        body = _json(r)
    finally:
        if own:
            await http.aclose()
    if not body.get("success") or not isinstance(body.get("data"), dict) or not body["data"].get("token"):
        raise FinalSurgeError(f"Вход не удался: {body.get('error_description') or 'неверный email или пароль'}")
    data = body["data"]
    user_key = data.get("user_key") or data.get("userKey")
    if not user_key:
        raise FinalSurgeError("Ответ на вход без user_key — формат API изменился")
    return Session(token=data["token"], user_key=user_key, obtained_at=time.time())


def _json(r: httpx.Response) -> dict[str, Any]:
    if r.status_code in (401, 403):
        raise AuthRequired(f"Final Surge ответил {r.status_code}")
    r.raise_for_status()
    try:
        body = r.json()
    except ValueError as e:
        raise FinalSurgeError(f"Не-JSON ответ от Final Surge (HTTP {r.status_code})") from e
    if not isinstance(body, dict):
        raise FinalSurgeError("Неожиданный формат ответа Final Surge")
    return body


class FinalSurgeClient:
    """Async-клиент с сессией из файла токена."""

    def __init__(self, token_file: Path, *, transport: httpx.AsyncBaseTransport | None = None):
        self.token_file = token_file
        self._session: Session | None = None
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=60,
            transport=transport,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://beta.finalsurge.com/workoutcalendar",
            },
        )

    @property
    def session(self) -> Session:
        # перечитываем файл, если сессии нет: токен мог появиться после finalsurge-mcp-login
        if self._session is None:
            self._session = Session.load(self.token_file)
        if self._session is None:
            raise AuthRequired("Нет токена Final Surge")
        return self._session

    @property
    def user_key(self) -> str:
        return self.session.user_key

    async def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET /api/<endpoint>, возвращает поле data."""
        session = self.session
        q = {k: _param(v) for k, v in (params or {}).items() if v is not None}
        try:
            r = await self._http.get(f"/{endpoint}", params=q, headers={"Authorization": f"Bearer {session.token}"})
            body = _json(r)
        except AuthRequired:
            self._session = None  # при следующем вызове перечитаем файл
            raise
        if body.get("success") is False:
            msg = (body.get("error_description") or body.get("message")
                   or "Final Surge отклонил запрос (неверный ключ/параметры или нет доступа)")
            if any(w in str(msg).lower() for w in ("token", "auth", "login", "expired")):
                self._session = None
                raise AuthRequired(str(msg))
            raise FinalSurgeError(f"{endpoint}: {msg}")
        return body.get("data")

    async def aclose(self) -> None:
        await self._http.aclose()


def _param(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
