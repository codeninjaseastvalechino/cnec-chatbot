"""
LLM Provider abstraction for supporting multiple providers (Claude, Ollama, etc).

Provides a unified interface for different LLM backends with tool calling support.
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
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
            "type": "text" | "tool_use" | "end",
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


class OllamaProvider(LLMProvider):
    """Ollama provider using OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "mistral",
    ):
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI SDK required for Ollama support. Install with: pip install openai>=1.0"
            )

        self.client = OpenAI(api_key="not-needed", base_url=base_url)
        self.model = model
        self.base_url = base_url
        logger.info("Initialized OllamaProvider with model=%s at %s", model, base_url)

    def call(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Call Ollama API with tools via OpenAI-compatible endpoint."""
        try:
            # Build OpenAI-compatible request
            api_messages = [{"role": "system", "content": system_prompt}] + messages

            # Create the API call with tools
            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                tools=[{"type": "function", "function": tool} for tool in tools],
                tool_choice="auto",
            )

            logger.debug("Ollama response: finish_reason=%s", response.choices[0].finish_reason)

            # Parse Ollama response into standardized format
            message = response.choices[0].message

            # Check for tool calls
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_call = message.tool_calls[0]
                return {
                    "type": "tool_use",
                    "content": {
                        "name": tool_call.function.name,
                        "input": json.loads(tool_call.function.arguments),
                        "id": tool_call.id,
                    },
                    "raw": response,
                }

            # Extract text response
            text = message.content or ""

            return {
                "type": "end_turn",
                "content": text,
                "raw": response,
            }

        except Exception as e:
            logger.error("Ollama API call failed: %s", e)
            raise RuntimeError(f"Ollama API error: {e}")


def get_provider(provider_name: str = None) -> LLMProvider:
    """
    Factory function to get the appropriate LLM provider.

    Reads from LLM_PROVIDER environment variable if provider_name not specified.
    Defaults to "claude".

    Supported providers:
    - claude: Claude API via Anthropic SDK (requires ANTHROPIC_API_KEY)
    - ollama: Ollama via OpenAI-compatible API (requires Ollama running locally)
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

    elif provider_name == "ollama":
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        model = os.getenv("OLLAMA_MODEL", "mistral")
        return OllamaProvider(base_url=base_url, model=model)

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider_name}. "
            "Supported: claude, ollama"
        )
