import pytest

from finalsurge_mcp import server


async def test_all_tools_read_only():
    tools = await server.mcp.list_tools()
    assert len(tools) >= 10
    for t in tools:
        assert t.annotations.readOnlyHint is True, t.name
        assert t.annotations.destructiveHint is False, t.name


def test_date_range():
    assert server.date_range("2026-01-01", "2026-01-31") == ("2026-01-01", "2026-01-31")
    for a, b in [("2026-02-01", "2026-01-01"), ("2025-01-01", "2026-06-01"), ("01.01.2026", "2026-01-02")]:
        with pytest.raises(ValueError):
            server.date_range(a, b)


def test_compact_and_truncate():
    assert server.compact({"a": None, "b": "", "c": [], "d": {"e": None}, "f": 0, "g": [None, 1]}) == {"f": 0, "g": [1]}
    out = server.dump({"x": "y" * (server.MAX_OUTPUT_CHARS + 10)})
    assert "обрезано" in out and len(out) < server.MAX_OUTPUT_CHARS + 100
