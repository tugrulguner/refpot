"""Real append faults and frame-cut recovery qualification for ALTER VIEW."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import refpot.sql

SHIM = Path(__file__).parent / "native" / "io_faults.c"
PACKAGE_ORIGIN = str(Path(refpot.sql.__file__).resolve())


@pytest.fixture(scope="module")
def shim(tmp_path_factory):
    if sys.platform not in ("darwin", "linux"):
        pytest.skip("syscall interposition requires macOS/Linux")
    out = tmp_path_factory.mktemp("sql-evolution-faults") / (
        "fault.dylib" if sys.platform == "darwin" else "fault.so"
    )
    command = [
        "cc",
        "-dynamiclib" if sys.platform == "darwin" else "-shared",
        "-fPIC",
        "-Wall",
        "-Wextra",
        "-Werror",
        str(SHIM),
        "-o",
        str(out),
    ]
    if sys.platform == "linux":
        command.append("-ldl")
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return out


SEED = r"""
from refpot.sql import Database
import os, sys
assert str(__import__('refpot.sql', fromlist=['Database']).__file__) == sys.argv[2]
d = Database(sys.argv[1], mode=os.environ.get("REFPOT_TEST_MODE", "overlay"))
d.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
d.execute("CREATE MATERIALIZED VIEW base AS SELECT id, value FROM source")
d.execute("CREATE MATERIALIZED VIEW totals AS SELECT id, value FROM base")
d.execute("CREATE MATERIALIZED VIEW joined AS SELECT b.id, t.value FROM base AS b JOIN totals AS t ON b.id = t.id")
d.execute("CREATE TABLE empty_source (id INTEGER PRIMARY KEY)")
d.execute("CREATE ASSERTION empty_stays_empty CHECK (NOT EXISTS (SELECT * FROM empty_source))")
d.execute("INSERT INTO source VALUES (1, 10)")
d.execute("INSERT INTO source VALUES (2, 20)")
assert d.execute("SELECT * FROM totals ORDER BY id").rows == ((1, 10), (2, 20))
"""

VERIFY = r"""
from refpot.sql import Database, SQLError
import os, sys
p, origin, expected = sys.argv[1:]
assert str(__import__('refpot.sql', fromlist=['Database']).__file__) == origin
mode = os.environ.get('REFPOT_TEST_MODE', 'overlay')
d = Database(p, mode=mode)
old_rows = ((1, 10), (2, 20))
new_rows = ((1, 1), (2, 2))
actual = tuple(d.execute(f"SELECT * FROM {name} ORDER BY id").rows for name in ('base', 'totals', 'joined'))
old, new = (old_rows,) * 3, (new_rows,) * 3
assert actual in ({'old': [old], 'new': [new], 'either': [old, new]}[expected]), actual
is_new = actual == new
assert d.execute("SELECT * FROM source ORDER BY id").rows == old_rows
assert d.execute("SELECT * FROM empty_source").rows == ()
try:
    d.execute("INSERT INTO empty_source VALUES (1)")
except SQLError:
    pass
else:
    raise AssertionError('assertion was lost')
d.execute("INSERT INTO source VALUES (3, 5)")
continued = (new_rows if is_new else old_rows) + ((3, 3 if is_new else 5),)
assert all(d.execute(f"SELECT * FROM {name} ORDER BY id").rows == continued for name in ('base', 'totals', 'joined'))
d.checkpoint()
d.close()
with Database(p, mode=mode) as d:
    assert d.execute("SELECT * FROM source ORDER BY id").rows == ((1,10),(2,20),(3,5))
    assert all(d.execute(f"SELECT * FROM {name} ORDER BY id").rows == continued for name in ('base', 'totals', 'joined'))
"""


def clean_env(mode):
    env = os.environ.copy()
    for key in (
        "DYLD_INSERT_LIBRARIES",
        "LD_PRELOAD",
        "REFPOT_FAULT_PATH",
        "REFPOT_FAULT_CALL",
        "REFPOT_FAULT_SENTINEL",
    ):
        env.pop(key, None)
    env["REFPOT_TEST_MODE"] = mode
    return env


def run_child(script, args, env, cwd):
    return subprocess.run(
        [sys.executable, "-c", script, *map(str, args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )


@pytest.mark.parametrize("call", ["write", "fsync"])
@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_alter_interposed_io_failure_poison_and_reopen_whole_model(tmp_path, shim, call, mode):
    dbpath, sentinel = tmp_path / "model.rpsql", tmp_path / "fired"
    script = (
        SEED
        + r"""
import os, sys
os.environ['REFPOT_FAULT_PATH'] = sys.argv[3]
os.environ['REFPOT_FAULT_CALL'] = sys.argv[4]
try:
    d.execute("ALTER MATERIALIZED VIEW base AS SELECT id, id AS value FROM source")
except Exception:
    pass
else:
    raise AssertionError('faulted ALTER succeeded')
try:
    d.execute("SELECT * FROM source")
except Exception:
    pass
else:
    raise AssertionError('uncertain owner remained usable')
d.close()
"""
    )
    env = clean_env(mode)
    env["REFPOT_FAULT_SENTINEL"] = str(sentinel)
    env["DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"] = str(shim)
    result = run_child(script, [dbpath, PACKAGE_ORIGIN, str(dbpath) + ".wal", call], env, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel.read_text().splitlines() == [call], (
        "fault did not intercept the exact WAL target"
    )
    verify = run_child(VERIFY, [dbpath, PACKAGE_ORIGIN, "either"], clean_env(mode), tmp_path)
    assert verify.returncode == 0, (
        "recovery was not one complete old/new model: " + verify.stdout + verify.stderr
    )


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_alter_acknowledged_migration_survives_immediate_process_exit(tmp_path, mode):
    dbpath = tmp_path / "model.rpsql"
    script = (
        SEED
        + r"""
import os
assert d.execute("ALTER MATERIALIZED VIEW base AS SELECT id, id AS value FROM source").rows == ()
os._exit(77)
"""
    )
    result = run_child(script, [dbpath, PACKAGE_ORIGIN], clean_env(mode), tmp_path)
    assert result.returncode == 77, result.stdout + result.stderr
    reopened = run_child(VERIFY, [dbpath, PACKAGE_ORIGIN, "new"], clean_env(mode), tmp_path)
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr


@pytest.mark.parametrize("mode", ["overlay", "modular"])
def test_alter_truncated_migration_frame_prefixes_recover_complete_model(tmp_path, mode):
    dbpath = tmp_path / "model.rpsql"
    initial = run_child(
        SEED + "\nd.checkpoint()\nd.close()\n", [dbpath, PACKAGE_ORIGIN], clean_env(mode), tmp_path
    )
    assert initial.returncode == 0, initial.stdout + initial.stderr
    baseline = (tmp_path / "model.rpsql.wal").read_bytes()
    snapshot = dbpath.read_bytes()
    altered = run_child(
        r"""
from refpot.sql import Database
import sys
with Database(sys.argv[1]) as d:
    d.execute("ALTER MATERIALIZED VIEW base AS SELECT id, id AS value FROM source")
""",
        [dbpath],
        clean_env(mode),
        tmp_path,
    )
    assert altered.returncode == 0, altered.stdout + altered.stderr
    complete = (tmp_path / "model.rpsql.wal").read_bytes()
    assert len(complete) > len(baseline)
    # Cover every framing byte plus evenly spaced payload cuts and both frontiers.
    # Existing framing tests cover full byte-prefix sweeps; this verifies migration
    # semantics without spawning thousands of Python processes in every wheel lane.
    delta = len(complete) - len(baseline)
    offsets = sorted(
        set(range(min(64, delta)))
        | set(range(max(0, delta - 64), delta + 1))
        | {i * delta // 32 for i in range(33)}
    )
    for offset in offsets:
        dbpath.write_bytes(snapshot)
        (tmp_path / "model.rpsql.wal").write_bytes(complete[: len(baseline) + offset])
        expected = "new" if offset == delta else "either"
        recovered = run_child(VERIFY, [dbpath, PACKAGE_ORIGIN, expected], clean_env(mode), tmp_path)
        assert recovered.returncode == 0, (
            f"cut {offset}: incomplete recovered model\n{recovered.stderr}"
        )
