import pytest

from app.api.v1.endpoints import ws


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = value

    async def eval(self, script, nkeys, key):
        return self.store.pop(key, None)


@pytest.mark.anyio
async def test_ws_ticket_redis_issue_and_single_use_consume(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr(ws, "_REDIS_URL", "redis://fake")
    monkeypatch.setattr(ws, "_get_redis", _fake_get_redis)

    ticket = await ws._issue_ws_ticket("user-1")
    first = await ws._consume_ws_ticket(ticket)
    second = await ws._consume_ws_ticket(ticket)

    assert first == "user-1"
    assert second is None


@pytest.mark.anyio
async def test_portal_ws_ticket_redis_issue_and_single_use_consume(monkeypatch):
    fake = _FakeRedis()

    async def _fake_get_redis():
        return fake

    monkeypatch.setattr(ws, "_REDIS_URL", "redis://fake")
    monkeypatch.setattr(ws, "_get_redis", _fake_get_redis)

    ticket = await ws._issue_portal_ws_ticket("client-1")
    first = await ws._consume_portal_ws_ticket(ticket)
    second = await ws._consume_portal_ws_ticket(ticket)

    assert first == "client-1"
    assert second is None
