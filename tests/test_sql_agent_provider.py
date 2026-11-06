"""OpenRouter adapter protocol tests; all HTTP responses are labeled fixtures."""

import json
from email.message import Message
from urllib.error import HTTPError

import pytest

from refpot.agent import AgentConfig, AgentError
from refpot.sql import Database, SQLError

MODEL = "nvidia/nemotron-3.5-super-vl:free"


class FixtureResponse:
    def __init__(self, payload, *, status=200, headers=None):
        self.body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size=-1):
        if size < 0:
            return self.body
        return self.body[:size]

    def getcode(self):
        return self.status


def catalog(price="0", **overrides):
    item = {"id": MODEL, "pricing": {"prompt": price, "completion": price}}
    item.update(overrides)
    return {"data": [item]}


def chat(content, *, finish="stop", **choice_overrides):
    choice = {"finish_reason": finish, "message": {"content": content}}
    choice.update(choice_overrides)
    return {"choices": [choice], "model": MODEL, "usage": {"cost": 0}}


def install_fixtures(monkeypatch, responses, calls=None):
    import refpot.providers as providers

    queue = list(responses)

    def opener(request, *, timeout):
        if calls is not None:
            calls.append((request, timeout))
        if not queue:
            raise AssertionError("unexpected HTTP request")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(providers, "urlopen", opener)


def run_db(generator):
    with Database(agent=AgentConfig(generator, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
        db.execute("INSERT INTO items VALUES (1, 8)")
        db.execute("INSERT INTO items VALUES (2, 3)")
        return db.execute("Which items exceed five?", agent=True)


def test_openrouter_executes_structured_proposal_through_native_public_path(monkeypatch):
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    calls = []
    install_fixtures(
        monkeypatch,
        [
            FixtureResponse(catalog()),
            FixtureResponse(
                chat(
                    json.dumps(
                        {
                            "action": "query",
                            "query": "SELECT id FROM items WHERE quantity > ? ORDER BY id",
                            "parameters": [5],
                            "assumptions": [],
                        }
                    )
                )
            ),
        ],
        calls,
    )
    result = run_db(OpenRouter(model=MODEL, api_key_env="FIXTURE_OPENROUTER_KEY"))
    assert result.rows == ((1,),)
    assert result.generation is not None
    assert result.generation.query == "SELECT id FROM items WHERE quantity > ? ORDER BY id"
    assert result.generation.parameters == (5,)
    assert len(calls) == 2
    assert calls[0][0].full_url == "https://openrouter.ai/api/v1/models"
    request = json.loads(calls[1][0].data)
    assert request["model"] == MODEL
    assert request["provider"] == {
        "allow_fallbacks": False,
        "max_price": {"prompt": 0, "completion": 0},
    }
    assert request["tools"] == []
    assert request["response_format"] == {"type": "json_object"}
    assert "NOT NULL" in request["messages"][0]["content"]
    user_payload = json.loads(request["messages"][1]["content"])
    assert user_payload["authorized_schema"] == [
        {"name": "items", "columns": ["id", "quantity"], "derived": False}
    ]
    assert calls[1][1] == 30
    assert "fixture-secret" not in repr(calls)


def test_openrouter_structured_clarification_and_decline(monkeypatch):
    from refpot.agent import ClarificationRequired, QueryDeclined
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    for output, error in [
        ({"action": "clarify", "questions": ["Which threshold?"]}, ClarificationRequired),
        ({"action": "decline", "reason": "Unsupported request"}, QueryDeclined),
    ]:
        install_fixtures(
            monkeypatch, [FixtureResponse(catalog()), FixtureResponse(chat(json.dumps(output)))]
        )
        generator = OpenRouter(model=MODEL, api_key_env="FIXTURE_OPENROUTER_KEY")
        with Database(agent=AgentConfig(generator, ("items",), True)) as db:
            db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
            with pytest.raises(error):
                db.execute("Count items", agent=True)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_key",
        "http",
        "timeout",
        "truncated",
        "bad_json",
        "oversized",
        "redirect",
        "wrong_model",
        "paid",
        "unknown_cost",
        "length",
        "tools",
        "bad_action",
        "extra_field",
        "bool_param",
        "long_param",
    ],
)
def test_openrouter_rejects_untrusted_or_unbounded_provider_responses(monkeypatch, failure):
    from refpot.providers import OpenRouter

    if failure != "missing_key":
        monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    if failure == "missing_key":
        monkeypatch.delenv("FIXTURE_OPENROUTER_KEY", raising=False)
        install_fixtures(monkeypatch, [])
    elif failure == "http":
        install_fixtures(
            monkeypatch, [HTTPError("https://openrouter.ai", 429, "fixture", Message(), None)]
        )
    elif failure == "timeout":
        install_fixtures(monkeypatch, [TimeoutError("fixture detail")])
    elif failure == "truncated":
        install_fixtures(monkeypatch, [FixtureResponse(b'{"data":')])
    elif failure == "bad_json":
        install_fixtures(monkeypatch, [FixtureResponse(b"{broken")])
    elif failure == "oversized":
        install_fixtures(monkeypatch, [FixtureResponse(b" " * (4 * 1024 * 1024 + 1))])
    elif failure == "redirect":
        install_fixtures(
            monkeypatch,
            [FixtureResponse({}, status=302, headers={"Location": "https://evil.test"})],
        )
    elif failure == "wrong_model":
        install_fixtures(monkeypatch, [FixtureResponse(catalog(id="other/model:free"))])
    elif failure == "paid":
        install_fixtures(monkeypatch, [FixtureResponse(catalog("0.000001"))])
    elif failure == "unknown_cost":
        install_fixtures(
            monkeypatch,
            [
                FixtureResponse(
                    {"data": [{"id": MODEL, "pricing": {"prompt": "0", "completion": None}}]}
                )
            ],
        )
    elif failure == "length":
        install_fixtures(
            monkeypatch, [FixtureResponse(catalog()), FixtureResponse(chat("{}", finish="length"))]
        )
    elif failure == "tools":
        install_fixtures(
            monkeypatch,
            [
                FixtureResponse(catalog()),
                FixtureResponse(chat("{}", finish="tool_calls", tool_calls=[])),
            ],
        )
    else:
        payloads = {
            "bad_action": {
                "action": "sql",
                "query": "SELECT * FROM items",
                "parameters": [],
                "assumptions": [],
            },
            "extra_field": {
                "action": "query",
                "query": "SELECT * FROM items",
                "parameters": [],
                "assumptions": [],
                "secret": "x",
            },
            "bool_param": {
                "action": "query",
                "query": "SELECT * FROM items WHERE id = ?",
                "parameters": [True],
                "assumptions": [],
            },
            "long_param": {
                "action": "query",
                "query": "SELECT * FROM items",
                "parameters": [1] * 8193,
                "assumptions": [],
            },
        }
        install_fixtures(
            monkeypatch,
            [FixtureResponse(catalog()), FixtureResponse(chat(json.dumps(payloads[failure])))],
        )
    error = AgentError
    generator = OpenRouter(model=MODEL, api_key_env="FIXTURE_OPENROUTER_KEY")
    with Database(agent=AgentConfig(generator, ("items",), True)) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        with pytest.raises(error) as caught:
            db.execute("Count items", agent=True)
        assert "fixture-secret" not in repr(caught.value)
        assert "fixture detail" not in repr(caught.value)


def test_openrouter_never_retries_and_generated_sql_cannot_write(monkeypatch):
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    calls = []
    install_fixtures(
        monkeypatch,
        [
            FixtureResponse(catalog()),
            FixtureResponse(
                chat(
                    json.dumps(
                        {
                            "action": "query",
                            "query": "DELETE FROM items",
                            "parameters": [],
                            "assumptions": [],
                        }
                    )
                )
            ),
        ],
        calls,
    )
    with Database(
        agent=AgentConfig(
            OpenRouter(model=MODEL, api_key_env="FIXTURE_OPENROUTER_KEY"), ("items",), True
        )
    ) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO items VALUES (1)")
        with pytest.raises(SQLError):
            db.execute("delete the items", agent=True)
        assert db.execute("SELECT * FROM items").rows == ((1,),)
    assert len(calls) == 2


def test_openrouter_requires_literal_free_model_and_never_uses_custom_endpoint(monkeypatch):
    from refpot.providers import OpenRouter

    for model in ["openai/gpt-4o", "some-model:free:free", "https://evil.test/model:free"]:
        with pytest.raises((TypeError, ValueError)):
            OpenRouter(model=model)


@pytest.mark.parametrize("failure", ["paid_usage", "missing_usage", "wrong_response_model"])
def test_response_identity_and_reported_cost_are_checked_before_query_execution(
    monkeypatch, failure
):
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    payload = chat(
        json.dumps(
            {"action": "query", "query": "SELECT * FROM items", "parameters": [], "assumptions": []}
        )
    )
    if failure == "paid_usage":
        payload["usage"] = {"cost": 0.001}
    elif failure == "missing_usage":
        del payload["usage"]
    else:
        payload["model"] = "other/model:free"
    install_fixtures(monkeypatch, [FixtureResponse(catalog()), FixtureResponse(payload)])
    with pytest.raises(AgentError):
        run_db(OpenRouter(api_key_env="FIXTURE_OPENROUTER_KEY"))


@pytest.mark.parametrize("gate", ["prompt", "completion", "usage"])
@pytest.mark.parametrize(
    "token",
    ["1e-9999", "-1e-9999", '"1e-9999"', "0.001", "true", "null", "NaN", "1e999999999999999999999"],
)
def test_nonzero_or_invalid_prices_are_rejected_before_request_or_execution(
    monkeypatch, gate, token
):
    from refpot._sql import _Database
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    model_catalog = catalog()
    response = chat(
        json.dumps(
            {"action": "query", "query": "SELECT * FROM items", "parameters": [], "assumptions": []}
        )
    )
    if gate == "usage":
        response["usage"]["cost"] = "UNDERFLOW_TOKEN"
    else:
        model_catalog["data"][0]["pricing"][gate] = "UNDERFLOW_TOKEN"
    # Preserve the literal JSON number: constructing a Python float loses it first.
    responses = [
        FixtureResponse(json.dumps(payload).replace('"UNDERFLOW_TOKEN"', token).encode())
        for payload in (model_catalog, response)
    ]
    calls = []
    executions = []
    original = _Database.execute_readonly

    def execute_readonly(self, *args):
        executions.append(args)
        return original(self, *args)

    monkeypatch.setattr(_Database, "execute_readonly", execute_readonly)
    install_fixtures(monkeypatch, responses, calls)
    with pytest.raises(AgentError):
        run_db(OpenRouter(api_key_env="FIXTURE_OPENROUTER_KEY"))
    assert len(calls) == (2 if gate == "usage" else 1)
    assert executions == []


@pytest.mark.parametrize("token", ["0", "0.0", "-0.0", "0e-9999", '"0"', '"0.000"'])
def test_exact_zero_price_encodings_still_execute(monkeypatch, token):
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    response = chat(
        json.dumps(
            {
                "action": "query",
                "query": "SELECT id FROM items WHERE quantity > ? ORDER BY id",
                "parameters": [5],
                "assumptions": [],
            }
        )
    )
    response["usage"]["cost"] = "ZERO_TOKEN"
    calls = []
    install_fixtures(
        monkeypatch,
        [
            FixtureResponse(json.dumps(payload).replace('"ZERO_TOKEN"', token).encode())
            for payload in (catalog("ZERO_TOKEN"), response)
        ],
        calls,
    )
    result = run_db(OpenRouter(api_key_env="FIXTURE_OPENROUTER_KEY"))
    assert result.rows == ((1,),)
    assert result.generation is not None
    assert result.generation.parameters == (5,)
    assert len(calls) == 2


@pytest.mark.parametrize("token", ["1.0", "1e0", "1e-9999"])
def test_decimal_json_bindings_are_not_coerced_to_integers(monkeypatch, token):
    from refpot.providers import OpenRouter

    monkeypatch.setenv("FIXTURE_OPENROUTER_KEY", "fixture-secret")
    content = json.dumps(
        {
            "action": "query",
            "query": "SELECT id FROM items WHERE id = ?",
            "parameters": ["DECIMAL_TOKEN"],
            "assumptions": [],
        }
    ).replace('"DECIMAL_TOKEN"', token)
    install_fixtures(monkeypatch, [FixtureResponse(catalog()), FixtureResponse(chat(content))])
    with pytest.raises(AgentError):
        run_db(OpenRouter(api_key_env="FIXTURE_OPENROUTER_KEY"))


def test_nonfinite_timeout_is_rejected():
    from refpot.providers import OpenRouter

    with pytest.raises(ValueError, match="timeout"):
        OpenRouter(timeout=float("nan"))
