"""Opt-in reproduction; verify is offline, smoke/campaign require Docker."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent
SQLITE_URL = 'https://www.sqlite.org/2025/sqlite-amalgamation-3510000.zip'
SQLITE_HASHES = {
    'sqlite3.c': 'dc58f0b5b74e8416cc29b49163a00d6b8bf08a24dd4127652beaaae307bd1839',
    'sqlite3.h': '05c48cbf0a0d7bda2b6d0145ac4f2d3a5e9e1cb98b5d4fa9d88ef620e1940046',
}


def verify():
    for name, expected in json.loads((ROOT / 'manifest.json').read_text()).items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    with tempfile.TemporaryDirectory(prefix='refpot-verify-', dir=os.environ.get('TMPDIR')) as folder:
        out = Path(folder)
        (out / 'analyze.py').write_bytes((ROOT / 'analyze.py').read_bytes())
        with tarfile.open(ROOT / 'data/raw-records.tar.gz') as archive:
            members = archive.getmembers()
            assert len(members) == 672
            for member in members:
                name = Path(member.name)
                assert member.isfile() and not name.is_absolute() and '..' not in name.parts
                assert len(name.parts) == 2 and name.name == 'raw.jsonl'
                target = out / 'container-work' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = archive.extractfile(member)
                assert extracted is not None
                target.write_bytes(extracted.read())
        subprocess.run([sys.executable, str(out / 'analyze.py')], check=True, capture_output=True)
        actual = json.loads((out / 'summary.json').read_text())
        assert actual == json.loads((ROOT / 'summary.json').read_text()), 'summary drift'
        assert all(min(r['ratio_vs_best_same_policy_sql_service'], r['ratio_vs_best_same_policy_sql_cold']) >= 2
                   and r['p99_s'] < r['best_sql_p99_s'] for r in actual['summary'])
    print('PASS: hashes, exact 672 records, unchanged summary, all 16 service/setup/p99 cells')


def fetch_sqlite(destination):
    try:
        with urllib.request.urlopen(SQLITE_URL, timeout=90) as response:
            data = response.read()
    except urllib.error.URLError:
        # Some python.org macOS installs lack CA roots. System curl still verifies TLS.
        data = subprocess.run(['curl', '--fail', '--location', '--max-time', '90', SQLITE_URL],
                              check=True, capture_output=True).stdout
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name, expected in SQLITE_HASHES.items():
            matches = [n for n in archive.namelist() if n.endswith('/' + name)]
            assert len(matches) == 1
            content = archive.read(matches[0])
            assert hashlib.sha256(content).hexdigest() == expected, name
            (destination / name).write_bytes(content)


def execute(mode, output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sql = output / 'sqlite'
    sql.mkdir()
    fetch_sqlite(sql)
    suffix = uuid.uuid4().hex[:12]
    volume, container = 'refpot-repro-' + suffix, 'refpot-repro-' + suffix
    subprocess.run(['docker', 'volume', 'create', volume], check=True)
    command = ['docker', 'run', '--name', container, '--platform', 'linux/arm64',
               '-v', f'{volume}:/volume', '-v', f'{ROOT}:/src:ro',
               '-v', f'{sql}:/sqlite:ro', '-w', '/build', 'gcc:14', 'bash', '-lc']
    if mode == 'smoke':
        shell = '''set -euo pipefail
cp /src/*.hpp /src/*.cpp /sqlite/sqlite3.h /sqlite/sqlite3.c /build/
gcc -O3 -c sqlite3.c -o sqlite3.o
g++ -O3 -std=c++17 -DDENSE=1 -DTARGETED=1 -DPREFILL=1 -DREGION_COUNT=4096 -DRING_CAPACITY=32768 -DMAX_GROUP=1 -DFRAME_BYTES=128 -DDIRECT_OWNER=1 -DDSYNC_PACKED=1 -DVALUE_BANKS=1 -DSQL_CACHE_KIB=2000 -I/build backlog-n100000.cpp sqlite3.o -ldl -pthread -lm -Wl,--wrap=fsync,--wrap=fdatasync,--wrap=pwrite,--wrap=pwrite64,--wrap=write -o smoke
./smoke /volume/native-smoke 1 512 0 0 0
./smoke /volume/sqlite-smoke 1 512 0 0 5
'''
    else:
        shell = 'set -euo pipefail; bash /src/run.sh'
    with (output / 'execution.log').open('w') as log:
        result = subprocess.run(command + [shell], stdout=log, stderr=subprocess.STDOUT)
    (output / 'run.json').write_text(json.dumps({'container': container, 'volume': volume,
        'mode': mode, 'exit_code': result.returncode, 'image': 'gcc:14'}, indent=2))
    if result.returncode:
        raise RuntimeError(f'container exited {result.returncode}; see {output}/execution.log')
    subprocess.run(['docker', 'cp', f'{container}:/volume/' +
                    ('random-profile-01' if mode == 'campaign' else 'native-smoke'),
                    str(output / 'container-work')], check=True)
    if mode == 'smoke':
        subprocess.run(['docker', 'cp', f'{container}:/volume/sqlite-smoke', str(output / 'sqlite-smoke')], check=True)
        for name in ['container-work', 'sqlite-smoke']:
            record = json.loads((output / name / 'raw.jsonl').read_text())
            assert record['valid'] and record['requests'] == record['frontier'] == 512
    if mode == 'campaign':
        (output / 'analyze.py').write_bytes((ROOT / 'analyze.py').read_bytes())
        subprocess.run([sys.executable, str(output / 'analyze.py')], check=True)
    print(f'PASS {mode}; evidence: {output}; retained container={container}, volume={volume}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['verify', 'smoke', 'campaign'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.mode == 'verify':
        verify()
    else:
        if args.mode == 'campaign' and args.output is None:
            parser.error('campaign requires --output: 672 sequential trials took about 10 hours')
        output = args.output or Path(os.environ.get('TMPDIR', '.')) / ('refpot-smoke-' + uuid.uuid4().hex[:12])
        execute(args.mode, output)


if __name__ == '__main__':
    main()
