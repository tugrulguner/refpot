"""Frozen, provider-free inputs; shared by independent controls and both native modes."""

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/application-model"))
from models import delete, insert, pricing_spec, resource_spec, update  # noqa: E402

DOMAINS = ("resource", "pricing")
SIZES = (32, 256)
SCENARIOS = ("inspection", "cancel", "sparse", "dense", "parent")


def fixture(domain, size):
    if domain not in DOMAINS:
        raise ValueError("unknown domain")
    owners = 8
    if domain == "resource":
        spec = resource_spec()
        initial = [insert("resources", k, 1000000) for k in range(owners)]
        initial += [insert("teams", k, 1000000) for k in range(owners)]
        table = "reservations"
    else:
        spec = pricing_spec()
        initial = [insert("customers", k, 1000000) for k in range(owners)]
        initial += [insert("products", k, 3) for k in range(owners)]
        table = "orders"
    rows = [[k, k % owners, (k // owners) % owners, 2] for k in range(size)]
    initial += [insert(table, *row) for row in rows]
    return spec, initial, table, rows


def scenario(domain, size, name):
    spec, initial, table, rows = fixture(domain, size)
    if name == "inspection":
        batch = None
    elif name == "cancel":
        batch = [update(table, *rows[0][:-1], 3), update(table, *rows[0])]
    elif name == "sparse":
        batch = [update(table, *rows[0][:-1], 3)]
    elif name == "dense":
        batch = [update(table, *row[:-1], 3) for row in rows]
    elif name == "parent":
        parent, value = ("resources", 999999) if domain == "resource" else ("products", 4)
        batch = [update(parent, k, value) for k in range(8)]
    else:
        raise ValueError("unknown scenario")
    return spec, initial, batch


def sequence(domain, seed):
    spec, initial, table, _ = fixture(domain, 24)
    rng = random.Random(seed)
    batches = []
    for _ in range(80):
        ops = []
        for _ in range(rng.randrange(1, 4)):
            key = rng.randrange(40)
            kind = rng.choice(("insert", "update", "delete", "update", "parent"))
            if kind == "delete":
                ops.append(delete(table, key))
            elif kind == "parent":
                parent = "resources" if domain == "resource" else "products"
                ops.append(update(parent, rng.randrange(8), rng.choice((-1, 0, 4, 1000))))
            else:
                row = [key, rng.randrange(9), rng.randrange(9), rng.choice((-1, 0, 1, 2, 10))]
                ops.append((insert if kind == "insert" else update)(table, *row))
        batches.append(ops)
    return spec, initial, batches
