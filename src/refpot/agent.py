"""Explicit, schema-only query generation contracts.

Generators are trusted caller-configured Python code. Their proposals are data,
not authority: the native read-only binder enforces relation access and grammar.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class AgentError(RuntimeError):
    """Generation failed before native query execution."""


def _bounded_texts(value: object, *, nonempty: bool = False) -> None:
    if (
        type(value) is not tuple
        or len(value) > 16
        or (nonempty and not value)
        or any(
            type(text) is not str or not text or len(text.encode("utf-8")) > 4096 for text in value
        )
    ):
        raise AgentError("generation metadata must be bounded immutable text")


class ClarificationRequired(AgentError):
    """The caller must resolve these questions before requesting generation again."""

    def __init__(self, questions: tuple[str, ...]) -> None:
        self.questions = questions
        super().__init__("query requires clarification")


class QueryDeclined(AgentError):
    """The generator declined the request without executing a query."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__("query generation declined")


@dataclass(frozen=True, slots=True)
class Clarification:
    questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Decline:
    reason: str


@dataclass(frozen=True, slots=True)
class Relation:
    name: str
    columns: tuple[str, ...]
    derived: bool


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    query: str
    relations: tuple[Relation, ...]


@dataclass(frozen=True, slots=True)
class QueryProposal:
    query: str
    parameters: tuple[int, ...] = ()
    assumptions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Generation:
    query: str
    parameters: tuple[int, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AgentConfig:
    generator: Callable[[GenerationRequest], QueryProposal | Clarification | Decline]
    relations: tuple[str, ...]
    disclose_schema: bool = False

    def __post_init__(self) -> None:
        if not callable(self.generator):
            raise TypeError("generator must be callable")
        if type(self.relations) is not tuple:
            raise TypeError("relations must be an immutable tuple")
        if not 1 <= len(self.relations) <= 128:
            raise ValueError("authorize between one and 128 relations explicitly")
        if any(
            type(name) is not str or not name or len(name.encode("utf-8")) > 64
            for name in self.relations
        ):
            raise ValueError("relations must contain nonempty names of at most 64 UTF-8 bytes")
        if len(set(self.relations)) != len(self.relations):
            raise ValueError("duplicate authorized relation")
        if type(self.disclose_schema) is not bool:
            raise TypeError("disclose_schema must be bool")
