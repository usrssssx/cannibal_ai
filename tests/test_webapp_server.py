import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import cannibal_core.webapp_server as webapp_server


def test_validate_user_returns_401_for_invalid_init_data(monkeypatch) -> None:
    def fake_verify(*args, **kwargs):
        raise ValueError("bad init data")

    monkeypatch.setattr(webapp_server, "_verify_init_data", fake_verify)

    settings = SimpleNamespace(
        bot_token="token",
        webapp_max_age_sec=60,
        bot_allowed_users=[],
    )

    with pytest.raises(HTTPException) as exc:
        webapp_server._validate_user(settings, "init")

    assert exc.value.status_code == 401
    assert exc.value.detail == "bad init data"


def test_validate_user_preserves_forbidden_status(monkeypatch) -> None:
    monkeypatch.setattr(
        webapp_server,
        "_verify_init_data",
        lambda *args, **kwargs: {"user": {"id": 999}},
    )

    settings = SimpleNamespace(
        bot_token="token",
        webapp_max_age_sec=60,
        bot_allowed_users=[111],
    )

    with pytest.raises(HTTPException) as exc:
        webapp_server._validate_user(settings, "init")

    assert exc.value.status_code == 403
    assert exc.value.detail == "User is not allowed"


def test_send_message_raises_on_telegram_api_error() -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"ok": False, "description": "chat not found"}

    class FakeHTTP:
        async def post(self, url: str, json: dict[str, object]):
            return FakeResponse()

    with pytest.raises(RuntimeError, match="chat not found"):
        asyncio.run(webapp_server._send_message(FakeHTTP(), "token", 1, "hello"))
