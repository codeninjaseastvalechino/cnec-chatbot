"""Tests for llm_provider.py — multi-tool extraction logic."""
import pytest
from unittest.mock import MagicMock
from llm_provider import ClaudeProvider


def _make_response(stop_reason, blocks):
    """Build a mock Claude response object."""
    response = MagicMock()
    response.stop_reason = stop_reason
    response.content = blocks
    return response


def _make_tool_block(name, input_data, tool_id):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    block.id = tool_id
    return block


def _make_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    del block.name  # text blocks don't have .name
    return block


class TestClaudeProviderToolExtraction:
    def _provider_with_response(self, response):
        provider = ClaudeProvider.__new__(ClaudeProvider)
        provider.client = MagicMock()
        provider.model = "claude-haiku-4-5"
        provider.client.messages.create.return_value = response
        return provider

    def test_single_tool_call_returned_as_list(self):
        block = _make_tool_block("get_gbs_tours", {"date": "2026-06-05"}, "tool_1")
        response = _make_response("tool_use", [block])
        provider = self._provider_with_response(response)

        result = provider.call([], "", [])
        assert result["type"] == "tool_use"
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        assert result["content"][0]["name"] == "get_gbs_tours"
        assert result["content"][0]["id"] == "tool_1"

    def test_multiple_tool_calls_all_returned(self):
        blocks = [
            _make_tool_block("get_gbs_tours", {"date": "2026-06-12"}, "tool_1"),
            _make_tool_block("get_gbs_tours", {"date": "2026-06-13"}, "tool_2"),
            _make_tool_block("get_gbs_tours", {"date": "2026-06-14"}, "tool_3"),
        ]
        response = _make_response("tool_use", blocks)
        provider = self._provider_with_response(response)

        result = provider.call([], "", [])
        assert result["type"] == "tool_use"
        assert len(result["content"]) == 3
        ids = [t["id"] for t in result["content"]]
        assert ids == ["tool_1", "tool_2", "tool_3"]

    def test_text_blocks_ignored_when_tool_use(self):
        blocks = [
            _make_text_block("Let me check that for you."),
            _make_tool_block("get_gbs_tours", {"date": "2026-06-12"}, "tool_1"),
        ]
        response = _make_response("tool_use", blocks)
        provider = self._provider_with_response(response)

        result = provider.call([], "", [])
        assert result["type"] == "tool_use"
        assert len(result["content"]) == 1
        assert result["content"][0]["name"] == "get_gbs_tours"

    def test_end_turn_returns_text(self):
        blocks = [_make_text_block("Here is your schedule.")]
        response = _make_response("end_turn", blocks)
        provider = self._provider_with_response(response)

        result = provider.call([], "", [])
        assert result["type"] == "end_turn"
        assert result["content"] == "Here is your schedule."

    def test_raw_response_included(self):
        block = _make_tool_block("get_gbs_tours", {}, "tool_1")
        response = _make_response("tool_use", [block])
        provider = self._provider_with_response(response)

        result = provider.call([], "", [])
        assert result["raw"] is response
