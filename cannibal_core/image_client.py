from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger

from .config import Settings


_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9']+")
_URL_RE = re.compile(r"https?://\\S+")


@dataclass(slots=True)
class ImageResult:
    url: str | None
    local_path: str | None
    source: str | None
    query: str | None


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "channel"


def _strip_leading_label(text: str) -> str:
    first_line = text.strip().splitlines()[0].strip()
    colon_idx = first_line.find(":")
    if 0 < colon_idx <= 15:
        label = first_line[:colon_idx].strip()
        if label and len(label.split()) <= 3:
            return text.replace(first_line[: colon_idx + 1], "", 1).lstrip()
    return text


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?…])\\s+", text.strip(), maxsplit=1)
    return parts[0] if parts else text.strip()


class ImageClient:
    def __init__(self, settings: Settings) -> None:
        self._enabled = settings.image_enabled
        self._search_provider = settings.image_search_provider.lower().strip()
        self._generation_provider = settings.image_generation_provider.lower().strip()
        self._safe_only = settings.image_safe_only
        self._download = settings.image_download
        self._output_dir = Path(settings.image_output_dir)
        self._query_max_words = settings.image_query_max_words
        self._prompt_style = settings.image_prompt_style

        self._pexels_key = settings.pexels_api_key
        self._pexels_per_page = settings.pexels_per_page
        self._pexels_orientation = settings.pexels_orientation

        self._replicate_token = settings.replicate_api_token
        self._replicate_version = settings.replicate_model_version
        self._replicate_poll_interval = settings.replicate_poll_interval
        self._replicate_timeout = settings.replicate_timeout
        self._replicate_negative_prompt = settings.replicate_negative_prompt

        self._http = httpx.AsyncClient(timeout=httpx.Timeout(60.0))

    def _build_query(self, text: str) -> str:
        cleaned = _URL_RE.sub("", text or "")
        cleaned = cleaned.replace("#", " ").replace("@", " ")
        cleaned = _strip_leading_label(cleaned)
        cleaned = _first_sentence(cleaned)
        words = _WORD_RE.findall(cleaned)
        if not words:
            return ""
        return " ".join(words[: self._query_max_words])

    def _build_prompt(self, query: str) -> str:
        base = self._prompt_style.strip()
        if not base.endswith("."):
            base += "."
        if not query:
            return f"{base} Newsroom illustration, neutral background."
        return f"{base} Subject: {query}."

    async def get_image(
        self,
        text: str,
        channel_name: str,
        message_id: int,
    ) -> ImageResult | None:
        if not self._enabled:
            return None

        query = self._build_query(text)
        logger.info("Image query: {}", query or "<empty>")

        url = None
        source = None

        if self._search_provider == "pexels":
            url = await self._search_pexels(query)
            if url:
                source = "pexels"

        if not url and self._generation_provider == "replicate":
            prompt = self._build_prompt(query)
            url = await self._generate_replicate(prompt)
            if url:
                source = "replicate"

        if not url:
            return ImageResult(url=None, local_path=None, source=None, query=query)

        local_path = None
        if self._download:
            local_path = await self._download_image(url, channel_name, message_id)

        return ImageResult(url=url, local_path=local_path, source=source, query=query)

    async def _search_pexels(self, query: str) -> str | None:
        if not query:
            return None
        if not self._pexels_key:
            return None
        headers = {"Authorization": self._pexels_key}
        params = {
            "query": query,
            "per_page": self._pexels_per_page,
        }
        if self._pexels_orientation:
            params["orientation"] = self._pexels_orientation
        if self._safe_only:
            params["safe_search"] = "true"

        try:
            response = await self._http.get(
                "https://api.pexels.com/v1/search",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            logger.exception("Pexels search failed")
            return None

        photos = data.get("photos") or []
        if not photos:
            return None
        src = (photos[0] or {}).get("src") or {}
        return (
            src.get("large2x")
            or src.get("large")
            or src.get("original")
            or src.get("medium")
        )

    async def _generate_replicate(self, prompt: str) -> str | None:
        if not self._replicate_token or not self._replicate_version:
            return None
        headers = {"Authorization": f"Token {self._replicate_token}"}
        payload: dict[str, Any] = {
            "version": self._replicate_version,
            "input": {"prompt": prompt},
        }
        if self._safe_only and self._replicate_negative_prompt:
            payload["input"]["negative_prompt"] = self._replicate_negative_prompt

        try:
            create_resp = await self._http.post(
                "https://api.replicate.com/v1/predictions",
                headers=headers,
                json=payload,
            )
            create_resp.raise_for_status()
            data = create_resp.json()
        except Exception:
            logger.exception("Replicate create prediction failed")
            return None

        prediction_id = data.get("id")
        if not prediction_id:
            return None

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._replicate_timeout
        while loop.time() < deadline:
            await asyncio.sleep(self._replicate_poll_interval)
            try:
                poll_resp = await self._http.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers,
                )
                poll_resp.raise_for_status()
                status_data = poll_resp.json()
            except Exception:
                logger.exception("Replicate poll failed")
                return None

            status = status_data.get("status")
            if status == "succeeded":
                return self._extract_replicate_output(status_data.get("output"))
            if status in {"failed", "canceled"}:
                logger.warning("Replicate generation {}.", status)
                return None

        logger.warning("Replicate generation timed out")
        return None

    @staticmethod
    def _extract_replicate_output(output: Any) -> str | None:
        if isinstance(output, list) and output:
            return output[0]
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return output.get("url")
        return None

    async def _download_image(
        self,
        url: str,
        channel_name: str,
        message_id: int,
    ) -> str | None:
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix or ".jpg"
        channel_slug = _safe_name(channel_name)
        out_dir = self._output_dir / channel_slug
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{message_id}{ext}"
        out_path = out_dir / filename

        try:
            resp = await self._http.get(url)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
        except Exception:
            logger.exception("Failed to download image")
            return None

        return str(out_path)
