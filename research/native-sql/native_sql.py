"""Local volatile SQL preview; not the installed refpot.Database API.

SQL parsing, binding, scans and mutations execute in the native shared library.
This module handles typed arguments, ownership and detached result decoding only.
"""

import ctypes
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


class SQLError(RuntimeError):
    """A native SQL statement was rejected."""


@dataclass(frozen=True)
class Result:
    columns: tuple[str, ...]
    rows: tuple[tuple[int | None, ...], ...]
    affected: int
    plan: str


class Database:
    def __init__(self, *, library, mode="overlay"):
        if mode not in ("overlay", "modular"):
            raise ValueError("mode must be overlay or modular")
        self._lib = ctypes.CDLL(str(Path(library).resolve()))
        self._lib.rp_sql_open.argtypes = [ctypes.c_int]
        self._lib.rp_sql_open.restype = ctypes.c_void_p
        self._lib.rp_sql_close.argtypes = [ctypes.c_void_p]
        self._lib.rp_sql_close.restype = ctypes.c_int
        self._lib.rp_sql_rollback.argtypes = [ctypes.c_void_p]
        self._lib.rp_sql_rollback.restype = ctypes.c_int
        self._lib.rp_sql_free.argtypes = [ctypes.c_void_p]
        self._lib.rp_sql_free.restype = None
        self._lib.rp_sql_execute.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.c_size_t,
            ctypes.c_int,
        ]
        self._lib.rp_sql_execute.restype = ctypes.c_void_p
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._handle = self._lib.rp_sql_open(mode == "modular")
        if not self._handle:
            raise MemoryError("native database construction failed")
        self._in_transaction = False
        self._scope = False
        self._aborted = False

    def _check(self):
        if (os.getpid(), threading.get_ident()) != (self._pid, self._thread):
            raise RuntimeError("database belongs to its creating process and thread")
        if not self._handle:
            raise RuntimeError("database is closed")

    def _abort(self):
        if self._handle and self._lib.rp_sql_rollback(self._handle):
            raise RuntimeError("native rollback ownership violation")
        self._in_transaction = False
        if self._scope:
            self._aborted = True

    def execute(self, query, parameters=(), *, explain=False):
        self._check()
        if self._scope and self._aborted:
            raise SQLError("transaction aborted; exit its context before further execution")
        try:
            parameters = tuple(parameters)
            if self._scope and not explain:
                # Let the native binder identify transaction control; do not parse SQL in Python.
                inspection = self._execute(query, parameters, explain=True)
                if inspection.plan in ("begin", "commit", "rollback"):
                    raise SQLError("transaction control belongs to the active context")
            return self._execute(query, parameters, explain=explain)
        except BaseException:
            if not explain:
                self._abort()
            raise

    @contextmanager
    def transaction(self):
        self._check()
        if self._scope or self._in_transaction:
            self._abort()
            raise SQLError("nested transaction is unsupported")
        self._execute("BEGIN")
        self._scope, self._aborted = True, False
        try:
            yield self
            if self._aborted:
                raise SQLError("transaction aborted")
            self._check()
            self._execute("COMMIT")
        except BaseException:
            self._abort()
            raise
        finally:
            self._scope = False
            self._aborted = False

    def _execute(self, query, parameters=(), *, explain=False):
        self._check()
        if not isinstance(query, str):
            raise TypeError("query must be a SQL string")
        encoded = query.encode("utf-8")
        if not encoded or len(encoded) > 65536 or b"\0" in encoded:
            raise ValueError("SQL must be nonempty, NUL-free and at most 65536 bytes")
        values = tuple(parameters)
        if len(values) > 8192:
            raise ValueError("too many parameters")
        for value in values:
            if type(value) is not int:
                raise TypeError(
                    "parameters must be signed 64-bit integers, not bool/float/text/NULL"
                )
            if not -(1 << 63) <= value < (1 << 63):
                raise OverflowError("parameter outside signed 64-bit range")
        params = (ctypes.c_int64 * len(values))(*values)
        pointer = self._lib.rp_sql_execute(
            self._handle, encoded, len(encoded), params, len(values), bool(explain)
        )
        if not pointer:
            self.close()
            raise MemoryError(
                "native response unavailable; database closed to prevent uncertain reuse"
            )
        try:
            payload = json.loads(ctypes.string_at(pointer))
        except BaseException:
            self.close()
            raise
        finally:
            self._lib.rp_sql_free(pointer)
        if not payload["ok"]:
            if payload.get("fatal"):
                self.close()
                raise SQLError("native response failed after execution; volatile database closed")
            if not explain:
                self._in_transaction = False
            raise SQLError(payload["error"])
        self._in_transaction = payload["in_transaction"]
        try:
            return Result(
                tuple(payload["columns"]),
                tuple(tuple(row) for row in payload["rows"]),
                payload["affected"],
                payload["plan"],
            )
        except BaseException:
            self.close()
            raise

    def close(self):
        if not getattr(self, "_handle", None):
            return
        self._check()
        if self._lib.rp_sql_close(self._handle):
            raise RuntimeError("native handle ownership violation")
        self._handle = None

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_):
        self.close()
