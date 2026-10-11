"""Интерактивный вход в Final Surge: сохраняет только токен сессии, пароль не хранится.

    finalsurge-mcp-login            # спросит email и пароль
    finalsurge-mcp-login --verify   # проверить сохранённый токен
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from .client import AuthRequired, FinalSurgeClient, FinalSurgeError, login


async def _verify(path: Path) -> bool:
    c = FinalSurgeClient(path)
    try:
        profile = await c.get("Profile", {"user_key": c.user_key})
        name = " ".join(filter(None, [profile.get("first_name"), profile.get("last_name")])) if isinstance(profile, dict) else ""
        print(f"Токен рабочий{': ' + name if name else ''}")
        return True
    except AuthRequired as e:
        print(f"Токен недействителен: {e}")
        return False
    finally:
        await c.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true", help="только проверить сохранённый токен")
    args = ap.parse_args()
    path = Path(os.getenv("FINALSURGE_TOKEN_FILE", "/data/token.json"))

    if args.verify:
        sys.exit(0 if asyncio.run(_verify(path)) else 1)

    email = input("Final Surge email: ").strip()
    password = getpass.getpass("Пароль: ")
    try:
        session = asyncio.run(login(email, password))
    except FinalSurgeError as e:
        sys.exit(str(e))
    session.save(path)
    print(f"Вход выполнен, токен сохранён в {path}")
    asyncio.run(_verify(path))


if __name__ == "__main__":
    main()
