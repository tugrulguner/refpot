"""RefPot's initial native CRUD slice; SQL and ORM are not implemented."""
from __future__ import annotations

from dataclasses import dataclass
from os import PathLike, getpid
import threading
from types import TracebackType

from ._core import _Database


@dataclass(frozen=True, slots=True)
class Row:
    key: int
    value: int
    text: str


def _integer(value: int, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer, not a coercible value")
    if not -(1 << 63) <= value < (1 << 63):
        raise OverflowError(f"{name} requires a signed 64-bit integer")
    return value


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("text must be str")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("text must be valid UTF-8") from exc
    if len(encoded) > 31:
        raise ValueError("text exceeds 31 UTF-8 bytes")
    return value


class _Transaction:
    def __init__(self, db: Database) -> None:
        self.db = db

    def __enter__(self) -> Database:
        self.db._check()
        self.db._core.begin()
        self.db._in_transaction = True
        return self.db

    def __exit__(self, typ: type[BaseException] | None, value: BaseException | None,
                 traceback: TracebackType | None) -> bool:
        self.db._check()
        try:
            if typ is None:
                self.db._core.commit()
            else:
                self.db._core.rollback()
        finally:
            self.db._in_transaction = False
        return False


class Database:
    """Single-owner, thread-affine native database at a file path.

    The parent directory must exist. One owner holds an exclusive process lock;
    this is not a concurrent-reader or multiwriter API. This initial format is
    separate from the benchmark prototype and has no qualified speed claim.
    """
    def __init__(self, path: str | PathLike[str]) -> None:
        self._owner = threading.get_ident()
        self._pid = getpid()
        self._closed = False
        self._in_transaction = False
        self._core = _Database(str(path))

    def _check(self) -> None:
        if getpid() != self._pid or threading.get_ident() != self._owner:
            raise RuntimeError("database must be used by its owning thread")
        if self._closed:
            raise RuntimeError("database is closed")

    def insert(self, key: int, value: int, text: str = "") -> None:
        self._check()
        self._core.insert(_integer(key, "key"), _integer(value, "value"), _text(text))

    def get(self, key: int) -> Row:
        self._check()
        row = self._core.get(_integer(key, "key"))
        return Row(row.key, row.value, row.text)

    def update(self, key: int, *, value: int | None = None, text: str | None = None) -> None:
        self._check()
        self._core.update(_integer(key, "key"),
                          _integer(value, "value") if value is not None else None,
                          _text(text) if text is not None else None)

    def delete(self, key: int) -> None:
        self._check()
        self._core.delete(_integer(key, "key"))

    def __len__(self) -> int:
        self._check()
        return self._core.size()

    def transaction(self) -> _Transaction:
        self._check()
        return _Transaction(self)

    def checkpoint(self) -> None:
        self._check()
        if self._in_transaction:
            raise RuntimeError("checkpoint during transaction")
        self._core.checkpoint()

    def close(self) -> None:
        if getpid() != self._pid or threading.get_ident() != self._owner:
            raise RuntimeError("database must be closed by its owning thread")
        if not self._closed:
            self._core.close()
            self._closed = True
            self._in_transaction = False

    def __enter__(self) -> Database:
        self._check()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = ["Database", "Row"]
