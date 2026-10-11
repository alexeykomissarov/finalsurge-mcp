import json
import os

import httpx
import pytest

from finalsurge_mcp.client import AuthRequired, FinalSurgeClient, FinalSurgeError, Session, login


def transport(handler):
    return httpx.MockTransport(handler)


async def test_login_ok():
    def h(req):
        assert req.url.path == "/api/login"
        body = json.loads(req.content)
        assert body["email"] == "a@b.c" and body["password"] == "pw"
        return httpx.Response(200, json={"success": True, "data": {"token": "T", "user_key": "U"}})

    async with httpx.AsyncClient(base_url="https://beta.finalsurge.com/api", transport=transport(h)) as http:
        s = await login("a@b.c", "pw", http=http)
    assert (s.token, s.user_key) == ("T", "U")


async def test_login_bad_password():
    h = lambda req: httpx.Response(200, json={"success": False, "error_description": "Invalid login"})
    async with httpx.AsyncClient(base_url="https://beta.finalsurge.com/api", transport=transport(h)) as http:
        with pytest.raises(FinalSurgeError, match="Invalid login"):
            await login("a", "b", http=http)


def test_session_file_is_private(tmp_path):
    p = tmp_path / "d" / "token.json"
    Session("T", "U", 1.0).save(p)
    assert oct(os.stat(p).st_mode & 0o777) == "0o600"
    assert Session.load(p) == Session("T", "U", 1.0)


async def test_get_sends_bearer_and_bool_params(tmp_path):
    p = tmp_path / "token.json"
    Session("T", "U", 1.0).save(p)

    def h(req):
        assert req.headers["Authorization"] == "Bearer T"
        assert req.url.params["completedonly"] == "false"
        assert "skip" not in req.url.params
        return httpx.Response(200, json={"success": True, "data": [1]})

    c = FinalSurgeClient(p, transport=transport(h))
    assert await c.get("WorkoutList", {"completedonly": False, "skip": None}) == [1]


async def test_no_token(tmp_path):
    c = FinalSurgeClient(tmp_path / "missing.json", transport=transport(lambda r: httpx.Response(200)))
    with pytest.raises(AuthRequired):
        await c.get("Profile")


async def test_401_and_token_error_raise_auth(tmp_path):
    p = tmp_path / "token.json"
    Session("T", "U", 1.0).save(p)
    c = FinalSurgeClient(p, transport=transport(lambda r: httpx.Response(401)))
    with pytest.raises(AuthRequired):
        await c.get("Profile")
    c = FinalSurgeClient(p, transport=transport(
        lambda r: httpx.Response(200, json={"success": False, "error_description": "Token expired"})))
    with pytest.raises(AuthRequired):
        await c.get("Profile")


async def test_api_error(tmp_path):
    p = tmp_path / "token.json"
    Session("T", "U", 1.0).save(p)
    c = FinalSurgeClient(p, transport=transport(
        lambda r: httpx.Response(200, json={"success": False, "error_description": "Bad key"})))
    with pytest.raises(FinalSurgeError, match="Bad key"):
        await c.get("WorkoutPlannedCompleted")
