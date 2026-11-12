"""Compile and execute the shared physical model adapter natively."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sql_shared_model_native():
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    assert compiler, "a C++17 compiler is required"
    with tempfile.TemporaryDirectory(prefix="refpot-shared-model-") as directory:
        for sanitized in (False, True):
            exe = Path(directory) / f"test-{sanitized}"
            dependency = exe.with_suffix(".d")
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
                str(dependency),
            ]
            if sanitized:
                command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            command += [str(ROOT / "tests/native/sql_shared_model.cpp"), "-o", str(exe)]
            built = subprocess.run(command, capture_output=True, text=True, timeout=120)
            assert built.returncode == 0, built.stdout + built.stderr
            assert "native/relational/shared_model.hpp" in dependency.read_text()
            env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0", UBSAN_OPTIONS="halt_on_error=1")
            ran = subprocess.run([str(exe)], capture_output=True, text=True, env=env, timeout=60)
            assert ran.returncode == 0, ran.stdout + ran.stderr
