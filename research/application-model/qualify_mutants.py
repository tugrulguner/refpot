"""Compile faulty copies and prove the actual native path rejects their behavior."""

import shutil
import subprocess
import tempfile
from pathlib import Path

from models import insert, resource_spec
from native_model import ModelError, NativeModel

ROOT = Path(__file__).resolve().parents[2]


def main():
    compiler = shutil.which("clang++") or shutil.which("c++")
    if compiler is None:
        raise RuntimeError("C++17 compiler required")
    source = (ROOT / "native/model/model.hpp").read_text()
    anchor = "if(!touched) return;"
    if source.count(anchor) != 1:
        raise AssertionError("mutant anchor changed; review the substitution")
    mutants = {
        "missing_propagation": source.replace(anchor, 'if(!touched || d.op!="source") return;'),
        "missing_absence_dependency": source.replace(
            anchor, 'if(!touched || d.op=="anti") return;'
        ),
    }
    publication = "for(const auto& n:required_) if(!candidate.at(n).empty())"
    if source.count(publication) != 1:
        raise AssertionError("publication mutant anchor changed")
    mutants["partial_publication"] = source.replace(
        publication, "bags_=candidate;\n        " + publication
    )
    with tempfile.TemporaryDirectory(prefix="refpot-model-mutants-") as directory:
        work = Path(directory)
        for name, code in mutants.items():
            (work / "model.hpp").write_text(code)
            shutil.copyfile(ROOT / "native/model/driver.cpp", work / "driver.cpp")
            binary = work / name
            subprocess.run(
                [
                    compiler,
                    "-std=c++17",
                    "-O1",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    str(work / "driver.cpp"),
                    "-o",
                    str(binary),
                ],
                check=True,
                timeout=120,
            )
            with NativeModel(binary, resource_spec()) as db:
                db.apply([insert("resources", 1, 10), insert("teams", 1, 10)])
                if name == "missing_propagation":
                    db.apply([insert("reservations", 1, 1, 1, 3)])
                    detected = db.snapshot()["resource_remaining"] != [[1, 7, 1]]
                elif name == "missing_absence_dependency":
                    rejected = False
                    try:
                        db.apply([insert("reservations", 1, 999, 1, 3)])
                    except ModelError:
                        rejected = True
                    detected = not rejected
                else:
                    before = db.snapshot()
                    rejected = False
                    try:
                        db.apply([insert("reservations", 1, 1, 1, 11)])
                    except ModelError:
                        rejected = True
                    detected = rejected and db.snapshot() != before
                if not detected:
                    raise AssertionError(f"mutant was not detected: {name}")
                print(f"REJECTED {name}: executed native mutant violated the contract")


if __name__ == "__main__":
    main()
