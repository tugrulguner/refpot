"""Subprocess-only SQL persistence faults; no production hooks or power-loss claim."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import refpot.sql

SHIM = Path(__file__).parent / "native" / "io_faults.c"


@pytest.fixture(scope="module")
def shim(tmp_path_factory):
    if sys.platform not in ("darwin", "linux"):
        pytest.skip("syscall interposition requires macOS/Linux")
    directory = tmp_path_factory.mktemp("sql-native-faults")
    out = directory / ("fault.dylib" if sys.platform == "darwin" else "fault.so")
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


# The parent import establishes the package selected by pytest (including an
# installed consumer). Children run outside the checkout and must load that same
# package tree rather than accidentally finding a source checkout on sys.path.
PACKAGE_ORIGIN = str(Path(refpot.sql.__file__).resolve())

SEED = r"""
from refpot.sql import Database
import sys
assert str(__import__('refpot.sql', fromlist=['Database']).__file__) == sys.argv[2], (
    __import__('refpot.sql', fromlist=['Database']).__file__, sys.argv[2]
)
d = Database(sys.argv[1])
d.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY)")
d.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)")
d.execute("CREATE MATERIALIZED VIEW booked AS SELECT resource, COUNT(*) AS n FROM reservations GROUP BY resource")
d.execute("CREATE MATERIALIZED VIEW missing AS SELECT r.id, r.resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM resources AS s WHERE s.id = r.resource)")
d.execute("CREATE ASSERTION resource_exists CHECK (NOT EXISTS (SELECT * FROM missing))")
d.execute("INSERT INTO resources VALUES (1)")
d.execute("INSERT INTO reservations VALUES (1, 1)")
assert d.execute("SELECT * FROM booked").rows == ((1, 1),)
assert d.execute("SELECT * FROM missing").rows == ()
"""

VERIFY_PREFIX_AND_CONTINUE = r"""
from refpot.sql import Database
import sys
assert str(__import__('refpot.sql', fromlist=['Database']).__file__) == sys.argv[2], (
    __import__('refpot.sql', fromlist=['Database']).__file__, sys.argv[2]
)
p = sys.argv[1]
with Database(p) as d:
    assert d.execute("SELECT * FROM resources").rows == ((1,),)
    rows = d.execute("SELECT * FROM reservations ORDER BY id").rows
    allowed = {
        'prefix': (((1, 1),),),
        'committed': (((1, 1), (2, 1), (3, 1)),),
        'uncertain': (((1, 1),), ((1, 1), (2, 1), (3, 1))),
    }[sys.argv[3]]
    assert rows in allowed, rows
    expected = len(rows)
    assert d.execute("SELECT * FROM booked").rows == ((1, expected),)
    assert d.execute("SELECT * FROM missing").rows == ()
    try:
        with d.transaction():
            d.execute("DELETE FROM resources")
    except Exception:
        pass
    else:
        raise AssertionError("recovered assertion was not enforced")
    d.execute("INSERT INTO reservations VALUES (4, 1)")
with Database(p) as d:
    assert d.execute("SELECT * FROM reservations ORDER BY id").rows == (*rows, (4, 1))
    assert d.execute("SELECT * FROM resources").rows == ((1,),)
    assert d.execute("SELECT * FROM booked").rows == ((1, expected + 1),)
    assert d.execute("SELECT * FROM missing").rows == ()
"""


@pytest.mark.parametrize(
    "call,target,action",
    [
        ("write", ".wal", "mutation"),
        ("fsync", ".wal", "mutation"),
        ("fsync", ".tmp", "checkpoint"),
        ("rename", ".tmp", "checkpoint"),
        ("fsync", "directory", "checkpoint"),
        ("ftruncate", ".wal", "checkpoint"),
        ("fsync", ".wal", "checkpoint"),
    ],
)
def test_sql_fault_poison_prefix_recovery_and_continued_writes(
    tmp_path, shim, call, target, action
):
    dbpath = tmp_path / "model.rpsql"
    sentinel = tmp_path / "fired"
    faultpath = str(tmp_path) if target == "directory" else str(dbpath) + target
    mutate = (
        "with d.transaction():\n"
        '    d.execute("INSERT INTO reservations VALUES (2, 1)")\n'
        '    d.execute("INSERT INTO reservations VALUES (3, 1)")'
    )
    operation = mutate if action == "mutation" else "d.checkpoint()"
    script = (
        SEED
        + f"""
import os
# Arm only after schema, derived state and the acknowledged prefix exist.
os.environ['REFPOT_FAULT_PATH'] = sys.argv[3]
os.environ['REFPOT_FAULT_CALL'] = sys.argv[4]
try:
    {operation.replace(chr(10), chr(10) + "    ")}
except Exception:
    pass
else:
    raise AssertionError('faulted SQL operation unexpectedly succeeded')
try:
    d.execute("SELECT * FROM resources")
except Exception:
    pass
else:
    raise AssertionError('uncertain SQL owner remained usable')
d.close()
"""
    )
    env = os.environ.copy()
    for name in ("REFPOT_FAULT_PATH", "REFPOT_FAULT_CALL"):
        env.pop(name, None)
    env["REFPOT_FAULT_SENTINEL"] = str(sentinel)
    env["DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"] = str(shim)
    result = subprocess.run(
        [sys.executable, "-c", script, str(dbpath), PACKAGE_ORIGIN, faultpath, call],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel.exists(), "filesystem interposer did not fire"
    assert call in sentinel.read_text().splitlines()
    recovery_outcome = "uncertain" if action == "mutation" else "prefix"

    clean_env = os.environ.copy()
    for name in (
        "DYLD_INSERT_LIBRARIES",
        "LD_PRELOAD",
        "REFPOT_FAULT_PATH",
        "REFPOT_FAULT_CALL",
        "REFPOT_FAULT_SENTINEL",
    ):
        clean_env.pop(name, None)
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            VERIFY_PREFIX_AND_CONTINUE,
            str(dbpath),
            PACKAGE_ORIGIN,
            recovery_outcome,
        ],
        cwd=tmp_path,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr


def test_sql_interrupted_short_append_preserves_acknowledged_prefix(tmp_path):
    """RLIMIT_FSIZE creates a genuine short/failed append without a fake result."""
    recovery_outcome = "prefix"
    if sys.platform == "win32":
        pytest.skip("RLIMIT_FSIZE is POSIX-only")
    dbpath = tmp_path / "model.rpsql"
    script = (
        SEED
        + r"""
import os, resource, signal
wal = sys.argv[3]
size = os.path.getsize(wal)
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (size + 12, size + 12))
try:
    with d.transaction():
        d.execute("INSERT INTO reservations VALUES (2, 1)")
        d.execute("INSERT INTO reservations VALUES (3, 1)")
except Exception:
    pass
else:
    raise AssertionError("limited append unexpectedly succeeded")
assert os.path.getsize(wal) == size + 12, "short append was not exercised"
try:
    d.execute("SELECT * FROM resources")
except Exception:
    pass
else:
    raise AssertionError("uncertain SQL owner remained usable")
d.close()
"""
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(dbpath), PACKAGE_ORIGIN, str(dbpath) + ".wal"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            VERIFY_PREFIX_AND_CONTINUE,
            str(dbpath),
            PACKAGE_ORIGIN,
            recovery_outcome,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr


def test_sql_process_exit_keeps_acknowledged_derived_state_and_recovers(tmp_path):
    """Abrupt process exit after an acknowledged transaction is not power-loss proof."""
    recovery_outcome = "committed"
    dbpath = tmp_path / "model.rpsql"
    script = (
        SEED
        + r"""
import os
with d.transaction():
    d.execute("INSERT INTO reservations VALUES (2, 1)")
    d.execute("INSERT INTO reservations VALUES (3, 1)")
os._exit(77)
"""
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(dbpath), PACKAGE_ORIGIN],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 77, result.stdout + result.stderr
    clean_env = os.environ.copy()
    for name in ("DYLD_INSERT_LIBRARIES", "LD_PRELOAD", "REFPOT_FAULT_PATH", "REFPOT_FAULT_CALL"):
        clean_env.pop(name, None)
    reopened = subprocess.run(
        [
            sys.executable,
            "-c",
            VERIFY_PREFIX_AND_CONTINUE,
            str(dbpath),
            PACKAGE_ORIGIN,
            recovery_outcome,
        ],
        cwd=tmp_path,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert reopened.returncode == 0, reopened.stdout + reopened.stderr
