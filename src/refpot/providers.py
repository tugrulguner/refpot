"""Bounded zero-spend OpenRouter provider for SQL query proposals.

HTTP operations use socket timeouts and byte caps; urllib cannot impose a hard
wall-clock deadline across DNS/TLS. Requests are HTTPS-only to OpenRouter's
fixed origin. No SDK, tool loop, fallback, or retry is used.
"""

from __future__ import annotations

import json
import math
import os
import re
from decimal import Decimal, InvalidOperation
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .agent import AgentError, Clarification, Decline, GenerationRequest, QueryProposal


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# Keep the symbol patchable for deterministic protocol tests while disabling
# urllib's default redirect-following behavior in production.
urlopen = build_opener(_NoRedirect()).open
_MAX_CATALOG = 4 * 1024 * 1024
_MAX_RESPONSE = 1024 * 1024
_MAX_QUESTION = 65536
_MAX_MODEL_TOKENS = 2048
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,180}:free\Z")
_SYSTEM = """Return exactly one JSON object with no markdown and no extra fields.
Choose one action: {"action":"query","query":"...","parameters":[...],"assumptions":[...]};
{"action":"clarify","questions":[...]}; or {"action":"decline","reason":"..."}.
For query, write one SELECT statement only. Use only the authorized relations and
columns listed in the user message. Use ? placeholders and exact signed-64-bit
integer parameters (booleans are not integers here). Never invent business rules:
ask a concise clarification for ambiguity; decline unsupported requests. Do not
sample or infer from rows; none are supplied. Never request paths, credentials,
revision tokens, or other secrets. The native database validates all SQL.

All stored columns are signed-64-bit INTEGER NOT NULL, including primary keys.
Empty global COUNT(*) returns 0; empty global SUM returns SQL NULL. SQL identifiers
are unquoted ASCII names, case-insensitive, beginning with a letter, at most 64 bytes.
Supported SQL is a small native subset: SELECT named columns or * from one table,
optionally one equijoin, AND-connected comparisons against an integer literal or
? parameter, optional GROUP BY one column, COUNT(*) and SUM(column), and ORDER BY
selected output names/aliases plus LIMIT. With aggregates/grouping, every projected
nonaggregate column must be the grouping column. COUNT(*) is supported; AVG,
arithmetic expressions, DISTINCT, OR, outer/multiple joins, and other SQL features
are not. LIMIT must be an integer from 0 through 100000; use ? bindings for values.
Grouping/aggregates support only the stated restrictions. Decline unsupported
semantics rather than replacing them with a different question. A SELECT is still
checked by the native parser and relation authority boundary."""


def _no_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json_load(raw: bytes, limit: int):
    if len(raw) > limit:
        raise ValueError("response exceeds byte limit")
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_no_duplicate_pairs,
        # Preserve nonzero prices that binary float would underflow to zero.
        parse_float=Decimal,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid JSON number")),
    )
    stack = [(value, 0)]
    while stack:
        node, depth = stack.pop()
        if depth > 32:
            raise ValueError("JSON nesting exceeds limit")
        if isinstance(node, dict):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)
    return value


def _price_is_zero(value: object) -> bool:
    if type(value) not in (str, int, Decimal):
        return False
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return price.is_finite() and price == 0


class OpenRouter:
    """Callable AgentConfig generator using a catalog-verified `:free` model."""

    def __init__(
        self,
        model: str = "nvidia/nemotron-3.5-super-vl:free",
        *,
        api_key_env: str = "OPENROUTER_API_KEY",
        timeout: float = 30,
        max_tokens: int = _MAX_MODEL_TOKENS,
    ) -> None:
        if type(model) is not str or not _MODEL.fullmatch(model):
            raise ValueError("model must be a fixed OpenRouter model ending in :free")
        if type(api_key_env) is not str or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env):
            raise ValueError("api_key_env must be an environment variable name")
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > 120
        ):
            raise ValueError("timeout must be greater than zero and at most 120 seconds")
        if type(max_tokens) is not int or not 1 <= max_tokens <= _MAX_MODEL_TOKENS:
            raise ValueError("max_tokens must be between 1 and 2048")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = float(timeout)
        self.max_tokens = max_tokens

    def _request(self, url: str, *, key: str | None, body: bytes | None, limit: int) -> bytes:
        headers = {"Accept": "application/json"}
        if key is not None:
            headers["Authorization"] = f"Bearer {key}"
            headers["Content-Type"] = "application/json"
        req = Request(url, data=body, headers=headers, method="GET" if body is None else "POST")
        try:
            with urlopen(req, timeout=self.timeout) as response:
                status = response.getcode()
                if status != 200:
                    raise AgentError("OpenRouter returned a non-success status")
                raw = response.read(limit + 1)
        except AgentError:
            raise
        except (HTTPError, URLError, TimeoutError, OSError, HTTPException, ValueError):
            raise AgentError("OpenRouter request failed") from None
        if len(raw) > limit:
            raise AgentError("OpenRouter response exceeds byte limit")
        return raw

    def _verify_catalog(self) -> None:
        raw = self._request(
            "https://openrouter.ai/api/v1/models", key=None, body=None, limit=_MAX_CATALOG
        )
        try:
            payload = _json_load(raw, _MAX_CATALOG)
            models = payload["data"]
            if type(models) is not list:
                raise ValueError("invalid model catalog")
            matches = [
                item for item in models if type(item) is dict and item.get("id") == self.model
            ]
            if len(matches) != 1:
                raise ValueError("model must occur once in the catalog")
            data = matches[0]
            pricing = data["pricing"]
            valid = (
                type(payload) is dict
                and type(data) is dict
                and data.get("id") == self.model
                and type(pricing) is dict
                and _price_is_zero(pricing.get("prompt"))
                and _price_is_zero(pricing.get("completion"))
            )
        except (KeyError, TypeError, ValueError, RecursionError):
            valid = False
        if not valid:
            raise AgentError("OpenRouter model is unknown or not verified zero-cost")

    def __call__(self, request: GenerationRequest):
        if type(request) is not GenerationRequest or type(request.query) is not str:
            raise AgentError("invalid generation request")
        question = request.query.encode("utf-8")
        if not question or len(question) > _MAX_QUESTION:
            raise AgentError("question exceeds byte limit")
        key = os.environ.get(self.api_key_env)
        if not key:
            raise AgentError("OpenRouter API key is not configured")
        schema = []
        for relation in request.relations:
            schema.append(
                {
                    "name": relation.name,
                    "columns": list(relation.columns),
                    "derived": relation.derived,
                }
            )
        try:
            self._verify_catalog()
            body = json.dumps(
                {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"question": request.query, "authorized_schema": schema},
                                ensure_ascii=False,
                            ),
                        },
                    ],
                    "max_tokens": self.max_tokens,
                    "temperature": 0,
                    "stream": False,
                    "tools": [],
                    "response_format": {"type": "json_object"},
                    "provider": {
                        "allow_fallbacks": False,
                        "max_price": {"prompt": 0, "completion": 0},
                    },
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            raw = self._request(
                "https://openrouter.ai/api/v1/chat/completions",
                key=key,
                body=body,
                limit=_MAX_RESPONSE,
            )
            payload = _json_load(raw, _MAX_RESPONSE)
            if type(payload) is not dict or payload.get("model") != self.model:
                raise AgentError("OpenRouter response model did not match the configured model")
            usage = payload.get("usage")
            if type(usage) is not dict or not _price_is_zero(usage.get("cost")):
                raise AgentError("OpenRouter did not report a zero-cost response")
            choices = payload["choices"]
            if type(choices) is not list or len(choices) != 1:
                raise ValueError("invalid choices")
            choice = choices[0]
            if type(choice) is not dict or choice.get("finish_reason") != "stop":
                raise ValueError("incomplete response")
            message = choice["message"]
            if type(message) is not dict or message.get("tool_calls") not in (None, []):
                raise ValueError("tool calls are unsupported")
            content = message.get("content")
            if type(content) is not str or len(content.encode("utf-8")) > 65536:
                raise ValueError("invalid content")
            envelope = _json_load(content.encode("utf-8"), 65536)
            if type(envelope) is not dict or type(envelope.get("action")) is not str:
                raise ValueError("invalid action envelope")
            action = envelope["action"]
            if action == "query" and set(envelope) == {
                "action",
                "query",
                "parameters",
                "assumptions",
            }:
                query, params, assumptions = (
                    envelope["query"],
                    envelope["parameters"],
                    envelope["assumptions"],
                )
                if (
                    type(query) is not str
                    or not query
                    or len(query.encode("utf-8")) > 65536
                    or type(params) is not list
                    or len(params) > 8192
                    or any(type(x) is not int or not -(1 << 63) <= x < (1 << 63) for x in params)
                    or type(assumptions) is not list
                    or len(assumptions) > 16
                    or any(
                        type(x) is not str or not x or len(x.encode("utf-8")) > 4096
                        for x in assumptions
                    )
                ):
                    raise ValueError("invalid query proposal")
                return QueryProposal(query, tuple(params), tuple(assumptions))
            if action == "clarify" and set(envelope) == {"action", "questions"}:
                items = envelope["questions"]
                if (
                    type(items) is not list
                    or not 1 <= len(items) <= 16
                    or any(
                        type(x) is not str or not x or len(x.encode("utf-8")) > 4096 for x in items
                    )
                ):
                    raise ValueError("invalid clarification")
                return Clarification(tuple(items))
            if action == "decline" and set(envelope) == {"action", "reason"}:
                reason = envelope["reason"]
                if type(reason) is not str or not reason or len(reason.encode("utf-8")) > 4096:
                    raise ValueError("invalid decline")
                return Decline(reason)
            raise ValueError("unsupported action")
        except AgentError:
            raise
        except (KeyError, TypeError, ValueError, InvalidOperation, RecursionError, UnicodeError):
            raise AgentError("OpenRouter response was invalid or incomplete") from None


__all__ = ["OpenRouter"]
