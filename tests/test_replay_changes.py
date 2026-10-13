import struct
import zlib

from refpot import Database


def _full_snapshot(path):
    maximum = 64 * 1024 * 1024
    count = (maximum - 32) // 48 + 1
    data = bytearray(struct.pack("<8sIQQ", b"RPSNAP2\0", 2, 0, count))
    data.extend(struct.pack("<qqB", 0, 1, 15) + b"x" * 15)
    for key in range(1, count):
        data.extend(struct.pack("<qqB", key, 1, 31) + b"x" * 31)
    data.extend(struct.pack("<I", zlib.crc32(data)))
    assert len(data) == maximum
    path.write_bytes(data)


def test_replay_capacity_uses_final_state_for_ordered_shrink_then_growth(tmp_path):
    path = tmp_path / "capacity-replay.db"
    _full_snapshot(path)
    with Database(path) as db:
        with db.transaction():
            db.update(1, text="")
            db.update(0, text="x" * 31)
        assert db.get(0).text == "x" * 31
        assert db.get(1).text == ""
    with Database(path) as db:
        assert db.get(0).text == "x" * 31
        assert db.get(1).text == ""
        db.update(0, value=2)
    with Database(path) as db:
        assert db.get(0).value == 2


def test_replay_capacity_accounts_for_insertions_and_deletions_before_upserts(tmp_path):
    path = tmp_path / "capacity-insert-delete.db"
    _full_snapshot(path)
    with Database(path) as db, db.transaction():
        db.delete(2)
        db.insert(2_000_000, 1, "z" * 31)
    with Database(path) as db:
        assert db.get(2_000_000).text == "z" * 31
        try:
            db.get(2)
        except KeyError:
            pass
        else:
            raise AssertionError("deleted row recovered")


def test_net_noop_transactions_do_not_write_wal_or_advance_sequence(tmp_path):
    path = tmp_path / "noop.db"
    with Database(path) as db:
        db.insert(1, 1, "original")
        db.checkpoint()
        wal = path.with_name(path.name + ".wal")
        assert wal.stat().st_size == 0
        with db.transaction():
            db.update(1, value=2)
            db.update(1, value=1)
        assert wal.stat().st_size == 0
        with db.transaction():
            db.delete(1)
            db.insert(1, 1, "original")
        assert wal.stat().st_size == 0
    with Database(path) as db:
        assert db.get(1).value == 1


def test_replay_applies_sequential_change_frames_without_losing_repeated_keys(tmp_path):
    path = tmp_path / "replay.db"
    db = Database(path)
    db.insert(1, 10, "initial")
    with db.transaction():
        db.update(1, value=11)
        db.insert(2, 20, "temporary")
        db.delete(2)
        db.insert(2, 21, "final")
    db.update(1, value=12)
    db.delete(2)
    db.insert(2, 22, "reinserted")
    db.close()

    reopened = Database(path)
    assert len(reopened) == 2
    assert reopened.get(1).value == 12
    assert reopened.get(2).text == "reinserted"
    reopened.close()
