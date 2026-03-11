import asyncio
from types import SimpleNamespace

import cannibal_core.bot as bot
from cannibal_core.bot import _normalize_channel, _parse_channel_list


def test_normalize_channel_accepts_links_and_handles() -> None:
    assert _normalize_channel("@channel_one") == "channel_one"
    assert _normalize_channel("https://t.me/channel_two") == "channel_two"


def test_parse_channel_list_handles_csv_and_newlines() -> None:
    assert _parse_channel_list("@one,\nhttps://t.me/two\nthree") == [
        "one",
        "two",
        "three",
    ]


class _DummyEvent:
    def __init__(self, chat) -> None:
        self.sender_id = 77
        self.message = SimpleNamespace(
            forward=SimpleNamespace(chat=chat) if chat is not None else None
        )
        self.replies: list[str] = []

    async def reply(self, text: str, buttons=None) -> None:
        self.replies.append(text)


def test_capture_forwarded_source_prefers_chat_id(monkeypatch) -> None:
    calls: dict[str, object] = {}

    async def fake_resolve_editorial_source(user_client, raw_ref):
        calls["raw_ref"] = raw_ref
        return {
            "channel_ref": "777",
            "channel_title": "Private source",
            "telegram_id": 777,
            "added_via": "manual",
        }

    async def fake_upsert_editorial_sources(user_id, sources, replace=False):
        calls["user_id"] = user_id
        calls["sources"] = sources
        calls["replace"] = replace

    async def fake_show_menu(event, settings, state, edit=False):
        calls["menu_state"] = list(state.source_channels)

    monkeypatch.setattr(bot, "resolve_editorial_source", fake_resolve_editorial_source)
    monkeypatch.setattr(bot, "upsert_editorial_sources", fake_upsert_editorial_sources)
    monkeypatch.setattr(bot, "_show_menu", fake_show_menu)

    event = _DummyEvent(SimpleNamespace(id=777, username=None, title="Private source"))
    state = bot.BotState(source_channels=["existing"])

    captured = asyncio.run(
        bot._try_capture_forwarded_source(
            event,
            SimpleNamespace(webapp_url=None),
            object(),
            state,
        )
    )

    assert captured is True
    assert calls["raw_ref"] == 777
    assert calls["user_id"] == 77
    assert calls["replace"] is False
    assert state.source_channels == ["existing", "777"]
    assert event.replies == ["Источник сохранён из пересланного поста: 777"]


def test_capture_forwarded_source_returns_false_without_forward() -> None:
    event = _DummyEvent(chat=None)
    state = bot.BotState()

    captured = asyncio.run(
        bot._try_capture_forwarded_source(
            event,
            SimpleNamespace(webapp_url=None),
            object(),
            state,
        )
    )

    assert captured is False
    assert event.replies == []
