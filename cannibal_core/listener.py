from __future__ import annotations

from loguru import logger
from telethon import TelegramClient, events

from .config import Settings
from .processor import Processor


class Listener:
    def __init__(self, settings: Settings, processor: Processor) -> None:
        self._settings = settings
        self._processor = processor
        self._client = TelegramClient(
            settings.telethon_session,
            settings.telethon_api_id,
            settings.telethon_api_hash,
        )

    async def start(self) -> None:
        if not self._settings.target_channels:
            logger.warning("TARGET_CHANNELS is empty. Listener will not receive messages.")
        self._client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=self._settings.target_channels),
        )
        await self._client.start()
        logger.info("Listener started")
        await self._client.run_until_disconnected()

    def _is_ad(self, text: str) -> bool:
        lowered = text.lower()
        return any(word in lowered for word in self._settings.ad_stop_words)

    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        message = event.message
        text = message.message or ""
        if not text.strip():
            return

        if self._is_ad(text):
            logger.info("Ad filtered")
            return

        chat = event.chat
        channel_id = event.chat_id
        channel_name = getattr(chat, "username", None) or getattr(chat, "title", None)
        channel_name = channel_name or str(channel_id or "unknown")

        await self._processor.enqueue(
            {
                "channel_name": channel_name,
                "channel_id": channel_id,
                "message_id": message.id,
                "text": text,
            }
        )
