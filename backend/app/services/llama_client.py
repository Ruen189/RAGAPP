import json
from collections.abc import AsyncIterator

import httpx

from app.config import get_settings


class LlamaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, prompt: str, model: str | None = None) -> str:
        payload = {
            "prompt": prompt,
            "temperature": 0.2,
            "n_predict": 1024,
            "stream": False,
        }
        if model:
            payload["model"] = model
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(f"{self.settings.llama_url}/completion", json=payload)
            response.raise_for_status()
            data = response.json()
        return data.get("content", "").strip()

    async def generate_stream(self, prompt: str, model: str | None = None) -> AsyncIterator[str]:
        payload = {
            "prompt": prompt,
            "temperature": 0.2,
            "n_predict": 1024,
            "stream": True,
        }
        if model:
            payload["model"] = model
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{self.settings.llama_url}/completion", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    token = parse_llama_stream_line(line)
                    if token:
                        yield token


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
    return str(payload.get("content") or payload.get("token") or "")
