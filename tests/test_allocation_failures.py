"""Allocation failures against an isolated test-only build of the real native core."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def instrumented_python(tmp_path_factory):
    work = tmp_path_factory.mktemp("allocation-build")
    build = work / "build"
    site = work / "site"
    package = site / "refpot"
    package.mkdir(parents=True)
    shutil.copy(ROOT / "src/refpot/__init__.py", package / "__init__.py")

    uv_cache = subprocess.run(
        ["uv", "cache", "dir"], check=True, capture_output=True, text=True
    ).stdout.strip()
    configs = sorted(Path(uv_cache).rglob("pybind11Config.cmake"))
    assert configs, "pybind11 CMake build dependency is absent from the local uv cache"
    pybind11_dir = configs[-1].parent

    subprocess.run(
        [
            "cmake",
            "-S",
            str(ROOT),
            "-B",
            str(build),
            f"-Dpybind11_DIR={pybind11_dir}",
            f"-DPython_EXECUTABLE={sys.executable}",
            "-DCMAKE_CXX_FLAGS=-DREFPOT_TEST_ALLOC",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(["cmake", "--build", str(build), "--config", "Release"], check=True)
    extensions = list(build.rglob("_core*.so")) + list(build.rglob("_core*.dylib"))
    assert len(extensions) == 1, extensions
    shutil.copy(extensions[0], package / extensions[0].name)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(site)
    env["REFPOT_TEST_SITE"] = str(site)
    return env


def _run_isolated(instrumented_python, script, path):
    result = subprocess.run(
        [sys.executable, "-S", "-c", script, str(path)],
        cwd=instrumented_python["REFPOT_TEST_SITE"],
        env=instrumented_python,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_commit_preparation_allocation_positions_leave_wal_unchanged(instrumented_python, tmp_path):
    _run_isolated(
        instrumented_python,
        r"""
import importlib, sys
from pathlib import Path
from refpot import Database
core=importlib.import_module('refpot._core')
p=Path(sys.argv[1]); db=Database(p); db.insert(1,10,'one'); db.insert(2,20,'two')
wal=Path(str(p)+'.wal'); before=wal.stat().st_size
failures=0; reached_success=False
for index in range(128):
 db._core.begin(); db.update(1,value=100+index); db.insert(3,30,'z'*31); db.delete(2)
 core._test_fail_allocation_after(2,index)
 try: db._core.commit()
 except MemoryError:
  failures+=1; core._test_clear_allocation_failure()
  assert wal.stat().st_size==before
  assert db.get(1).value==10 and db.get(2).value==20
  try: db.get(3)
  except KeyError: pass
  else: raise AssertionError('failed commit published insertion')
 else:
  core._test_clear_allocation_failure(); reached_success=True; break
assert failures>0 and reached_success,(failures,reached_success)
db.close()
""",
        tmp_path / "commit-sweep.db",
    )


def test_staging_and_commit_allocation_failures_preserve_state(instrumented_python, tmp_path):
    _run_isolated(
        instrumented_python,
        r"""
import importlib, os, sys
from pathlib import Path
from refpot import Database
core=importlib.import_module('refpot._core')
root=Path(os.environ['REFPOT_TEST_SITE'],'refpot').resolve()
assert Path(__import__('refpot').__file__).resolve().parent == root
assert Path(core.__file__).resolve().parent == root
assert hasattr(core, '_test_fail_phase_allocation')
p=Path(sys.argv[1]); db=Database(p); db.insert(1,10,'original'); db.checkpoint()
wal=Path(str(p)+'.wal'); before=wal.stat().st_size
db._core.begin(); db.update(1,value=12); core._test_fail_phase_allocation(1)
try: db.insert(2,20,'new')
except MemoryError: pass
else: raise AssertionError('staging allocation was not injected')
core._test_clear_allocation_failure()
assert len(db)==1 and db.get(1).value==12
try: db.get(2)
except KeyError: pass
else: raise AssertionError('failed stage became visible')
db._core.rollback(); assert wal.stat().st_size==before
db._core.begin(); db.update(1,value=11); core._test_fail_phase_allocation(2)
try: db._core.commit()
except MemoryError: pass
else: raise AssertionError('commit preparation allocation was not injected')
core._test_clear_allocation_failure()
assert db.get(1).value==10 and wal.stat().st_size==before
db.insert(3,30,'usable'); db.close()
with Database(p) as db: assert db.get(3).value==30 and db.get(1).value==10
""",
        tmp_path / "atomic.db",
    )


def test_staging_allocation_positions_are_atomic(instrumented_python, tmp_path):
    _run_isolated(
        instrumented_python,
        r"""
import importlib, os, sys
from pathlib import Path
from refpot import Database
core=importlib.import_module('refpot._core')
assert Path(core.__file__).resolve().parent == Path(os.environ['REFPOT_TEST_SITE'],'refpot').resolve()
db=Database(sys.argv[1]); db.insert(1,10,'one'); db.insert(2,20,'two')
operations=[lambda: db.insert(3,30,'y'*31), lambda: db.delete(2)]
for operation_number,operation in enumerate(operations):
 failures=0; reached_success=False
 for index in range(64):
  db._core.begin(); db.update(1,value=1000+index)
  core._test_fail_allocation_after(1,index)
  try: operation()
  except MemoryError:
   failures+=1; core._test_clear_allocation_failure()
   assert db.get(1).value==1000+index and db.get(2).value==20
   try: db.get(3)
   except KeyError: pass
   else: raise AssertionError('failed stage became visible')
   db._core.rollback()
  else:
   core._test_clear_allocation_failure(); db._core.rollback(); reached_success=True; break
 assert failures>0 and reached_success,(operation_number,failures,reached_success)
db.close()
""",
        tmp_path / "stage-sweep.db",
    )


def test_recovery_allocation_failure_releases_lock_and_recovers(instrumented_python, tmp_path):
    _run_isolated(
        instrumented_python,
        r"""
import importlib, os, sys
from pathlib import Path
from refpot import Database
core=importlib.import_module('refpot._core')
assert Path(__import__('refpot').__file__).resolve().parent == Path(os.environ['REFPOT_TEST_SITE'],'refpot').resolve()
assert Path(core.__file__).resolve().parent == Path(os.environ['REFPOT_TEST_SITE'],'refpot').resolve()
p=sys.argv[1]
with Database(p) as db: db.insert(1,10,'ack')
core._test_fail_phase_allocation(3)
try: Database(p)
except MemoryError: pass
else: raise AssertionError('recovery allocation was not injected')
core._test_clear_allocation_failure()
with Database(p) as db:
 assert db.get(1).value==10
 db.insert(2,20,'continued')
with Database(p) as db: assert db.get(1).value==10 and db.get(2).value==20
""",
        tmp_path / "recovery.db",
    )


def test_publication_after_sync_has_no_native_allocations(instrumented_python, tmp_path):
    _run_isolated(
        instrumented_python,
        r"""
import importlib, sys
from refpot import Database
core=importlib.import_module('refpot._core')
with Database(sys.argv[1]) as db:
 db.insert(1,10,'before'); db.insert(2,20,'delete-me')
 operations=[lambda: db.update(1,value=11), lambda: db.insert(3,30,'singleton'), lambda: db.delete(3)]
 for operation in operations:
  core._test_reset_post_sync_allocations(); operation()
  assert core._test_post_sync_allocations()==0,core._test_post_sync_allocations()
 db._core.begin(); db.update(1,value=12); db.insert(4,40,'transaction'); db.delete(2)
 core._test_reset_post_sync_allocations(); db._core.commit()
 assert core._test_post_sync_allocations()==0,core._test_post_sync_allocations()
 assert db.get(1).value==12 and db.get(4).value==40
 try: db.get(2)
 except KeyError: pass
 else: raise AssertionError('transaction delete not published')
""",
        tmp_path / "publication.db",
    )
