from __future__ import annotations

from typing import Iterable

import httpx
from loguru import logger
from openai import AsyncOpenAI
from openai import OpenAIError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings


def _log_retry(retry_state) -> None:
    sleep = getattr(retry_state.next_action, "sleep", None)
    if sleep is None:
        logger.warning("OpenAI call failed. Retrying.")
    else:
        logger.warning("OpenAI call failed. Retrying in {}s", round(sleep, 2))


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._provider = settings.llm_provider.lower().strip()
        if self._provider == "openai":
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._http: httpx.AsyncClient | None = None
            self._model = settings.openai_model
            self._embedding_model = settings.openai_embedding_model
        else:
            self._client = None
            self._http = httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=httpx.Timeout(60.0),
            )
            self._model = settings.ollama_model
            self._embedding_model = settings.ollama_embedding_model

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((OpenAIError, httpx.HTTPError)),
        before_sleep=_log_retry,
    )
    async def embed(self, text: str) -> list[float]:
        logger.debug("Requesting embedding")
        if self._provider == "openai":
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding

        if not self._http:
            raise RuntimeError("Ollama client is not initialized")
        response = await self._http.post(
            "/api/embeddings",
            json={"model": self._embedding_model, "prompt": text},
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((OpenAIError, httpx.HTTPError)),
        before_sleep=_log_retry,
    )
    async def rewrite(self, text: str, style_examples: Iterable[str]) -> str:
        style_block = "\n\n".join(
            f"Example {idx + 1}:\n{example}" for idx, example in enumerate(style_examples)
        )
        system_prompt = (
            "You are a senior news editor. Rewrite the source post to preserve facts, "
            "keep the admin tone, and avoid adding new information. Be concise and "
            "informative."
        )
        user_prompt = (
            "Style examples:\n"
            f"{style_block}\n\n"
            "Source post:\n"
            f"{text}\n\n"
            "Rewrite the source post in the same tone and language as the examples."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if self._provider == "openai":
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.4,
            )
            content = response.choices[0].message.content or ""
            return content.strip()

        if not self._http:
            raise RuntimeError("Ollama client is not initialized")
        response = await self._http.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.4},
            },
        )
        response.raise_for_status()
        data = response.json()
        content = (data.get("message") or {}).get("content") or ""
        return content.strip()
