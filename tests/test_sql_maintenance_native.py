"""Compile and execute maintained SQL tests against the package headers."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MaintainedNativeTests(unittest.TestCase):
    def test_maintained_native_contract(self):
        compiler = os.environ.get("CXX") or shutil.which("c++")
        self.assertIsNotNone(compiler, "a C++17 compiler is required")
        with tempfile.TemporaryDirectory(prefix="refpot-maintained-native-") as directory:
            for source in (
                "test_sql_maintenance_native.cpp",
                "test_maintenance_foundation.cpp",
                "test_sql_maintenance_alloc.cpp",
            ):
                for sanitized in (False, True):
                    with self.subTest(source=source, sanitized=sanitized):
                        binary = Path(directory) / f"{source}-{sanitized}"
                        command = [
                            str(compiler),
                            "-std=c++17",
                            "-O1",
                            "-g",
                            "-Wall",
                            "-Wextra",
                            "-Werror",
                            "-UNDEBUG",
                        ]
                        if sanitized:
                            command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                        command += [str(ROOT / "tests" / source), "-o", str(binary)]
                        subprocess.run(
                            command, check=True, capture_output=True, text=True, timeout=120
                        )
                        env = dict(
                            os.environ,
                            ASAN_OPTIONS="detect_leaks=0",
                            UBSAN_OPTIONS="halt_on_error=1",
                        )
                        result = subprocess.run(
                            [str(binary)], env=env, capture_output=True, text=True, timeout=60
                        )
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
