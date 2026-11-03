"""Compile the shipped core, including inherited maintenance/failure controls."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RelationalNativeTests(unittest.TestCase):
    def test_native_correctness_and_work_accounting(self):
        compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
        self.assertIsNotNone(compiler, "C++17 compiler is required for native qualification")
        assert compiler is not None
        with tempfile.TemporaryDirectory(prefix="refpot-relational-native-") as directory:
            inherited = Path(directory) / "inherited.cpp"
            source = (ROOT / "research/shared-change/test_native.cpp").read_text()
            inherited.write_text(
                source.replace(
                    '#include "native.hpp"',
                    f'#include "{ROOT / "native/relational/foundation.hpp"}"',
                    1,
                )
            )
            sources = [ROOT / "tests/test_relational_native.cpp", inherited]
            for name in ("test_qualification.cpp", "test_budget.cpp"):
                source = (ROOT / "research/native-sql" / name).read_text()
                self.assertIn('#include "sql.hpp"', source)
                generated = Path(directory) / name
                generated.write_text(
                    source.replace(
                        '#include "sql.hpp"', f'#include "{ROOT / "native/relational/sql.hpp"}"', 1
                    )
                )
                sources.append(generated)
            for source_path in sources:
                for sanitized in (False, True):
                    binary = Path(directory) / ("sanitized" if sanitized else "normal")
                    flags = ["-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
                    if sanitized:
                        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
                    compiled = subprocess.run(
                        [compiler, *flags, str(source_path), "-o", str(binary)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )
                    self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
                    executed = subprocess.run(
                        [str(binary)],
                        capture_output=True,
                        text=True,
                        timeout=120,
                        env={
                            **os.environ,
                            "ASAN_OPTIONS": "detect_leaks=0",
                            "UBSAN_OPTIONS": "halt_on_error=1",
                        },
                    )
                    self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
