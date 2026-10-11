import random
import subprocess
import sys
from pathlib import Path

import pytest

from refpot import Database, Row


def test_crud_transactions_differential_reopen(tmp_path):
    rng = random.Random(89173)
    path = tmp_path / "state"
    expected = {}
    db = Database(path)
    try:
        for batch in range(60):
            next_state = dict(expected)
            abort = batch % 7 == 0
            try:
                with db.transaction():
                    for step in range(12):
                        key = rng.randrange(24)
                        operation = rng.choice(["insert", "delete", "update", "read"])
                        if operation == "insert":
                            value, text = rng.randrange(-100, 100), f"é{batch}:{step}"
                            if key in next_state:
                                with pytest.raises(ValueError):
                                    db.insert(key, value, text)
                            else:
                                db.insert(key, value, text)
                                next_state[key] = Row(key, value, text)
                        elif operation == "delete":
                            if key not in next_state:
                                with pytest.raises(KeyError):
                                    db.delete(key)
                            else:
                                db.delete(key)
                                del next_state[key]
                        elif operation == "update":
                            value = rng.randrange(-100, 100)
                            if key not in next_state:
                                with pytest.raises(KeyError):
                                    db.update(key, value=value)
                            else:
                                db.update(key, value=value)
                                next_state[key] = Row(key, value, next_state[key].text)
                        else:
                            if key not in next_state:
                                with pytest.raises(KeyError):
                                    db.get(key)
                            else:
                                assert db.get(key) == next_state[key]
                        assert len(db) == len(next_state)
                    if abort:
                        raise LookupError("abort batch")
            except LookupError:
                assert abort
            else:
                expected = next_state
            if batch % 5 == 0:
                db.checkpoint()
            db.close()
            db = Database(path)
            assert len(db) == len(expected)
            for key in range(24):
                if key in expected:
                    assert db.get(key) == expected[key]
                else:
                    with pytest.raises(KeyError):
                        db.get(key)
    finally:
        db.close()


def test_examples_are_repeatable(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in ["crud.py", "transactions.py"]:
        for _ in range(2):
            subprocess.run(
                [sys.executable, str(root / "examples" / name)],
                cwd=tmp_path,
                check=True,
                capture_output=True,
            )
