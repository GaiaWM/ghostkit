"""BYOK inference engine — any OpenAI-compatible endpoint.

The key lives in this object, on your machine. ghostkit sends it only to the
``base_url`` you configured — never to the Ghost Gateway.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass
class Engine:
    base_url: str
    api_key: str
    model: str
    timeout: float = 180.0

    def chat(self, messages: list[dict], temperature: float = 0.6,
             max_tokens: int | None = None) -> tuple[str, dict]:
        """One chat completion. Returns (text, usage)."""
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        r = httpx.post(self.base_url.rstrip("/") + "/chat/completions", json=body,
                       headers={"Authorization": f"Bearer {self.api_key}"},
                       timeout=self.timeout)
        r.raise_for_status()
        out = r.json()
        text = ((out.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return text.strip(), out.get("usage") or {}

    def __repr__(self) -> str:  # never print the key
        return f"Engine(model={self.model!r}, base_url={self.base_url!r})"
