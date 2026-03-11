from __future__ import annotations

from typing import Any
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
        self._embedding_max_chars = settings.embedding_max_chars
        self._rewrite_mode = settings.rewrite_mode
        self._rewrite_temperature = settings.rewrite_temperature
        self._http: httpx.AsyncClient | None = None
        self._client: AsyncOpenAI | None = None
        if self._provider == "openai":
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
            self._model = settings.openai_model
            self._embedding_model = settings.openai_embedding_model
        elif self._provider == "llama_cpp":
            base_url = settings.llama_cpp_base_url.rstrip("/")
            openai_base = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
            self._client = AsyncOpenAI(
                api_key=settings.llama_cpp_api_key or "local",
                base_url=openai_base,
            )
            self._http = httpx.AsyncClient(
                base_url=base_url,
                timeout=httpx.Timeout(60.0),
            )
            self._model = settings.llama_cpp_model
            self._embedding_model = (
                settings.llama_cpp_embedding_model or settings.llama_cpp_model
            )
        else:
            self._client = None
            self._http = httpx.AsyncClient(
                base_url=settings.ollama_base_url,
                timeout=httpx.Timeout(60.0),
            )
            self._model = settings.ollama_model
            self._embedding_model = settings.ollama_embedding_model
            self._ollama_options = settings.ollama_chat_options
            if self._rewrite_temperature is not None:
                self._ollama_options = {
                    **self._ollama_options,
                    "temperature": self._rewrite_temperature,
                }

    async def health_check(self) -> None:
        if self._provider == "openai":
            return
        if self._provider == "llama_cpp":
            if not self._http:
                raise RuntimeError("llama.cpp client is not initialized")
            try:
                response = await self._http.get("/v1/models", timeout=5.0)
                response.raise_for_status()
            except Exception as exc:
                logger.error("llama.cpp health check failed: {}", exc)
                raise
            return
        if not self._http:
            raise RuntimeError("Ollama client is not initialized")
        try:
            response = await self._http.get("/api/tags", timeout=5.0)
            response.raise_for_status()
        except Exception as exc:
            logger.error("Ollama health check failed: {}", exc)
            raise

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((OpenAIError, httpx.HTTPError)),
        before_sleep=_log_retry,
    )
    async def embed(self, text: str) -> list[float]:
        logger.debug("Requesting embedding")
        if self._embedding_max_chars and len(text) > self._embedding_max_chars:
            text = text[: self._embedding_max_chars]
        if self._provider == "openai":
            if not self._client:
                raise RuntimeError("OpenAI client is not initialized")
            response = await self._client.embeddings.create(
                model=self._embedding_model,
                input=text,
            )
            return response.data[0].embedding
        if self._provider == "llama_cpp":
            if not self._http:
                raise RuntimeError("llama.cpp client is not initialized")
            try:
                response = await self._http.post(
                    "/embedding",
                    json={"content": text},
                )
                response.raise_for_status()
                data = response.json()
                if "embedding" in data:
                    return data["embedding"]
            except httpx.HTTPStatusError:
                pass
            response = await self._http.post(
                "/v1/embeddings",
                json={"model": self._embedding_model, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

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
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if self._provider in {"openai", "llama_cpp"}:
            if not self._client:
                raise RuntimeError("OpenAI-compatible client is not initialized")
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            return content.strip()

        if not self._http:
            raise RuntimeError("Ollama client is not initialized")
        options = dict(self._ollama_options)
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        response = await self._http.post(
            "/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": options,
            },
        )
        response.raise_for_status()
        data = response.json()
        content = (data.get("message") or {}).get("content") or ""
        return content.strip()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((OpenAIError, httpx.HTTPError)),
        before_sleep=_log_retry,
    )
    async def rewrite(
        self,
        text: str,
        style_examples: Iterable[str],
        style_profile: str | None = None,
        voice_hint: str | None = None,
    ) -> str:
        style_block = "\n\n".join(
            f"Example {idx + 1}:\n{example}" for idx, example in enumerate(style_examples)
        )
        system_prompt = (
            "You are a senior editor. Rewrite the source post to preserve facts, "
            "keep the author's tone, and avoid adding new information."
        )
        if self._rewrite_mode == "aggressive":
            system_prompt = (
                "You are a senior editor. Rewrite the source post with maximum "
                "paraphrasing while preserving all facts and the author's tone. "
                "Change sentence order and structure, avoid copying phrases longer "
                "than 3 words except names, tickers, numbers, and official titles. "
                "Do not add new information, do not insert dates, headings, or "
                "signatures, and return only the rewritten post."
            )
        prompt_parts = []
        if style_profile:
            prompt_parts.append("Style profile:\n" + style_profile)
        if voice_hint == "first_person":
            prompt_parts.append("Narrative voice: first person. Keep it.")
        elif voice_hint == "third_person":
            prompt_parts.append("Narrative voice: third person. Keep it.")
        prompt_parts.append("Style examples:\n" + style_block)
        prompt_parts.append("Source post:\n" + text)
        prompt_parts.append(
            "Constraints:\n"
            "- Preserve meaning and sentiment.\n"
            "- Do not add or remove facts.\n"
            "- Keep paragraph breaks and overall length similar.\n"
            "- Output only the rewritten post."
        )
        prompt_parts.append(
            "Rewrite the source post in the same tone and language as the examples."
        )
        user_prompt = "\n\n".join(prompt_parts)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return await self.chat(messages, temperature=self._rewrite_temperature)

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        client = self._client
        if client is not None and hasattr(client, "close"):
            await client.close()
