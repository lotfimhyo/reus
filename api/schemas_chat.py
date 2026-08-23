# Project: Reus
# Founder: Lotfi Mahiddine
# Organization: Reulink
# Contact: Contact@reulink.app

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    system: Optional[str] = Field(default=None, max_length=2000)


class ChatResponse(BaseModel):
    response: str
    provider: Optional[str] = None
    model_used: Optional[str] = None
    fallback_from: Optional[str] = None
    sources: list[str] = Field(default_factory=list)

    @classmethod
    def from_executor_result(cls, result: Any) -> "ChatResponse":
        """Executors return different shapes. This normalization exposes rich
        provider, model, and fallback fields only when they are actually
        present in the result and does not invent them for other modes."""
        if isinstance(result, dict) and "response" in result:
            return cls(
                response=str(result["response"]),
                provider=result.get("provider"),
                model_used=result.get("model_used"),
                fallback_from=result.get("fallback_from"),
                sources=[str(source) for source in result.get("sources", []) if isinstance(source, (str, int, float))],
            )
        return cls(response=str(result))
