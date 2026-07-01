"""
LLM Provider abstraction for supporting multiple LLM backends.

Provides a unified interface with tool-calling support. ClaudeProvider is the
only implementation today; the LLMProvider ABC keeps the door open for adding
others (e.g. a future Gemini provider) without touching ChatbotEngine.
"""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List
from core.logger import get_logger

logger = get_logger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def call(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Call the LLM with messages, system prompt, and tools.

        Returns standardized response:
        {
            "type": "tool_use" | "end_turn",
            "content": <varies by type>,
            "raw": <original response for debugging>
        }
        """
        pass


class ClaudeProvider(LLMProvider):
    """Claude API provider using Anthropic SDK."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)
        self.model = model
        logger.info("Initialized ClaudeProvider with model=%s", model)

    def call(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Call Claude API with tools."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )

            logger.debug("Claude response: stop_reason=%s", response.stop_reason)

            # Parse Claude response into standardized format
            if response.stop_reason == "tool_use":
                # Collect ALL tool_use blocks — Claude may request several at once
                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

                if tool_use_blocks:
                    return {
                        "type": "tool_use",
                        "content": [
                            {
                                "name": b.name,
                                "input": b.input,
                                "id": b.id,
                            }
                            for b in tool_use_blocks
                        ],
                        "raw": response,
                    }

            # Extract text response
            text_blocks = [block.text for block in response.content if hasattr(block, "text")]
            text = "\n".join(text_blocks) if text_blocks else ""

            return {
                "type": "end_turn",
                "content": text,
                "raw": response,
            }

        except Exception as e:
            logger.error("Claude API call failed: %s", e)
            raise RuntimeError(f"Claude API error: {e}")


def get_provider(provider_name: str = None) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider.

    Reads from LLM_PROVIDER environment variable if provider_name not specified.
    Defaults to "claude".

    Supported providers:
    - claude: Claude API via Anthropic SDK (requires ANTHROPIC_API_KEY)
    """
    if provider_name is None:
        provider_name = os.getenv("LLM_PROVIDER", "claude").lower()

    logger.info("Loading LLM provider: %s", provider_name)

    if provider_name == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not found in environment. "
                "Set it in .env or as environment variable."
            )
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
        return ClaudeProvider(api_key=api_key, model=model)

    raise ValueError(f"Unknown LLM provider: {provider_name}. Supported: claude")
