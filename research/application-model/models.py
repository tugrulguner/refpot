"""Two application declarations for the same experimental relational operators."""


def source(name, width):
    return {"name": name, "op": "source", "width": width}


def mapped(name, parent, *expressions):
    return {"name": name, "op": "map", "input": parent, "exprs": list(expressions)}


def filtered(name, parent, column, cmp, value):
    return {
        "name": name,
        "op": "filter",
        "input": parent,
        "column": column,
        "cmp": cmp,
        "value": value,
    }


def joined(name, left, right, left_key, right_key, op="join"):
    return {
        "name": name,
        "op": op,
        "left": left,
        "right": right,
        "left_key": left_key,
        "right_key": right_key,
    }


def totals(prefix, owner, amounts):
    """Seed each owner with zero, so zero-usage rows remain visible."""
    return [
        mapped(prefix + "_zero", owner, ["c0"], [0]),
        {"name": prefix + "_input", "op": "union", "left": prefix + "_zero", "right": amounts},
        {
            "name": prefix + "_usage",
            "op": "group",
            "input": prefix + "_input",
            "key": 0,
            "value": 1,
        },
        joined(prefix + "_joined", owner, prefix + "_usage", 0, 0),
        mapped(prefix + "_remaining", prefix + "_joined", ["c0"], ["c1", "c3", "-"]),
        filtered(prefix + "_overdrawn", prefix + "_remaining", 1, "lt", 0),
    ]


def resource_spec():
    nodes = [
        source("resources", 2),
        source("teams", 2),
        source("reservations", 4),
        filtered("bad_capacity", "resources", 1, "lt", 0),
        filtered("bad_quota", "teams", 1, "lt", 0),
        filtered("bad_quantity", "reservations", 3, "le", 0),
        joined("missing_resource", "reservations", "resources", 1, 0, "anti"),
        joined("missing_team", "reservations", "teams", 2, 0, "anti"),
        mapped("resource_amounts", "reservations", ["c1"], ["c3"]),
        mapped("team_amounts", "reservations", ["c2"], ["c3"]),
        *totals("resource", "resources", "resource_amounts"),
        *totals("team", "teams", "team_amounts"),
        filtered("eligible_resources", "resource_remaining", 1, "gt", 0),
        filtered("eligible_teams", "team_remaining", 1, "gt", 0),
    ]
    return {
        "nodes": nodes,
        "required_empty": [
            "bad_capacity",
            "bad_quota",
            "bad_quantity",
            "missing_resource",
            "missing_team",
            "resource_overdrawn",
            "team_overdrawn",
        ],
    }


def pricing_spec():
    nodes = [
        source("customers", 2),
        source("products", 2),
        source("orders", 4),
        filtered("bad_limit", "customers", 1, "lt", 0),
        filtered("bad_price", "products", 1, "lt", 0),
        filtered("bad_quantity", "orders", 3, "le", 0),
        joined("missing_customer", "orders", "customers", 1, 0, "anti"),
        joined("missing_product", "orders", "products", 2, 0, "anti"),
        joined("priced_orders", "orders", "products", 2, 0),
        mapped("line_totals", "priced_orders", ["c0"], ["c1"], ["c3", "c5", "*"]),
        mapped("customer_amounts", "line_totals", ["c1"], ["c2"]),
        *totals("customer", "customers", "customer_amounts"),
    ]
    return {
        "nodes": nodes,
        "required_empty": [
            "bad_limit",
            "bad_price",
            "bad_quantity",
            "missing_customer",
            "missing_product",
            "customer_overdrawn",
        ],
    }


def insert(table, *row):
    return {"op": "insert", "table": table, "row": list(row)}


def update(table, *row):
    return {"op": "update", "table": table, "row": list(row)}


def delete(table, key):
    return {"op": "delete", "table": table, "key": key}
