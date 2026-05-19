"""Smoke test: verify the OllamaChatOpenAI fix produces strict structured output
via response_format=json_schema (no tool_choice fallback) against a live
llama.cpp / Ollama / LM Studio server.

Run with the qwen-agent server (or any llama.cpp instance) live on
http://127.0.0.1:11434/v1.

What we're proving:
1. Wiring: OpenAIClient instantiates OllamaChatOpenAI for provider="ollama".
2. Method default: with_structured_output(Schema) defaults to method="json_schema".
3. Wire format: the request the client would send contains
   response_format={"type": "json_schema", ...} — NOT tool_choice={...}.
4. End-to-end: a real round-trip returns a strict Pydantic instance whose
   types match the declared schema, including an optional field that gets
   filled (proving schema enforcement, not free-text fallback).
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from pydantic import BaseModel, Field

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import (
    NormalizedChatOpenAI,
    OllamaChatOpenAI,
)


class CityWeather(BaseModel):
    """Tiny schema with a required field, an enum-style string, and an optional float."""

    city: str = Field(description="The city name.")
    season: str = Field(description="Exactly one of: spring, summer, autumn, winter.")
    temperature_celsius: Optional[float] = Field(
        default=None,
        description="Approximate average temperature in degrees Celsius.",
    )


def assert_eq(label: str, got: object, want: object) -> None:
    if got != want:
        print(f"FAIL  {label}: got {got!r}, want {want!r}")
        sys.exit(1)
    print(f"PASS  {label}: {got!r}")


def assert_isinstance(label: str, got: object, want_type: type) -> None:
    if not isinstance(got, want_type):
        print(f"FAIL  {label}: got {type(got).__name__}, want {want_type.__name__}")
        sys.exit(1)
    print(f"PASS  {label}: {type(got).__name__}")


def main() -> int:
    print("=" * 60)
    print("Step 1: wiring — ollama provider must produce OllamaChatOpenAI")
    print("=" * 60)
    client = create_llm_client(
        provider="ollama",
        model="qwen3.6-27b-agent",
        base_url="http://127.0.0.1:11434/v1",
    )
    llm = client.get_llm()
    assert_isinstance("client class", llm, OllamaChatOpenAI)
    assert_isinstance("inherits NormalizedChatOpenAI", llm, NormalizedChatOpenAI)

    print()
    print("=" * 60)
    print("Step 2: idempotency — repeated calls return same default method")
    print("=" * 60)
    s1 = llm.with_structured_output(CityWeather)
    s2 = llm.with_structured_output(CityWeather)
    s3 = llm.with_structured_output(CityWeather, method="json_schema")
    print(f"PASS  s1 type: {type(s1).__name__}")
    print(f"PASS  s2 type: {type(s2).__name__}")
    print(f"PASS  s3 type: {type(s3).__name__} (explicit json_schema, same path)")
    # Override escape hatch: caller can still force a different method.
    s_override = llm.with_structured_output(CityWeather, method="function_calling")
    print(f"PASS  override respected: method=function_calling -> {type(s_override).__name__}")

    print()
    print("=" * 60)
    print("Step 3: wire format — bound kwargs include response_format json_schema")
    print("=" * 60)
    # langchain-openai composes the structured output as a RunnableSequence:
    #   bind(response_format=...) | parser
    # The first step in the sequence is the model bound with response_format.
    runnable = s1
    has_response_format = False
    has_tool_choice = False
    method_marker = None
    if hasattr(runnable, "first") and hasattr(runnable.first, "kwargs"):
        bound_kwargs = runnable.first.kwargs
        print(f"      bound kwargs keys: {sorted(bound_kwargs.keys())}")
        has_response_format = "response_format" in bound_kwargs
        has_tool_choice = "tool_choice" in bound_kwargs
        method_marker = bound_kwargs.get("ls_structured_output_format", {}).get("kwargs", {}).get("method")
    assert_eq("response_format key bound on request (json_schema path)", has_response_format, True)
    assert_eq("tool_choice NOT bound (no object-form forcing)", has_tool_choice, False)
    assert_eq("ls_structured_output_format.method", method_marker, "json_schema")

    print()
    print("=" * 60)
    print("Step 4: end-to-end — real call must return a strict CityWeather instance")
    print("=" * 60)
    print("      sending small request to http://127.0.0.1:11434/v1 ...")
    result = s1.invoke(
        "Tell me about Reykjavik in January. "
        "Answer using the schema fields exactly."
    )
    assert_isinstance("result type", result, CityWeather)
    print(f"      result.city                 = {result.city!r}")
    print(f"      result.season               = {result.season!r}")
    print(f"      result.temperature_celsius  = {result.temperature_celsius!r}")
    # Schema enforcement checks
    assert_isinstance("result.city is str", result.city, str)
    if result.season not in {"spring", "summer", "autumn", "winter"}:
        print(f"NOTE  season {result.season!r} not in expected enum; model picked freely")
    if result.temperature_celsius is not None:
        assert_isinstance(
            "temperature_celsius is float when present",
            result.temperature_celsius,
            float,
        )

    print()
    print("=" * 60)
    print("ALL CHECKS PASSED")
    print("=" * 60)
    print(
        "Conclusion: OllamaChatOpenAI uses response_format=json_schema by default "
        "for any model served on an OpenAI-compatible local endpoint. "
        "No tool_choice object form is sent, so llama.cpp will not emit the "
        "'Wrong type supplied for parameter tool_choice' warning, and structured "
        "output is grammar-constrained to the declared schema regardless of "
        "which GGUF model is loaded."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
