"""Build and qualify the local SQL preview without installing packages."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    compiler = os.environ.get("CXX") or shutil.which("clang++") or shutil.which("c++")
    if not compiler:
        raise RuntimeError("an existing C++17 compiler is required; nothing is installed")
    flags = ["-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror"]
    env = {
        **os.environ,
        "TMPDIR": str(output),
        "ASAN_OPTIONS": "detect_leaks=0",
        "UBSAN_OPTIONS": "halt_on_error=1",
    }
    paths = sorted(p for p in HERE.iterdir() if p.suffix in (".py", ".cpp", ".hpp"))
    paths += [
        HERE / "CONTRACT.md",
        ROOT / "research/shared-change/native.hpp",
        ROOT / "native/model/model.hpp",
        ROOT / "examples/experimental_native_sql.py",
        ROOT / "tests/test_native_sql.py",
    ]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    steps = []

    def run(command, *, cwd=ROOT, extra_env=None):
        result = subprocess.run(
            command,
            cwd=cwd,
            env={**env, **(extra_env or {})},
            capture_output=True,
            text=True,
            timeout=180,
        )
        log = f"step-{len(steps):02d}.log"
        (output / log).write_text(result.stdout + result.stderr)
        steps.append(
            {
                "command": list(map(str, command)),
                "cwd": str(cwd),
                "exit_code": result.returncode,
                "log": log,
            }
        )
        print(result.stdout + result.stderr, end="", flush=True)
        result.check_returncode()

    library = output / ("librefpot_sql.dylib" if sys.platform == "darwin" else "librefpot_sql.so")
    run([compiler, *flags, "-shared", "-fPIC", str(HERE / "bridge.cpp"), "-o", str(library)])
    for source in (
        "test_scan.cpp",
        "test_sql.cpp",
        "test_qualification.cpp",
        "test_bridge.cpp",
        "test_budget.cpp",
    ):
        for sanitized in (False, True):
            binary = output / (Path(source).stem + ("-sanitized" if sanitized else ""))
            sanitizers = (
                ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if sanitized else []
            )
            run([compiler, *flags, *sanitizers, str(HERE / source), "-o", str(binary)])
            run([str(binary)])
    run(
        [sys.executable, str(HERE / "test_python.py"), "-v"],
        extra_env={"REFPOT_SQL_LIBRARY": str(library)},
    )
    consumer = output / "consumer"
    consumer.mkdir()
    for source in (HERE / "native_sql.py", ROOT / "examples/experimental_native_sql.py", library):
        shutil.copy2(source, consumer / source.name)
    run(
        [
            sys.executable,
            "-I",
            "-c",
            "import pathlib,sys; sys.path.insert(0,str(pathlib.Path.cwd())); import native_sql; assert pathlib.Path(native_sql.__file__).parent == pathlib.Path.cwd(); print('Outside-checkout adapter:', native_sql.__file__)",
        ],
        cwd=consumer,
    )
    for mode in ("overlay", "modular"):
        for _ in range(2):
            run(
                [
                    sys.executable,
                    str(consumer / "experimental_native_sql.py"),
                    "--library",
                    str(consumer / library.name),
                    "--mode",
                    mode,
                ],
                cwd=consumer,
                extra_env={"PYTHONPATH": ""},
            )
    assert all(
        hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items()
    ), "sources changed during qualification"
    manifest = {
        "scope": "local volatile native SQL/Python preview, not installed wheel or performance qualification",
        "source_hashes": hashes,
        "library_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
        "compiler": subprocess.check_output([compiler, "--version"], text=True),
        "python": sys.version,
        "platform": platform.platform(),
        "flags": flags,
        "sanitizer_scope": "native scan, SQL, parser and C bridge tests; Python loads normal library",
        "steps": steps,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for path in paths:
        target = output / "source" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    print("Qualified local SQL preview:", output)


if __name__ == "__main__":
    main()
