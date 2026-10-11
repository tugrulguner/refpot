import os
import subprocess
import sys
import threading

import pytest

from refpot import Database, Row


def test_commits_use_redo_until_explicit_checkpoint(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2, "stored")
        assert (tmp_path / "db.wal").stat().st_size > 0
        assert not path.exists()
        db.checkpoint()
        assert path.exists()
        assert (tmp_path / "db.wal").stat().st_size == 0
    with Database(path) as db:
        assert db.get(1) == Row(1, 2, "stored")


def test_every_key_entrypoint_rejects_bool_and_non_integer(tmp_path):
    with Database(tmp_path / "db") as db:
        db.insert(1, 2)
        for key in [True, 1.0, "1"]:
            for call in [
                lambda key=key: db.get(key),
                lambda key=key: db.update(key, value=7),
                lambda key=key: db.delete(key),
            ]:
                with pytest.raises(TypeError):
                    call()
        assert db.get(1).value == 2


def test_thread_affinity_prevents_transaction_cross_talk(tmp_path):
    with Database(tmp_path / "db") as db:
        errors = []

        def worker():
            try:
                db.insert(9, 9)
            except RuntimeError as exc:
                errors.append(str(exc))

        with db.transaction():
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
        assert errors
        assert len(db) == 0


def test_process_exit_without_close_recovers_crud_transaction(tmp_path):
    path = tmp_path / "db"
    code = """from refpot import Database
import os,sys
db=Database(sys.argv[1])
with db.transaction():
 db.insert(1,2,'real')
 db.insert(3,4)
 db.update(1,value=8)
 db.delete(3)
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path)], check=True)
    with Database(path) as db:
        assert db.get(1) == Row(1, 8, "real")
        assert len(db) == 1


def test_truncated_unacknowledged_tail_preserves_acknowledged_prefix(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2)
    with (tmp_path / "db.wal").open("ab") as file:
        file.write(b"\x10\x00")
    with Database(path) as db:
        assert db.get(1).value == 2
        db.insert(2, 3)
    with Database(path) as db:
        assert len(db) == 2


def test_corrupt_checkpoint_fails_without_retaining_lock(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2)
        db.checkpoint()
    saved = path.read_bytes()
    data = bytearray(saved)
    data[-1] ^= 1
    path.write_bytes(data)
    with pytest.raises(RuntimeError):
        Database(path)
    path.write_bytes(saved)
    with Database(path) as db:
        assert db.get(1).value == 2


def test_complete_redo_corruption_is_not_silently_dropped(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2)
    wal = tmp_path / "db.wal"
    data = bytearray(wal.read_bytes())
    # Destroy both checksum-protected copies while preserving framing length.
    data[4:] = b"\x00" * (len(data) - 4)
    wal.write_bytes(data)
    with pytest.raises(RuntimeError):
        Database(path)


def test_corrupted_redo_length_fails_closed(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2)
    wal = tmp_path / "db.wal"
    data = bytearray(wal.read_bytes())
    data[0] ^= 1
    wal.write_bytes(data)
    with pytest.raises(RuntimeError):
        Database(path)


def test_failed_write_poisons_owner_and_preserves_old_ack(tmp_path):
    path = tmp_path / "db"
    code = """from refpot import Database
import os,sys,resource,signal
db=Database(sys.argv[1]);db.insert(1,2)
limit=os.stat(sys.argv[1]+'.wal').st_size+20
signal.signal(signal.SIGXFSZ,signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
try: db.insert(3,4)
except RuntimeError: pass
else: raise AssertionError('write unexpectedly succeeded')
try: db.get(1)
except RuntimeError: pass
else: raise AssertionError('uncertain writer was not poisoned')
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path)], check=True)
    with Database(path) as db:
        assert db.get(1).value == 2
        with pytest.raises(KeyError):
            db.get(3)
        db.insert(5, 6)


def test_single_corrupt_redo_copy_recovers_other_copy(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2, "real")
    wal = tmp_path / "db.wal"
    data = bytearray(wal.read_bytes())
    data[40] ^= 1
    wal.write_bytes(data)
    with Database(path) as db:
        assert db.get(1) == Row(1, 2, "real")
        db.insert(3, 4)
    with Database(path) as db:
        assert len(db) == 2


def test_every_interrupted_append_prefix_keeps_old_ack(tmp_path):
    original = tmp_path / "original"
    with Database(original) as db:
        db.insert(1, 2)
    prefix = (tmp_path / "original.wal").read_bytes()
    with Database(original) as db:
        db.insert(3, 4)
    tail = (tmp_path / "original.wal").read_bytes()[len(prefix) :]
    # Simulate an unacknowledged append interrupted at each byte, not damage
    # to an already acknowledged record or physical power loss.
    for cut in range(len(tail)):
        path = tmp_path / f"prefix-{cut}"
        path.with_suffix(".wal").write_bytes(prefix + tail[:cut])
        with Database(path) as db:
            assert db.get(1).value == 2
            assert len(db) == 1
            db.insert(5, 6)
        with Database(path) as db:
            assert db.get(5).value == 6
            assert db.get(1).value == 2


def test_checksummed_invalid_utf8_is_rejected_on_open(tmp_path):
    import zlib

    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2, "x")
        db.checkpoint()
    data = bytearray(path.read_bytes())
    data[45] = 255
    data[-4:] = zlib.crc32(data[:-4]).to_bytes(4, "little")
    path.write_bytes(data)
    with pytest.raises(RuntimeError):
        Database(path)


def test_symlink_database_alias_is_rejected(tmp_path):
    path = tmp_path / "db"
    with Database(path) as db:
        db.insert(1, 2)
        db.checkpoint()
        alias = tmp_path / "alias"
        alias.symlink_to(path)
        with pytest.raises(RuntimeError):
            Database(alias)


def test_forked_owner_cannot_read_or_close_parent_database(tmp_path):
    with Database(tmp_path / "db") as db:
        pid = os.fork()
        if pid == 0:
            errors = 0
            for call in [lambda: len(db), db.close]:
                try:
                    call()
                except RuntimeError:
                    errors += 1
            os._exit(0 if errors == 2 else 9)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        # Child must not unlock the parent's file description.
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from refpot import Database; import sys; Database(sys.argv[1])",
                str(tmp_path / "db"),
            ],
            capture_output=True,
        )
        assert proc.returncode != 0
        db.insert(1, 2)


def test_lock_is_enforced_across_processes(tmp_path):
    path = tmp_path / "db"
    with Database(path):
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "from refpot import Database; import sys; Database(sys.argv[1])",
                str(path),
            ],
            capture_output=True,
        )
        assert proc.returncode != 0
