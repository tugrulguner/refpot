"""Experimental native model transport; not the installed refpot API."""

import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value):
        raise ValueError("expected a lowercase relation name")
    return value


def _integer(value):
    if type(value) is not int or not -(1 << 63) <= value < (1 << 63):
        raise ValueError("expected a signed-64-bit integer (not bool)")
    return str(value)


def _index(value):
    if type(value) is not int or not 0 <= value <= 4096:
        raise ValueError("expected a bounded nonnegative index")
    return str(value)


def _expression(tokens):
    result = []
    for token in tokens:
        if type(token) is int:
            result.append(_integer(token))
        elif isinstance(token, str) and (
            token in {"+", "-", "*"} or re.fullmatch(r"c[0-9]+", token)
        ):
            result.append(token)
        else:
            raise ValueError("invalid expression token")
    return [_index(len(result)), *result]


def definition_commands(spec):
    if len(spec["nodes"]) > 4096:
        raise ValueError("too many relation definitions")
    commands = []
    for node in spec["nodes"]:
        op = node["op"]
        parts = ["DEF", op, _name(node["name"])]
        if op == "source":
            parts += [_index(node["width"])]
        elif op == "map":
            parts += [_name(node["input"]), _index(len(node["exprs"]))]
            for expr in node["exprs"]:
                parts += _expression(expr)
        elif op == "filter":
            cmp = node["cmp"]
            if cmp not in {"lt", "le", "eq", "ne", "ge", "gt"}:
                raise ValueError("invalid comparison")
            parts += [_name(node["input"]), _index(node["column"]), cmp, _integer(node["value"])]
        elif op in {"join", "anti"}:
            parts += [
                _name(node["left"]),
                _name(node["right"]),
                _index(node["left_key"]),
                _index(node["right_key"]),
            ]
        elif op == "group":
            parts += [_name(node["input"]), _index(node["key"]), _index(node["value"])]
        elif op == "union":
            parts += [_name(node["left"]), _name(node["right"])]
        else:
            raise ValueError("unknown relation operator")
        commands.append(" ".join(parts))
    required = spec.get("required_empty", [])
    commands.append(" ".join(["SEAL", _index(len(required)), *map(_name, required)]))
    return commands


def build_driver(destination, *, sanitize=False):
    """Compile the standalone C++17 driver; does not install or alter a package."""
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("a C++17 compiler is required for this research example")
    root = Path(__file__).resolve().parents[2]
    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
    if sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    subprocess.run(
        [compiler, *flags, str(root / "native/model/driver.cpp"), "-o", str(target)],
        check=True,
        timeout=120,
    )
    return target


def mutation_command(op):
    kind = op["op"]
    if kind not in {"insert", "update", "delete"}:
        raise ValueError("unknown mutation")
    parts = [kind.upper(), _name(op["table"])]
    if kind == "delete":
        parts.append(_integer(op["key"]))
    else:
        row = op["row"]
        parts += [_index(len(row)), *map(_integer, row)]
    return " ".join(parts)


class ModelError(ValueError):
    """Native model rejected a definition or complete transaction."""


class NativeModel:
    """Process-local research driver. All reads expose committed state only."""

    def __init__(self, binary, spec):
        commands = definition_commands(spec)
        self._batching = False
        self._closed = False
        self._stderr = tempfile.TemporaryFile(mode="w+t")  # noqa: SIM115 - owned until close()
        try:
            self._process = subprocess.Popen(
                [str(binary)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                text=True,
                bufsize=1,
            )
        except BaseException:
            self._stderr.close()
            raise
        try:
            for command in commands:
                self.request(command)
        except BaseException:
            self.close()
            raise

    def request(self, command):
        if self._closed:
            raise RuntimeError("model is closed")
        if "\n" in command or "\r" in command:
            raise ValueError("one command per request")
        process = self._process
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(command + "\n")
        process.stdin.flush()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(timeout=30):
                self.close()
                raise TimeoutError("native model did not respond")
        line = process.stdout.readline()
        if not line:
            self._stderr.seek(0)
            detail = self._stderr.read()
            self.close()
            raise RuntimeError("native model terminated: " + detail)
        result = json.loads(line)
        if not result["ok"]:
            raise ModelError(result["error"])
        return result

    def apply(self, ops):
        if self._batching:
            raise RuntimeError("cannot apply inside a buffered transaction")
        if len(ops) > 10000:
            raise ValueError("transaction too large")
        commands = [mutation_command(op) for op in ops]
        self.request("BEGIN")
        try:
            for command in commands:
                self.request(command)
            self.request("COMMIT")
        except BaseException:
            with suppress(ModelError, RuntimeError, BrokenPipeError):
                self.request("ROLLBACK")
            raise

    def snapshot(self):
        return self.request("SNAPSHOT")["tables"]

    @property
    def epoch(self):
        return self.request("SNAPSHOT")["epoch"]

    @property
    def stats(self):
        return self.request("SNAPSHOT")["stats"]

    @contextmanager
    def transaction(self):
        if self._batching or self._closed:
            raise RuntimeError("model closed or nested transaction")
        self._batching = True
        batch = Batch()
        try:
            yield batch
        except BaseException:
            raise
        else:
            self._batching = False
            self.apply(batch.ops)
        finally:
            batch.closed = True
            self._batching = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        process = self._process
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        self._stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Batch:
    def __init__(self):
        self.ops = []
        self.closed = False

    def _append(self, op):
        if self.closed:
            raise RuntimeError("transaction is closed")
        mutation_command(op)
        self.ops.append(op)

    def insert(self, table, *row):
        self._append({"op": "insert", "table": table, "row": list(row)})

    def update(self, table, *row):
        self._append({"op": "update", "table": table, "row": list(row)})

    def delete(self, table, key):
        self._append({"op": "delete", "table": table, "key": key})
