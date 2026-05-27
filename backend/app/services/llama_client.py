import json
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx

from app.config import get_settings


class LlamaServerUnavailable(Exception):
    pass


class LlamaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str, model: str | None = None, image_data: list[dict] | None = None) -> str:
        payload = self._build_payload(prompt, stream=False, model=model, image_data=image_data)
        if model:
            payload["model"] = model
        async with httpx.AsyncClient(timeout=120) as client:
            response = await self._post_with_retries(client, self._endpoint_for(image_data), payload)
            data = response.json()
        return extract_response_content(data).strip()

    async def generate_stream(
        self,
        prompt: str,
        model: str | None = None,
        image_data: list[dict] | None = None,
        on_retry: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(prompt, stream=True, model=model, image_data=image_data)
        if model:
            payload["model"] = model
        async with httpx.AsyncClient(timeout=None) as client:
            async with self._stream_with_retries(
                client,
                self._endpoint_for(image_data),
                payload,
                on_retry=on_retry,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    token = parse_llama_stream_line(line)
                    if token:
                        yield token

    def _endpoint_for(self, image_data: list[dict] | None = None) -> str:
        if image_data:
            return f"{self.settings.llama_url}/v1/chat/completions"
        return f"{self.settings.llama_url}/completion"

    def _build_payload(self, prompt: str, stream: bool, model: str | None, image_data: list[dict] | None = None) -> dict:
        if image_data:
            content: list[dict] = []
            for image in image_data:
                image_url = image.get("url")
                if image_url:
                    content.append({"type": "image_url", "image_url": {"url": image_url}})
            content.append({"type": "text", "text": prompt})
            payload = {
                "messages": [{"role": "user", "content": content}],
                "temperature": 0.2,
                "max_tokens": 1024,
                "stream": stream,
            }
            if model:
                payload["model"] = model
            return payload

        payload = {
            "prompt": prompt,
            "temperature": 0.2,
            "n_predict": 1024,
            "stream": stream,
        }
        if model:
            payload["model"] = model
        return payload

    async def _post_with_retries(self, client: httpx.AsyncClient, url: str, payload: dict) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, 61):
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError) as exc:
                last_error = exc
                await asyncio.sleep(min(attempt, 5))
        raise LlamaServerUnavailable(
            f"LLM-сервер недоступен по адресу {self.settings.llama_url}. "
            "Проверьте, что контейнер llama запущен, модель полностью загрузилась и LLAMA_HOST/LLAMA_PORT совпадают с .env."
        ) from last_error

    def _stream_with_retries(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict,
        on_retry: Callable[[int, int, str], Awaitable[None]] | None = None,
    ):
        return _RetryingStream(client, url, payload, self.settings.llama_url, on_retry)


class _RetryingStream:
    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        payload: dict,
        llama_url: str,
        on_retry: Callable[[int, int, str], Awaitable[None]] | None = None,
    ) -> None:
        self.client = client
        self.url = url
        self.payload = payload
        self.llama_url = llama_url
        self.on_retry = on_retry
        self.stream_context = None
        self.response = None

    async def __aenter__(self) -> httpx.Response:
        last_error: Exception | None = None
        max_attempts = 60
        for attempt in range(1, max_attempts + 1):
            try:
                self.stream_context = self.client.stream("POST", self.url, json=self.payload)
                self.response = await self.stream_context.__aenter__()
                return self.response
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadError) as exc:
                last_error = exc
                self.stream_context = None
                if self.on_retry is not None:
                    await self.on_retry(attempt, max_attempts, str(exc))
                await asyncio.sleep(min(attempt, 5))
        raise LlamaServerUnavailable(
            f"LLM-сервер недоступен по адресу {self.llama_url}. "
            "Проверьте, что контейнер llama запущен, модель полностью загрузилась и LLAMA_HOST/LLAMA_PORT совпадают с .env."
        ) from last_error

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.stream_context is not None:
            await self.stream_context.__aexit__(exc_type, exc, traceback)


def parse_llama_stream_line(line: str) -> str:
    """Extract visible content from llama-server streaming lines."""
    cleaned = line.strip()
    if cleaned.startswith("data:"):
        cleaned = cleaned.removeprefix("data:").strip()
    if cleaned == "[DONE]":
        return ""
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned
    choices = payload.get("choices")
    if choices:
        delta = choices[0].get("delta", {})
        message = choices[0].get("message", {})
        return str(delta.get("content") or message.get("content") or "")
    return str(payload.get("content") or payload.get("token") or "")


def extract_response_content(payload: dict) -> str:
    choices = payload.get("choices")
    if choices:
        message = choices[0].get("message", {})
        return str(message.get("content") or choices[0].get("text") or "")
    return str(payload.get("content") or "")
