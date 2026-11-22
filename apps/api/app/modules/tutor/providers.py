"""Small asynchronous LLM adapters; provider SDK types never enter the domain."""

import json
import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import ValidationError

from app.modules.tutor.contracts import (
    AnswerBlock,
    GenerationRequest,
    GenerationResult,
    LLMDraft,
    Mode,
    Provider,
    ProviderError,
)

MAX_RESPONSE_BYTES = 1024 * 1024
DEFAULT_REAL_MODEL = "gpt-6.1-sol"
DEFAULT_REASONING_EFFORT = "medium"
REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})
KNOWN_REASONING_CAPABILITIES = {
    DEFAULT_REAL_MODEL: frozenset({"low", "medium", "high", "xhigh", "max"})
}


def _ci_is_truthy() -> bool:
    return os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no", "off"}


def _retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return min(300, math.ceil(seconds))


class MockProvider:
    """Deterministic demonstrator, deliberately not a simulated physics expert."""

    name = "mock"
    is_mock = True
    is_external = False

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        passages = request.source_context.get("passages", request.source_context.get("hits", []))
        if not passages:
            passages = request.source_context.get("tutor_context", {}).get("passages", [])
        citation = None
        for passage in passages:
            try:
                citation = UUID(str(passage["citation_id"]))
                break
            except (KeyError, TypeError, ValueError):
                continue

        blocks = []
        if citation:
            blocks.append(
                AnswerBlock(
                    kind="source_content",
                    text=(
                        "MOCK: Eine Fundstelle wurde im freigegebenen Kontext bereitgestellt. "
                        "Diese Demo prüft keine wissenschaftliche Aussage des Dokuments."
                    ),
                    citation_ids=[citation],
                )
            )

        if request.mode == Mode.SOCRATIC_MODE and not request.direct_answer:
            text = (
                "MOCK: Welche Größen sind gegeben und welche gesucht? "
                "Welche Annahme und welchen ersten Ansatz möchtest du prüfen? "
                "Dies sind Demonstrationsfragen, keine fachlich geprüfte Lösung."
            )
        elif request.mode == Mode.SOCRATIC_MODE:
            text = (
                "MOCK: Eine direkte Antwort wurde ausdrücklich angefordert. "
                "Die Demo erzeugt keine vollständige physikalische Lösung."
            )
        else:
            text = (
                f"MOCK: Modus {request.mode.value}, Tiefe {request.depth.value}. "
                "Diese deterministische Demo erzeugt keine physikalische Herleitung "
                "und ersetzt keine fachliche Prüfung."
            )
        blocks.append(
            AnswerBlock(
                kind="derivation" if request.mode == Mode.SOURCE_MODE else "model_knowledge",
                text=text,
            )
        )
        uncertainties = ["mock_output_not_scientifically_evaluated"]
        if citation is None:
            uncertainties.append("no_source_citation_in_context")
        return GenerationResult(
            draft=LLMDraft(blocks=blocks, uncertainties=uncertainties),
            provider_name=self.name,
            model_name=request.model,
            usage={},
        )


def _strict_schema(value: Any) -> Any:
    """OpenAI strict object schemas require every property and forbid extras."""
    if isinstance(value, list):
        return [_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    output = {key: _strict_schema(item) for key, item in value.items() if key != "default"}
    if output.get("type") == "object" and "properties" in output:
        output["required"] = list(output["properties"])
        output["additionalProperties"] = False
    return output


class OpenAICompatibleProvider:
    """HTTPS chat-completions adapter with bounded, validated JSON output."""

    name = "openai_compatible"
    is_mock = False
    is_external = True

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        allow_real_calls: bool = False,
    ):
        try:
            parsed = urlsplit(base_url)
            valid_url = (
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
            )
            _ = parsed.port
        except ValueError:
            valid_url = False
        if not valid_url:
            raise ProviderError("unavailable", "The LLM endpoint must be a valid HTTPS base URL.")
        if not api_key or not api_key.strip() or "\n" in api_key or "\r" in api_key:
            raise ProviderError("unavailable", "LLM credentials are not configured correctly.")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._transport = transport
        self._allow_real_calls = allow_real_calls is True

    def _ensure_real_calls_allowed(self) -> None:
        # Only the in-memory test transport bypasses the paid-call gate. A custom
        # socket/network transport does not become an implicit authorization.
        if isinstance(self._transport, httpx.MockTransport):
            return
        if _ci_is_truthy():
            raise ProviderError("disabled", "Real LLM calls are disabled in CI.")
        if not self._allow_real_calls:
            raise ProviderError("disabled", "Real LLM calls require explicit enablement.")

    async def _post(
        self,
        endpoint: str,
        payload: dict,
        timeout_seconds: float,
        *,
        rate_limit_errors: bool = False,
    ) -> bytearray:
        self._ensure_real_calls_allowed()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}{endpoint}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                ) as response:
                    if response.status_code == 429 and rate_limit_errors:
                        raise ProviderError(
                            "rate_limit",
                            "The LLM service rate limit was reached.",
                            retry_after_seconds=_retry_after_seconds(
                                response.headers.get("retry-after")
                            ),
                        )
                    if not 200 <= response.status_code < 300:
                        raise ProviderError(
                            "unavailable", "The LLM service could not complete the request."
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ProviderError(
                                "invalid_response", "The LLM response exceeded its size limit."
                            )
                        body.extend(chunk)
                    return body
        except httpx.TimeoutException:
            raise ProviderError("timeout", "The LLM request timed out.") from None
        except httpx.HTTPError:
            raise ProviderError(
                "unavailable", "The LLM service is currently unavailable."
            ) from None

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        parameters = request.parameters
        payload = {
            "model": request.model,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": parameters.temperature,
            "max_tokens": parameters.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "physics_tutor_answer",
                    "strict": True,
                    "schema": _strict_schema(LLMDraft.model_json_schema()),
                },
            },
        }
        body = await self._post("/chat/completions", payload, parameters.timeout_seconds)

        try:
            output = json.loads(body)
            if not isinstance(output, dict) or not isinstance(output.get("choices"), list):
                raise ValueError("An answer object is required")
            choice = output["choices"][0]
            if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
                raise ValueError("A message object is required")
            if choice.get("finish_reason") == "length":
                raise ValueError("Truncated result")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ValueError("A JSON content string is required")
            draft = LLMDraft.model_validate_json(content)
            usage = {}
            usage_payload = output.get("usage") or {}
            if not isinstance(usage_payload, dict):
                raise ValueError("Invalid usage metadata")
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = usage_payload.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    usage[key] = value
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise ProviderError(
                "invalid_response", "The LLM returned an invalid structured answer."
            ) from None
        return GenerationResult(
            draft=draft,
            provider_name=self.name,
            model_name=request.model,
            usage=usage,
        )


def _responses_usage(payload: Any) -> dict[str, int]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Invalid usage metadata")
    usage = {}

    def retain(name: str, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Invalid token count")
        usage[name] = value

    for name in ("input_tokens", "output_tokens", "total_tokens"):
        retain(name, payload.get(name))
    input_details = payload.get("input_tokens_details") or {}
    output_details = payload.get("output_tokens_details") or {}
    if not isinstance(input_details, dict) or not isinstance(output_details, dict):
        raise ValueError("Invalid token details")
    retain("cached_input_tokens", input_details.get("cached_tokens"))
    retain("reasoning_tokens", output_details.get("reasoning_tokens"))
    retain(
        "cache_write_tokens",
        payload.get("cache_write_tokens", input_details.get("cache_write_tokens")),
    )
    # Cached/reasoning counts are subsets. Preserve their separate counters but
    # never add them to the API's input/output/total counters.
    if usage.get("cached_input_tokens", 0) > usage.get("input_tokens", math.inf):
        raise ValueError("Cached tokens exceed input tokens")
    if usage.get("reasoning_tokens", 0) > usage.get("output_tokens", math.inf):
        raise ValueError("Reasoning tokens exceed output tokens")
    return usage


class OpenAIResponsesProvider(OpenAICompatibleProvider):
    """OpenAI Responses API adapter with explicit reasoning and no remote state."""

    name = "openai_responses"

    def _reasoning_effort(self, request: GenerationRequest) -> str | None:
        effort = request.parameters.reasoning_effort
        if effort is None:
            effort = os.environ.get("PHYSICS_LLM_REASONING_EFFORT")
        if effort is None and request.model in KNOWN_REASONING_CAPABILITIES:
            effort = DEFAULT_REASONING_EFFORT
        if effort is not None and effort not in REASONING_EFFORTS:
            raise ProviderError("invalid_configuration", "The reasoning effort is not supported.")
        supported = KNOWN_REASONING_CAPABILITIES.get(request.model)
        if supported is not None and effort not in supported:
            raise ProviderError(
                "invalid_configuration", "The reasoning effort is not supported by this model."
            )
        return effort

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        parameters = request.parameters
        effort = self._reasoning_effort(request)
        payload = {
            "model": request.model,
            "input": [message.model_dump() for message in request.messages],
            "max_output_tokens": parameters.max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "physics_tutor_answer",
                    "strict": True,
                    "schema": _strict_schema(LLMDraft.model_json_schema()),
                }
            },
        }
        effective_parameters = {
            "model": request.model,
            "max_output_tokens": parameters.max_output_tokens,
            "timeout_seconds": parameters.timeout_seconds,
            "store": False,
        }
        if effort is not None:
            payload["reasoning"] = {"effort": effort}
            effective_parameters["reasoning_effort"] = effort
        body = await self._post(
            "/responses", payload, parameters.timeout_seconds, rate_limit_errors=True
        )
        try:
            output = json.loads(body)
            if not isinstance(output, dict) or output.get("status") != "completed":
                raise ValueError("An incomplete response is not an answer")
            if not isinstance(output.get("output"), list):
                raise ValueError("Response output is required")
            text_parts = []
            for item in output["output"]:
                if not isinstance(item, dict):
                    raise ValueError("Invalid output item")
                if item.get("type") == "reasoning":
                    continue
                if (
                    item.get("type") != "message"
                    or item.get("role", "assistant") != "assistant"
                    or item.get("status", "completed") != "completed"
                    or not isinstance(item.get("content"), list)
                ):
                    raise ValueError("An assistant message is required")
                for content in item["content"]:
                    if (
                        not isinstance(content, dict)
                        or content.get("type") != "output_text"
                        or not isinstance(content.get("text"), str)
                    ):
                        raise ValueError("Refused or malformed output")
                    text_parts.append(content["text"])
            if not text_parts:
                raise ValueError("A structured answer is required")
            draft = LLMDraft.model_validate_json("".join(text_parts))
            model_name = output.get("model", request.model)
            if not isinstance(model_name, str) or not 1 <= len(model_name) <= 255:
                raise ValueError("Invalid response model")
            response_id = output.get("id")
            if response_id is not None and (
                not isinstance(response_id, str) or not 1 <= len(response_id) <= 255
            ):
                raise ValueError("Invalid response identifier")
            usage = _responses_usage(output.get("usage"))
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise ProviderError(
                "invalid_response", "The LLM returned an incomplete or invalid structured answer."
            ) from None
        return GenerationResult(
            draft=draft,
            provider_name=self.name,
            model_name=model_name,
            usage=usage,
            effective_parameters=effective_parameters,
            response_id=response_id,
        )


def provider_from_environment() -> Provider:
    """Read bindings without exposing them; no network call occurs in this factory."""
    name = os.environ.get("PHYSICS_LLM_PROVIDER", "mock")
    if name == "mock":
        return MockProvider()
    if name in {"openai_compatible", "openai_responses"}:
        adapter = (
            OpenAIResponsesProvider if name == "openai_responses" else OpenAICompatibleProvider
        )
        return adapter(
            base_url=os.environ.get("PHYSICS_LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.environ.get("PHYSICS_LLM_API_KEY", ""),
            allow_real_calls=os.environ.get("PHYSICS_LLM_ENABLE_REAL") == "1"
            and not _ci_is_truthy(),
        )
    raise ProviderError("unavailable", "The configured LLM provider is not supported.")
