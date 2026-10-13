from refpot import Database


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
