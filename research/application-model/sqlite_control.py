"""SQLite-view control: source tables are transactional; derived views recompute on read."""

import sqlite3

from oracle import MAX_INT, MIN_INT, _graph, _int


def _checked(v):
    if not MIN_INT <= v <= MAX_INT:
        raise OverflowError("signed 64-bit arithmetic overflow")
    return v


def _add(a, b):
    return _checked(a + b)


def _sub(a, b):
    return _checked(a - b)


def _mul(a, b):
    return _checked(a * b)


class _WideSum:
    def __init__(self):
        self.total = 0

    def step(self, *values: int):
        value, mult = values  # Registered with SQLite's fixed arity of two.
        self.total += value * mult

    def finalize(self):
        return _checked(self.total)


class _CheckedCount:
    def __init__(self):
        self.total = 0

    def step(self, mult):
        self.total = _checked(self.total + mult)

    def finalize(self):
        return self.total


class SQLiteControl:
    """SQL-view baseline; no incremental materialization/performance claim is made."""

    def __init__(self, spec):
        self._nodes, self._widths, self._required = _graph(spec)
        self._epoch = 0
        self._db = sqlite3.connect(":memory:")
        self._db.create_function("checked_add", 2, _add, deterministic=True)
        self._db.create_function("checked_sub", 2, _sub, deterministic=True)
        self._db.create_function("checked_mul", 2, _mul, deterministic=True)
        self._db.create_aggregate("wide_sum", 2, _WideSum)
        self._db.create_aggregate("checked_count", 1, _CheckedCount)
        self._closed = False
        for n in self._nodes:
            self._create_relation(n)

    @property
    def epoch(self):
        return self._epoch

    def _cols(self, width):
        return [f"c{i}" for i in range(width)]

    def _select(self, name):
        return ", ".join([*self._cols(self._widths[name]), "__m"])

    def _source(self, name):
        return f'"__source${name}"'

    def _view(self, name):
        return f'"__view${name}"'

    def _create_relation(self, n):
        name, op = n["name"], n["op"]
        if op == "source":
            cols = self._cols(n["width"])
            declaration = ", ".join(
                ["c0 INTEGER PRIMARY KEY"] + [f"{c} INTEGER NOT NULL" for c in cols[1:]]
            )
            self._db.execute(f"CREATE TABLE {self._source(name)} ({declaration})")
            self._db.execute(
                f"CREATE VIEW {self._view(name)} AS SELECT {', '.join(cols)}, 1 AS __m FROM {self._source(name)}"
            )
            return
        if op == "map":
            inp = n["input"]

            def expression(expr):
                stack = []
                for t in expr:
                    if type(t) is int:
                        stack.append(str(t))
                    elif isinstance(t, str) and t.startswith("c") and t[1:].isdigit():
                        stack.append(f'"c{int(t[1:])}"')
                    else:
                        b, a = stack.pop(), stack.pop()
                        fn = {"+": "checked_add", "-": "checked_sub", "*": "checked_mul"}[t]
                        stack.append(f"{fn}({a}, {b})")
                return stack[0]

            exprs = [f"{expression(e)} AS c{i}" for i, e in enumerate(n["exprs"])]
            sql = f"CREATE VIEW {self._view(name)} AS SELECT {', '.join(exprs)}, __m FROM {self._view(inp)}"
        elif op == "filter":
            inp = n["input"]
            cmp = {"lt": "<", "le": "<=", "eq": "=", "ne": "!=", "ge": ">=", "gt": ">"}[n["cmp"]]
            sql = f"CREATE VIEW {self._view(name)} AS SELECT {self._select(inp)} FROM {self._view(inp)} WHERE c{n['column']} {cmp} {n['value']}"
        elif op in ("join", "anti"):
            left, right = n["left"], n["right"]
            if op == "join":
                left_cols = self._cols(self._widths[left])
                right_cols = self._cols(self._widths[right])
                projections = [f'l."{c}" AS "{c}"' for c in left_cols] + [
                    f'r."{c}" AS "c{len(left_cols) + i}"' for i, c in enumerate(right_cols)
                ]
                sql = (
                    f"CREATE VIEW {self._view(name)} AS SELECT {', '.join(projections)}, "
                    f"checked_mul(l.__m, r.__m) AS __m FROM {self._view(left)} l JOIN {self._view(right)} r "
                    f"ON l.c{n['left_key']}=r.c{n['right_key']}"
                )
            else:
                sql = (
                    f"CREATE VIEW {self._view(name)} AS SELECT {self._select(left)} FROM {self._view(left)} l "
                    f"WHERE NOT EXISTS (SELECT 1 FROM {self._view(right)} r WHERE l.c{n['left_key']}=r.c{n['right_key']})"
                )
        elif op == "union":
            left, right = n["left"], n["right"]
            sql = f"CREATE VIEW {self._view(name)} AS SELECT {self._select(left)} FROM {self._view(left)} UNION ALL SELECT {self._select(right)} FROM {self._view(right)}"
        else:
            inp = n["input"]
            sql = (
                f"CREATE VIEW {self._view(name)} AS SELECT c{n['key']} AS c0, "
                f"wide_sum(c{n['value']}, __m) AS c1, checked_count(__m) AS c2, 1 AS __m "
                f"FROM {self._view(inp)} GROUP BY c{n['key']}"
            )
        self._db.execute(sql)

    def _relation(self, name):
        width = self._widths[name]
        rows = self._db.execute(f"SELECT {self._select(name)} FROM {self._view(name)}").fetchall()
        totals = {}
        for raw in rows:
            row, mult = tuple(raw[:width]), raw[width]
            for x in row:
                _int(x)
            if type(mult) is not int or not 0 < mult <= MAX_INT:
                raise OverflowError("invalid bag multiplicity")
            totals[row] = _checked(totals.get(row, 0) + mult)
        return sorted(totals.items())

    def apply(self, ops):
        if self._closed:
            raise ValueError("control is closed")
        if not isinstance(ops, list):
            raise ValueError("operations must be a list")
        if self._epoch == (1 << 64) - 1:
            raise OverflowError("epoch exhausted")
        try:
            self._db.execute("BEGIN")
            sources = {n["name"] for n in self._nodes if n["op"] == "source"}
            for op in ops:
                if not isinstance(op, dict):
                    raise ValueError("operation must be a dictionary")
                kind, table = op.get("op"), op.get("table")
                if table not in sources:
                    raise ValueError("operation target must be a source")
                width = self._widths[table]
                if kind in ("insert", "update"):
                    row = op.get("row")
                    if not isinstance(row, list | tuple) or len(row) != width:
                        raise ValueError("wrong row width")
                    values = tuple(_int(x) for x in row)
                    if kind == "insert":
                        self._db.execute(
                            f"INSERT INTO {self._source(table)} VALUES ({','.join('?' for _ in values)})",
                            values,
                        )
                    else:
                        if width == 1:
                            cur = self._db.execute(
                                f"SELECT 1 FROM {self._source(table)} WHERE c0=?", values[:1]
                            )
                            if cur.fetchone() is None:
                                raise ValueError("missing update")
                        else:
                            cur = self._db.execute(
                                f"UPDATE {self._source(table)} SET {', '.join(f'c{i}=?' for i in range(1, width))} WHERE c0=?",
                                values[1:] + values[:1],
                            )
                            if cur.rowcount != 1:
                                raise ValueError("missing update")
                elif kind == "delete":
                    key = _int(op.get("key"))
                    cur = self._db.execute(f"DELETE FROM {self._source(table)} WHERE c0=?", (key,))
                    if cur.rowcount != 1:
                        raise ValueError("missing delete")
                else:
                    raise ValueError("unknown operation")
            for n in self._nodes:
                self._relation(n["name"])
            if any(self._relation(name) for name in self._required):
                raise ValueError("required relation is not empty")
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise
        self._epoch += 1

    def snapshot(self):
        if self._closed:
            raise ValueError("control is closed")
        return {
            n["name"]: [[*row, mult] for row, mult in sorted(self._relation(n["name"]))]
            for n in self._nodes
        }

    def close(self):
        if not self._closed:
            self._db.close()
            self._closed = True
