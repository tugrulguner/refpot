"""Compile persistence tests against the package's actual native headers."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "source",
    [
        "test_sql_storage.cpp",
        "test_sql_persistence_native.cpp",
        "test_sql_persistence_alloc.cpp",
        "test_sql_persistence_codec.cpp",
        "test_sql_evolution_native.cpp",
        "test_sql_evolution_alloc.cpp",
        "test_sql_agent_native.cpp",
    ],
)
@pytest.mark.parametrize("sanitized", [False, True])
def test_native_persistence_contract(tmp_path, source, sanitized):
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    assert compiler, "a C++17 compiler is required"
    binary = tmp_path / "native-test"
    command = [compiler, "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror", "-UNDEBUG"]
    if sanitized:
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    command += [str(ROOT / "tests" / source), "-o", str(binary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    env = dict(
        os.environ,
        TMPDIR=str(tmp_path),
        ASAN_OPTIONS="detect_leaks=0",
        UBSAN_OPTIONS="halt_on_error=1",
    )
    result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
