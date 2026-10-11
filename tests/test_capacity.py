"""Capacity checks must happen before acknowledging uncheckpointable state."""
import struct
import zlib

import pytest

from refpot import Database


def test_snapshot_capacity_is_enforced_before_commit(tmp_path):
    maximum = 64 * 1024 * 1024
    record_size = 48
    count = (maximum - 32) // record_size
    data = bytearray(28 + count * record_size)
    struct.pack_into('<8sIQQ', data, 0, b'RPSNAP2\0', 2, 0, count)
    text = b'x' * 31
    for key in range(count):
        offset = 28 + key * record_size
        struct.pack_into('<qqB', data, offset, key, 1, len(text))
        data[offset + 17:offset + record_size] = text
    data.extend(struct.pack('<I', zlib.crc32(data)))
    path = tmp_path / 'full'
    path.write_bytes(data)
    del data
    with Database(path) as db:
        with pytest.raises(ValueError, match='capacity'):
            db.insert(count, 2, text.decode())
        assert len(db) == count
        assert (tmp_path / 'full.wal').stat().st_size == 0
        # Validation refusal must not poison the owner.
        assert db.get(count - 1).value == 1
