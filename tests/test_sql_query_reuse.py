"""Compile and run maintained-query reuse native controls in both modes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "source_name", ["sql_query_reuse.cpp", "sql_query_reuse_index.cpp", "sql_query_reuse_alloc.cpp"]
)
def test_native_query_reuse_both_modes(tmp_path, source_name):
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    assert compiler, "a C++17 compiler is required"
    source = ROOT / "tests/native" / source_name
    for sanitized in (False, True):
        exe = tmp_path / f"query-reuse-{sanitized}"
        dep = exe.with_suffix(".d")
        command = [
            compiler,
            "-std=c++17",
            "-O1",
            "-g",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-UNDEBUG",
            "-MMD",
            "-MF",
            str(dep),
        ]
        if sanitized:
            command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        command += [str(source), "-o", str(exe)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=120)
        assert built.returncode == 0, built.stdout + built.stderr
        dependencies = dep.read_text()
        assert source.name in dependencies
        assert "native/relational/sql.hpp" in dependencies
        assert "native/relational/foundation.hpp" in dependencies
        env = dict(
            os.environ,
            TMPDIR=str(tmp_path),
            ASAN_OPTIONS="detect_leaks=0",
            UBSAN_OPTIONS="halt_on_error=1",
        )
        ran = subprocess.run([str(exe)], capture_output=True, text=True, env=env, timeout=60)
        assert ran.returncode == 0, ran.stdout + ran.stderr
