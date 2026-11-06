"""SQL preview API with optional native whole-model file persistence."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import islice
from typing import TYPE_CHECKING

from ._sql import _Database

if TYPE_CHECKING:
    from .agent import AgentConfig, Generation


class SQLError(RuntimeError):
    """A native SQL statement was rejected."""


@dataclass(frozen=True, slots=True)
class Result:
    """Detached immutable results from a SQL statement."""

    columns: tuple[str, ...]
    rows: tuple[tuple[int | None, ...], ...]
    affected: int
    plan: str
    generation: Generation | None = None


class Database:
    """A single-owner SQL database: volatile by default, persistent with a path."""

    def __init__(
        self,
        path: str | os.PathLike[str] | None = None,
        *,
        mode: str = "overlay",
        agent: AgentConfig | None = None,
    ) -> None:
        if agent is not None:
            from .agent import AgentConfig

            if type(agent) is not AgentConfig:
                raise TypeError("agent must be an AgentConfig")
        self._agent = agent
        if mode not in ("overlay", "modular"):
            raise ValueError("mode must be 'overlay' or 'modular'")
        filename = None if path is None else os.fspath(path)
        if filename is not None:
            if not isinstance(filename, str):
                raise TypeError("database path must be str or PathLike[str]")
            if not filename or "\0" in filename:
                raise ValueError("database path must be nonempty and NUL-free")
            try:
                filename.encode("utf-8")
            except UnicodeError as exc:
                raise ValueError("database path must be valid UTF-8") from exc
        self._pid = os.getpid()
        self._thread = threading.get_ident()
        self._closed = False
        self._busy = False
        self._in_transaction = False
        self._scope = False
        self._aborted = False
        self._db = _Database(mode, filename)

    def _check(self) -> None:
        if (os.getpid(), threading.get_ident()) != (self._pid, self._thread):
            raise RuntimeError("database belongs to its creating process and thread")
        if self._closed:
            raise RuntimeError("database is closed")
        if self._busy:
            raise RuntimeError("reentrant database operation is unsupported")

    @contextmanager
    def _operation(self) -> Iterator[None]:
        self._check()
        self._busy = True
        try:
            yield
        finally:
            self._busy = False

    @staticmethod
    def _arguments(query: str, parameters: Sequence[int]) -> tuple[str, tuple[int, ...]]:
        if not isinstance(query, str):
            raise TypeError("query must be a SQL string")
        try:
            encoded = query.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("query must be valid UTF-8") from exc
        if not encoded or len(encoded) > 65536 or b"\0" in encoded:
            raise ValueError("SQL must be nonempty, NUL-free and at most 65536 UTF-8 bytes")
        if isinstance(parameters, (str, bytes, bytearray)):
            raise TypeError("parameters must contain signed 64-bit integers")
        try:
            values = tuple(islice(parameters, 8193))
        except TypeError as exc:
            raise TypeError("parameters must be a sequence of signed 64-bit integers") from exc
        if len(values) > 8192:
            raise ValueError("too many parameters")
        for value in values:
            if type(value) is not int:
                raise TypeError(
                    "parameters must be signed 64-bit integers, not bool/float/text/NULL"
                )
            if not -(1 << 63) <= value < (1 << 63):
                raise OverflowError("parameter outside signed 64-bit range")
        return query, values

    def _abort(self) -> None:
        if not self._closed and not self._db.closed():
            self._db.rollback()
        else:
            self._closed = True
        self._in_transaction = False
        if self._scope:
            self._aborted = True

    def _execute(self, query: str, parameters: tuple[int, ...], explain: bool) -> Result:
        try:
            raw = self._db.execute(query, list(parameters), explain)
            self._in_transaction = self._db.in_transaction()
        except RuntimeError as exc:
            if self._db.closed():
                self._closed = True
                self._in_transaction = False
                raise
            if not explain:
                self._in_transaction = False
                if self._scope:
                    self._aborted = True
            raise SQLError(str(exc)) from exc
        try:
            return Result(
                tuple(raw.columns),
                tuple(tuple(value for value in row) for row in raw.rows),
                raw.affected,
                raw.plan,
            )
        except BaseException:
            # Native execution may already have mutated volatile state.  It is
            # unsafe to reuse the handle if detaching the response failed.
            self._close()
            raise

    def _generate(self, query: str, parameters: Sequence[int], explain: bool) -> Result:
        from .agent import (
            AgentError,
            Clarification,
            ClarificationRequired,
            Decline,
            Generation,
            GenerationRequest,
            QueryDeclined,
            QueryProposal,
            Relation,
            _bounded_texts,
        )

        config = self._agent
        if config is None:
            raise AgentError("agent configuration is required")
        if self._scope or self._in_transaction or self._db.in_transaction():
            raise AgentError("agent generation inside a transaction is unsupported")
        if type(explain) is not bool:
            raise TypeError("explain must be bool")
        query, values = self._arguments(query, parameters)
        if values:
            raise AgentError("natural-language input does not accept SQL parameters")
        if not config.disclose_schema:
            raise AgentError("explicit schema disclosure consent is required")
        context = self._db.query_context(config.relations)
        request = GenerationRequest(
            query,
            tuple(
                Relation(item["name"], tuple(item["columns"]), item["derived"])
                for item in context["relations"]
            ),
        )
        try:
            proposal = config.generator(request)
        except AgentError:
            raise
        except Exception:
            raise AgentError("query generation failed") from None
        if type(proposal) is Clarification:
            _bounded_texts(proposal.questions, nonempty=True)
            raise ClarificationRequired(proposal.questions)
        if type(proposal) is Decline:
            _bounded_texts((proposal.reason,), nonempty=True)
            raise QueryDeclined(proposal.reason)
        if type(proposal) is not QueryProposal:
            raise AgentError("generator must return a QueryProposal")
        generated, bound = self._arguments(proposal.query, proposal.parameters)
        _bounded_texts(proposal.assumptions)
        try:
            raw = self._db.execute_readonly(
                generated, bound, config.relations, context["revision"], explain
            )
        except (RuntimeError, ValueError) as exc:
            raise SQLError(str(exc)) from exc
        return Result(
            tuple(raw.columns),
            tuple(tuple(row) for row in raw.rows),
            raw.affected,
            raw.plan,
            Generation(generated, bound, proposal.assumptions),
        )

    def execute(
        self,
        query: str,
        parameters: Sequence[int] = (),
        *,
        explain: bool = False,
        agent: bool = False,
    ) -> Result:
        with self._operation():
            if self._scope and self._aborted:
                raise SQLError("transaction aborted; exit its context before further execution")
            if agent is True:
                return self._generate(query, parameters, explain)
            try:
                if type(agent) is not bool:
                    raise TypeError("agent must be bool")
                if type(explain) is not bool:
                    raise TypeError("explain must be bool")
                query, values = self._arguments(query, parameters)
                if self._scope and not explain:
                    # Let the native binder identify transaction control; never parse SQL here.
                    probe = self._execute(query, values, True)
                    if probe.plan.strip().lower() in {"begin", "commit", "rollback"}:
                        raise SQLError("transaction control belongs to the active context")
                return self._execute(query, values, explain)
            except BaseException:
                if explain is not True:
                    self._abort()
                raise

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        self._check()
        if self._scope or self._in_transaction:
            self._abort()
            raise SQLError("nested transaction is unsupported")
        with self._operation():
            self._execute("BEGIN", (), False)
        self._scope = True
        self._aborted = False
        try:
            yield self
            if self._aborted:
                raise SQLError("transaction aborted")
            self._check()
            with self._operation():
                self._execute("COMMIT", (), False)
        except BaseException:
            self._abort()
            raise
        finally:
            self._scope = False
            self._aborted = False

    def stats(self) -> dict[str, int]:
        with self._operation():
            return dict(self._db.stats())

    def checkpoint(self) -> None:
        """Checkpoint committed model state; unavailable inside a transaction."""
        with self._operation():
            if self._scope or self._in_transaction:
                raise SQLError("checkpoint inside a transaction is unsupported")
            try:
                self._db.checkpoint()
            except RuntimeError as exc:
                raise SQLError(str(exc)) from exc

    def close(self) -> None:
        if (os.getpid(), threading.get_ident()) != (self._pid, self._thread):
            raise RuntimeError("database belongs to its creating process and thread")
        if self._busy:
            raise RuntimeError("reentrant database operation is unsupported")
        self._close()

    def _close(self) -> None:
        if not self._closed:
            self._db.close()
            self._closed = True
            self._in_transaction = False

    def __enter__(self) -> Database:
        self._check()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = ["Database", "Result", "SQLError"]
