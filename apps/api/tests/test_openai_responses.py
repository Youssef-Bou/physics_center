"""Responses transport contracts. Every HTTP interaction stays inside MockTransport."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.modules.tutor.contracts import (
    GenerationParameters,
    GenerationRequest,
    Mode,
    ProviderError,
    StructuredMessage,
)
from app.modules.tutor.providers import (
    DEFAULT_REAL_MODEL,
    MAX_RESPONSE_BYTES,
    MockProvider,
    OpenAICompatibleProvider,
    OpenAIResponsesProvider,
    provider_from_environment,
)


@pytest.fixture(autouse=True)
def isolated_provider_configuration(monkeypatch):
    for name in (
        "PHYSICS_LLM_PROVIDER",
        "PHYSICS_LLM_API_KEY",
        "PHYSICS_LLM_BASE_URL",
        "PHYSICS_LLM_REASONING_EFFORT",
        "PHYSICS_LLM_ENABLE_REAL",
        "CI",
    ):
        monkeypatch.delenv(name, raising=False)


def request_for(*, model=DEFAULT_REAL_MODEL, effort=None):
    return GenerationRequest(
        messages=(
            StructuredMessage(role="system", content="Follow scientific response rules."),
            StructuredMessage(role="user", content="A controlled test question."),
        ),
        model=model,
        parameters=GenerationParameters(
            model=model,
            temperature=1.5,
            max_output_tokens=512,
            timeout_seconds=5,
            reasoning_effort=effort,
        ),
        mode=Mode.DEEP_PHYSICS_MODE,
    )


def response_payload(**overrides):
    output_text = json.dumps(
        {
            "blocks": [
                {
                    "kind": "derivation",
                    "text": "Controlled test output, not a scientific evaluation.",
                    "citation_ids": [],
                    "math_check_ids": [],
                }
            ],
            "uncertainties": ["test_fixture_only"],
            "math_claims": [],
        }
    )
    payload = {
        "id": "resp_controlled_test",
        "model": f"{DEFAULT_REAL_MODEL}-test-snapshot",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": [{"text": "SECRET REASONING MUST NOT BE STORED"}]},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": output_text, "annotations": []}],
            },
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_tokens_details": {"cached_tokens": 40},
            "output_tokens_details": {"reasoning_tokens": 20},
            "cache_write_tokens": 8,
        },
    }
    payload.update(overrides)
    return payload


def generate(provider, request=None):
    return asyncio.run(provider.generate(request or request_for()))


def adapter_for(payload=None, *, status=200, headers=None, calls=None):
    def respond(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(
            status,
            json=response_payload() if payload is None else payload,
            headers=headers,
        )

    return OpenAIResponsesProvider(
        "https://llm.example/v1",
        "synthetic-test-key",
        transport=httpx.MockTransport(respond),
    )


def test_responses_payload_uses_actual_reasoning_capability_and_no_remote_state():
    calls = []
    result = generate(adapter_for(calls=calls))
    assert len(calls) == 1
    assert str(calls[0].url) == "https://llm.example/v1/responses"
    payload = json.loads(calls[0].content)
    assert payload["model"] == DEFAULT_REAL_MODEL == "gpt-6.1-sol"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["max_output_tokens"] == 512
    assert payload["store"] is False
    assert payload["input"] == [message.model_dump() for message in request_for().messages]
    assert "temperature" not in payload
    assert "tools" not in payload
    assert "previous_response_id" not in payload
    assert "conversation" not in payload
    schema = payload["text"]["format"]
    assert schema["type"] == "json_schema" and schema["strict"] is True
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
    assert result.provider_name == "openai_responses"
    assert result.model_name == f"{DEFAULT_REAL_MODEL}-test-snapshot"
    assert result.response_id == "resp_controlled_test"
    assert result.effective_parameters["reasoning_effort"] == "medium"
    assert result.effective_parameters["max_output_tokens"] == 512
    assert "temperature" not in result.effective_parameters
    assert "SECRET REASONING" not in result.model_dump_json()
    assert "synthetic-test-key" not in json.dumps(payload)


def test_usage_preserves_subsets_without_adding_them_to_totals():
    result = generate(adapter_for())
    assert result.usage == {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "cached_input_tokens": 40,
        "reasoning_tokens": 20,
        "cache_write_tokens": 8,
    }
    assert result.usage["total_tokens"] == (
        result.usage["input_tokens"] + result.usage["output_tokens"]
    )


def test_nested_cache_write_usage_is_preserved_when_present():
    payload = response_payload()
    del payload["usage"]["cache_write_tokens"]
    payload["usage"]["input_tokens_details"]["cache_write_tokens"] = 5
    assert generate(adapter_for(payload)).usage["cache_write_tokens"] == 5


def test_missing_optional_usage_and_identifiers_are_not_fabricated():
    payload = response_payload()
    for name in ("usage", "id", "model"):
        del payload[name]
    result = generate(adapter_for(payload))
    assert result.usage == {}
    assert result.response_id is None
    assert result.model_name == DEFAULT_REAL_MODEL


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_known_model_supports_documented_reasoning_efforts(effort):
    calls = []
    result = generate(adapter_for(calls=calls), request_for(effort=effort))
    assert json.loads(calls[0].content)["reasoning"]["effort"] == effort
    assert result.effective_parameters["reasoning_effort"] == effort


@pytest.mark.parametrize("effort", ["none", "minimal"])
def test_unsupported_known_model_efforts_are_rejected_before_http(effort):
    calls = []
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(calls=calls), request_for(effort=effort))
    assert error.value.code == "invalid_configuration"
    assert not calls


def test_environment_reasoning_default_can_be_overridden_per_request(monkeypatch):
    monkeypatch.setenv("PHYSICS_LLM_REASONING_EFFORT", "high")
    assert generate(adapter_for()).effective_parameters["reasoning_effort"] == "high"
    assert (
        generate(adapter_for(), request_for(effort="low")).effective_parameters["reasoning_effort"]
        == "low"
    )
    monkeypatch.setenv("PHYSICS_LLM_REASONING_EFFORT", "not-supported")
    calls = []
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(calls=calls))
    assert error.value.code == "invalid_configuration"
    assert not calls


def test_unknown_model_does_not_inherit_assumed_reasoning_support():
    calls = []
    generate(adapter_for(calls=calls), request_for(model="another-model"))
    assert "reasoning" not in json.loads(calls[0].content)


@pytest.mark.parametrize("status", ["incomplete", "in_progress", "failed", "cancelled", None])
def test_only_completed_responses_are_accepted(status):
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(response_payload(status=status)))
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize(
    "output",
    [
        [],
        None,
        [None],
        [{"type": "function_call", "arguments": "{}"}],
        [{"type": "message", "content": [{"type": "refusal", "refusal": "Cannot answer"}]}],
        [{"type": "message", "content": [{"type": "output_text", "text": "not JSON"}]}],
        [{"type": "message", "content": [{"type": "output_text", "text": '{"blocks":[]}'}]}],
        [{"type": "message", "content": [{"type": "output_text", "text": None}]}],
    ],
)
def test_refusals_tool_items_and_malformed_output_are_not_answers(output):
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(response_payload(output=output)))
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize(
    "usage",
    [
        [],
        {"input_tokens": -1},
        {"output_tokens": True},
        {"input_tokens": 5, "input_tokens_details": {"cached_tokens": 6}},
        {"output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 6}},
    ],
)
def test_invalid_usage_is_not_reported_as_valid_cost_input(usage):
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(response_payload(usage=usage)))
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize(
    "retry_after,expected", [("3", 3), ("2.5", 3), ("9999", 300), ("bad", None)]
)
def test_rate_limit_is_safe_bounded_and_not_retried(retry_after, expected):
    calls = []
    with pytest.raises(ProviderError) as error:
        generate(
            adapter_for(
                {"error": "SECRET PROVIDER ERROR synthetic-test-key"},
                status=429,
                headers={"retry-after": retry_after},
                calls=calls,
            )
        )
    assert error.value.code == "rate_limit"
    assert error.value.retry_after_seconds == expected
    assert "SECRET" not in str(error.value)
    assert "synthetic-test-key" not in str(error.value)
    assert len(calls) == 1


def test_retry_after_http_date_is_bounded():
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=1000), usegmt=True)
    with pytest.raises(ProviderError) as error:
        generate(adapter_for(status=429, headers={"retry-after": when}))
    assert error.value.retry_after_seconds == 300


def test_response_size_limit_applies_before_parsing():
    provider = OpenAIResponsesProvider(
        "https://llm.example/v1",
        "synthetic-test-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1))
        ),
    )
    with pytest.raises(ProviderError) as error:
        generate(provider)
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize("provider_class", [OpenAIResponsesProvider, OpenAICompatibleProvider])
def test_real_network_disabled_by_default_before_client_creation(monkeypatch, provider_class):
    def forbidden_client(*args, **kwargs):
        pytest.fail("The real HTTP client must not be created while disabled")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    provider = provider_class("https://llm.example/v1", "synthetic-test-key")
    with pytest.raises(ProviderError) as error:
        generate(provider)
    assert error.value.code == "disabled"


@pytest.mark.parametrize("ci_value", ["1", "true", "yes", "CI-system"])
def test_ci_blocks_real_calls_even_when_explicitly_enabled(monkeypatch, ci_value):
    monkeypatch.setenv("CI", ci_value)

    def forbidden_client(*args, **kwargs):
        pytest.fail("CI must never create a real HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden_client)
    provider = OpenAIResponsesProvider(
        "https://llm.example/v1", "synthetic-test-key", allow_real_calls=True
    )
    with pytest.raises(ProviderError) as error:
        generate(provider)
    assert error.value.code == "disabled"


def test_only_mock_transport_can_bypass_the_paid_gate():
    class NetworkTripwire(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            pytest.fail("A nonmock transport cannot bypass the paid-call gate")

    provider = OpenAIResponsesProvider(
        "https://llm.example/v1", "synthetic-test-key", transport=NetworkTripwire()
    )
    with pytest.raises(ProviderError) as error:
        generate(provider)
    assert error.value.code == "disabled"


def test_mock_transport_remains_usable_in_ci_without_paid_authorization(monkeypatch):
    monkeypatch.setenv("CI", "true")
    assert generate(adapter_for()).provider_name == "openai_responses"


def test_factory_default_is_mock_and_responses_requires_a_key(monkeypatch):
    assert isinstance(provider_from_environment(), MockProvider)
    monkeypatch.setenv("PHYSICS_LLM_PROVIDER", "openai_responses")
    with pytest.raises(ProviderError):
        provider_from_environment()
    monkeypatch.setenv("PHYSICS_LLM_API_KEY", "synthetic-test-key")
    provider = provider_from_environment()
    assert isinstance(provider, OpenAIResponsesProvider)
    with pytest.raises(ProviderError) as error:
        generate(provider)
    assert error.value.code == "disabled"


def test_factory_flag_alone_does_not_enable_network_in_ci(monkeypatch):
    monkeypatch.setenv("PHYSICS_LLM_PROVIDER", "openai_responses")
    monkeypatch.setenv("PHYSICS_LLM_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("PHYSICS_LLM_ENABLE_REAL", "1")
    monkeypatch.setenv("CI", "true")
    with pytest.raises(ProviderError) as error:
        generate(provider_from_environment())
    assert error.value.code == "disabled"


def test_explicit_enablement_reaches_the_http_path_with_no_paid_test_call(monkeypatch):
    """Exercise production gate logic, replacing the HTTP client before any I/O."""
    monkeypatch.setenv("PHYSICS_LLM_PROVIDER", "openai_responses")
    monkeypatch.setenv("PHYSICS_LLM_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("PHYSICS_LLM_ENABLE_REAL", "1")
    requests = []
    real_client_class = httpx.AsyncClient

    def mocked_client(**kwargs):
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json=response_payload())

        kwargs["transport"] = httpx.MockTransport(respond)
        return real_client_class(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", mocked_client)
    assert generate(provider_from_environment()).provider_name == "openai_responses"
    assert len(requests) == 1
