"""Independent, full-recomputation reference model for the declarative graph."""

import re
from collections import Counter
from copy import deepcopy

MIN_INT = -(1 << 63)
MAX_INT = (1 << 63) - 1
_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_CMPS = {
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "ge": lambda a, b: a >= b,
    "gt": lambda a, b: a > b,
}


def _int(value):
    if type(value) is not int or not MIN_INT <= value <= MAX_INT:
        raise ValueError("expected signed 64-bit integer")
    return value


def _checked(value):
    if not MIN_INT <= value <= MAX_INT:
        raise OverflowError("signed 64-bit arithmetic overflow")
    return value


def _graph(spec):
    if (
        not isinstance(spec, dict)
        or not isinstance(spec.get("nodes"), list)
        or not isinstance(spec.get("required_empty", []), list)
    ):
        raise ValueError("invalid graph specification")
    nodes, widths = [], {}
    for raw in spec["nodes"]:
        if not isinstance(raw, dict):
            raise ValueError("definition must be a dictionary")
        n = deepcopy(raw)
        name, op = n.get("name"), n.get("op")
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name in widths:
            raise ValueError("invalid or duplicate relation name")

        def parent(key, definition=n):
            p = definition.get(key)
            if p not in widths:
                raise ValueError("parents must refer to preceding relations")
            return p

        if op == "source":
            w = n.get("width")
            if type(w) is not int or w <= 0:
                raise ValueError("source width must be positive")
        elif op == "map":
            p = parent("input")
            exprs = n.get("exprs")
            if not isinstance(exprs, list) or not exprs:
                raise ValueError("map needs expressions")
            for expr in exprs:
                if not isinstance(expr, list) or not expr:
                    raise ValueError("invalid postfix expression")
                depth = 0
                for token in expr:
                    if type(token) is int:
                        _int(token)
                        depth += 1
                    elif isinstance(token, str) and token.startswith("c") and token[1:].isdigit():
                        if int(token[1:]) >= widths[p]:
                            raise ValueError("map column out of range")
                        depth += 1
                    elif token in ("+", "-", "*"):
                        if depth < 2:
                            raise ValueError("invalid postfix expression")
                        depth -= 1
                    else:
                        raise ValueError("invalid postfix token")
                if depth != 1:
                    raise ValueError("expression must leave one value")
            w = len(exprs)
        elif op == "filter":
            p = parent("input")
            col = n.get("column")
            if type(col) is not int or not 0 <= col < widths[p] or n.get("cmp") not in _CMPS:
                raise ValueError("invalid filter")
            _int(n.get("value"))
            w = widths[p]
        elif op in ("join", "anti"):
            left, right = parent("left"), parent("right")
            for k, p in (("left_key", left), ("right_key", right)):
                c = n.get(k)
                if type(c) is not int or not 0 <= c < widths[p]:
                    raise ValueError("key column out of range")
            w = widths[left] + widths[right] if op == "join" else widths[left]
        elif op == "group":
            p = parent("input")
            for k in ("key", "value"):
                c = n.get(k)
                if type(c) is not int or not 0 <= c < widths[p]:
                    raise ValueError("group column out of range")
            w = 3
        elif op == "union":
            left, right = parent("left"), parent("right")
            if widths[left] != widths[right]:
                raise ValueError("union widths differ")
            w = widths[left]
        else:
            raise ValueError("unknown relation operation")
        widths[name] = w
        nodes.append(n)
    required = spec.get("required_empty", [])
    if len(set(required)) != len(required) or any(name not in widths for name in required):
        raise ValueError("invalid required_empty relation")
    return nodes, widths, tuple(required)


def _eval_expr(expr, row):
    stack = []
    for token in expr:
        if type(token) is int:
            stack.append(token)
        elif isinstance(token, str) and token.startswith("c") and token[1:].isdigit():
            stack.append(row[int(token[1:])])
        else:
            b, a = stack.pop(), stack.pop()
            stack.append(_checked(a + b if token == "+" else a - b if token == "-" else a * b))
    return stack[0]


class Oracle:
    """Python-int, whole-graph recomputation control; intentionally not incremental."""

    def __init__(self, spec):
        self._nodes, self._widths, self._required = _graph(spec)
        self._sources = {n["name"]: {} for n in self._nodes if n["op"] == "source"}
        self._epoch = 0
        self._state = {name: Counter() for name in self._widths}
        self._recompute(self._sources)

    @property
    def epoch(self):
        return self._epoch

    def close(self):
        pass

    def _recompute(self, sources):
        state = {}
        for n in self._nodes:
            name, op = n["name"], n["op"]
            if op == "source":
                state[name] = Counter({row: 1 for row in sources[name].values()})
                continue
            out = Counter()
            if op == "map":
                for row, mult in state[n["input"]].items():
                    out[tuple(_eval_expr(e, row) for e in n["exprs"])] += mult
            elif op == "filter":
                test = _CMPS[n["cmp"]]
                for row, mult in state[n["input"]].items():
                    if test(row[n["column"]], n["value"]):
                        out[row] += mult
            elif op == "union":
                out.update(state[n["left"]])
                out.update(state[n["right"]])
            elif op == "join":
                r_index = {}
                for r, rm in state[n["right"]].items():
                    r_index.setdefault(r[n["right_key"]], []).append((r, rm))
                for left_row, lm in state[n["left"]].items():
                    for r, rm in r_index.get(left_row[n["left_key"]], []):
                        out[left_row + r] += _checked(lm * rm)
            elif op == "anti":
                keys = {r[n["right_key"]] for r in state[n["right"]]}
                for row, mult in state[n["left"]].items():
                    if row[n["left_key"]] not in keys:
                        out[row] += mult
            elif op == "group":
                groups = {}
                for row, mult in state[n["input"]].items():
                    key = row[n["key"]]
                    total, count = groups.get(key, (0, 0))
                    groups[key] = (total + row[n["value"]] * mult, _checked(count + mult))
                for key, (total, count) in groups.items():
                    out[(key, _checked(total), count)] = 1
            for row, mult in out.items():
                if type(mult) is not int or not 0 < mult <= MAX_INT:
                    raise OverflowError("invalid bag multiplicity")
                for value in row:
                    _int(value)
            state[name] = out
        return state

    def apply(self, ops):
        if not isinstance(ops, list):
            raise ValueError("operations must be a list")
        if self._epoch == (1 << 64) - 1:
            raise OverflowError("epoch exhausted")
        candidate = {t: dict(rows) for t, rows in self._sources.items()}
        for op in ops:
            if not isinstance(op, dict):
                raise ValueError("operation must be a dictionary")
            kind, table = op.get("op"), op.get("table")
            if table not in candidate:
                raise ValueError("operation target must be a source")
            rows = candidate[table]
            if kind in ("insert", "update"):
                row = op.get("row")
                if not isinstance(row, list | tuple) or len(row) != self._widths[table]:
                    raise ValueError("wrong row width")
                row = tuple(_int(x) for x in row)
                key = row[0]
                if kind == "insert" and key in rows:
                    raise ValueError("duplicate insert")
                if kind == "update" and key not in rows:
                    raise ValueError("missing update")
                rows[key] = row
            elif kind == "delete":
                key = _int(op.get("key"))
                if key not in rows:
                    raise ValueError("missing delete")
                del rows[key]
            else:
                raise ValueError("unknown operation")
        new_state = self._recompute(candidate)
        if any(new_state[name] for name in self._required):
            raise ValueError("required relation is not empty")
        self._sources, self._state = candidate, new_state
        self._epoch += 1

    def snapshot(self):
        return {
            name: [[*row, mult] for row, mult in sorted(rows.items())]
            for name, rows in self._state.items()
        }
