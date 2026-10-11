"""Subprocess-only filesystem faults; no production hooks or power-loss claim."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

SHIM = Path(__file__).parent / 'native' / 'io_faults.c'


@pytest.fixture(scope='module')
def shim(tmp_path_factory):
    if sys.platform not in ('darwin', 'linux'):
        pytest.skip('syscall interposition requires macOS/Linux')
    directory = tmp_path_factory.mktemp('native-faults')
    out = directory / ('fault.dylib' if sys.platform == 'darwin' else 'fault.so')
    command = ['cc', '-dynamiclib' if sys.platform == 'darwin' else '-shared',
               '-fPIC', '-Wall', '-Wextra', '-Werror', str(SHIM), '-o', str(out)]
    if sys.platform == 'linux':
        command.append('-ldl')
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return out


@pytest.mark.parametrize('call,target,action', [
    ('write', '.wal', 'mutation'),
    ('fsync', '.wal', 'mutation'),
    ('fsync', '.tmp', 'checkpoint'),
    ('rename', '.tmp', 'checkpoint'),
    ('fsync', 'directory', 'checkpoint'),
    ('ftruncate', '.wal', 'checkpoint'),
    ('fsync', '.wal', 'checkpoint'),
])
def test_fault_poison_and_acknowledged_prefix(tmp_path, shim, call, target, action):
    dbpath = tmp_path / 'db'
    sentinel = tmp_path / 'fired'
    faultpath = str(tmp_path) if target == 'directory' else str(dbpath) + target
    operation = "with d.transaction():\n  d.insert(2,22,'uncertain')\n  d.insert(4,44,'paired')" if action == 'mutation' else 'd.checkpoint()'
    script = f'''from refpot import Database
import os,sys
d=Database(sys.argv[1])
d.insert(1,11,'ack')
# Activate only AFTER initial directory/WAL creation and first acknowledgement.
os.environ['REFPOT_FAULT_PATH']=sys.argv[2]
os.environ['REFPOT_FAULT_CALL']=sys.argv[3]
try:
 {operation}
except RuntimeError: pass
else: raise AssertionError('injected operation unexpectedly succeeded')
try: d.get(1)
except RuntimeError: pass
else: raise AssertionError('uncertain writer remained usable')
d.close()
'''
    env = os.environ.copy()
    env.pop('REFPOT_FAULT_PATH', None)
    env.pop('REFPOT_FAULT_CALL', None)
    env['REFPOT_FAULT_SENTINEL'] = str(sentinel)
    if sys.platform == 'darwin':
        env['DYLD_INSERT_LIBRARIES'] = str(shim)
    else:
        env['LD_PRELOAD'] = str(shim)
    result = subprocess.run([sys.executable, '-c', script, str(dbpath), faultpath, call],
                            cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert sentinel.exists(), 'interposer did not fire'
    assert call in sentinel.read_text().splitlines()
    # A successful physical write with a failed sync can recover atomically;
    # failure does not promise the new transaction is definitely absent.
    verify = '''from refpot import Database,Row
import sys
with Database(sys.argv[1]) as d:
 assert d.get(1)==Row(1,11,'ack')
 try: row=d.get(2)
 except KeyError:
  assert len(d)==1
  try: d.get(4)
  except KeyError: pass
  else: raise AssertionError('half transaction recovered')
 else:
  assert row==Row(2,22,'uncertain') and len(d)==3
  assert d.get(4)==Row(4,44,'paired')
 d.insert(3,33,'continued')
with Database(sys.argv[1]) as d:
 assert d.get(1)==Row(1,11,'ack')
 assert d.get(3)==Row(3,33,'continued')
'''
    clean_env = os.environ.copy()
    for name in ('DYLD_INSERT_LIBRARIES', 'LD_PRELOAD', 'REFPOT_FAULT_PATH',
                 'REFPOT_FAULT_CALL', 'REFPOT_FAULT_SENTINEL'):
        clean_env.pop(name, None)
    result = subprocess.run([sys.executable, '-c', verify, str(dbpath)], cwd=tmp_path,
                            env=clean_env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
