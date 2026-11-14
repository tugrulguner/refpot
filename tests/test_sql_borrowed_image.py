import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_borrowed_image_codec_matches_materialized_image(tmp_path):
    source = ROOT / "tests/native/sql_borrowed_image.cpp"
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    assert compiler
    for sanitized in (False, True):
        binary = tmp_path / ("borrowed-image-san" if sanitized else "borrowed-image")
        command = [
            compiler,
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-I",
            str(ROOT / "native"),
        ]
        if sanitized:
            command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        command += [str(source), "-o", str(binary)]
        compiled = subprocess.run(command, text=True, capture_output=True, timeout=120)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        env = dict(
            os.environ,
            TMPDIR=str(tmp_path),
            ASAN_OPTIONS="detect_leaks=0",
            UBSAN_OPTIONS="halt_on_error=1",
        )
        completed = subprocess.run(
            [str(binary)], text=True, capture_output=True, env=env, timeout=60
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "borrowed image bytes=" in completed.stdout
