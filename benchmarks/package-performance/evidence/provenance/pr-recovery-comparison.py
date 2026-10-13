"""Same-fixture installed-wheel recovery comparison; no crash/power-loss claim."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from refpot import Database, Row

p = argparse.ArgumentParser()
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--label', required=True)
args = p.parse_args()
assert not args.output.exists()
args.output.parent.mkdir(parents=True, exist_ok=True)
for repeat in range(3):
    for transactions in ([128,1024] if repeat % 2 == 0 else [1024,128]):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as temp:
            path = Path(temp)/'db'
            shutil.copyfile(args.fixture,path)
            with Database(path) as db:
                assert len(db)==10000
                for i in range(transactions):
                    db.update(2,value=i+1)
            wal_bytes = Path(str(path)+'.wal').stat().st_size
            start=time.perf_counter_ns()
            db=Database(path)
            elapsed=time.perf_counter_ns()-start
            assert len(db)==10000
            assert all(db.get(3*i+1+int(i%7==0)) == Row(3*i+1+int(i%7==0),transactions if i==0 else i%17,f'row-{i}') for i in range(10000))
            db.close()
            record=dict(label=args.label,repeat=repeat,rows=10000,transactions=transactions,wal_bytes=wal_bytes,reopen_ns=elapsed,verified=True)
            with args.output.open('a') as out:
                out.write(json.dumps(record)+'\n')
            print(json.dumps(record))
