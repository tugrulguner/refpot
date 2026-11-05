"""Compile and execute maintained SQL tests against the package headers."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MaintainedNativeTests(unittest.TestCase):
    def test_compiler_selection_matches_existing_native_qualification(self):
        for override, available, expected in (
            (None, {"clang++": "/clang", "c++": "/gcc"}, "/clang"),
            ("/custom", {"clang++": "/clang", "c++": "/gcc"}, "/custom"),
            (None, {"c++": "/gcc"}, "/gcc"),
        ):
            with (
                self.subTest(override=override, available=available),
                patch.dict(os.environ, {"CXX": override or ""}),
                patch.object(shutil, "which", side_effect=available.get),
                patch.object(
                    subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0, "", ""),
                ) as run,
            ):
                self.test_maintained_native_contract()
                commands = [call.args[0] for call in run.call_args_list]
                self.assertEqual(len(commands), 12)
                for command in commands[::2]:
                    self.assertEqual(command[0], expected)
                    self.assertIn("-Werror", command)
                self.assertEqual(
                    sum("-fsanitize=address,undefined" in command for command in commands), 3
                )

    def test_compile_failure_includes_diagnostics(self):
        with patch.object(
            subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", "compiler detail"),
        ) as run:
            # Run through unittest so subTest failures can be inspected without
            # swallowing them in this enclosing test's result.
            result = unittest.TestResult()
            MaintainedNativeTests("test_maintained_native_contract").run(result)
        self.assertEqual(run.call_count, 6)  # Never execute after a failed compile.
        self.assertFalse(result.wasSuccessful())
        self.assertTrue(result.failures)
        self.assertTrue(all("compiler detail" in message for _, message in result.failures))

    def test_maintained_native_contract(self):
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
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
                        compiled = subprocess.run(
                            command, capture_output=True, text=True, timeout=120
                        )
                        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
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
