"""Verify and preserve the parent-run RefPot PR performance evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import statistics

source=Path('/Users/tugrulguner/.hermes/cache/scratch/refpot-parent-benchmark')
dest=Path('/Users/tugrulguner/Desktop/hermes-agent/research/refpot-simplicity/pr-performance-evidence')
assert not dest.exists()
shutil.copytree(source,dest)
records=[]
summary=[]
for rows in (1000,10000):
    plans=[]
    data={}
    for label in ('baseline','candidate'):
        folder=dest/f'{label}{rows}'
        plan=json.loads((folder/'plan.json').read_text())
        plan_hash=hashlib.sha256((folder/'plan.json').read_bytes()).hexdigest()
        metadata=json.loads((folder/'run.json').read_text())
        assert plan_hash==metadata['plan_sha256']==(folder/'plan.sha256').read_text().split()[0]
        assert 'site-packages' in metadata['environment']['refpot_import_path']
        plans.append(plan_hash)
        raw=[json.loads(x) for x in (folder/'raw.jsonl').read_text().splitlines()]
        keys={(r['repeat'],r['rows'],r['workload'],r['candidate']) for r in raw}
        expected={(rep,rows,w,c) for rep in range(5) for w in plan['workloads'] for c in plan['candidates']}
        assert keys==expected and len(raw)==len(keys)==75
        for r in raw:
            assert r['operations']==plan['operations_by_cell'][f"{rows}:{r['workload']}"]
            assert r['seed']==plan['seed'] and r['verified'] and r['full_state_validated'] and r['recovery_validated'] and r['clean_reopen_validated']
            assert r['operations_ns']>=plan['minimum_duration_ns']
            assert r['service_ns']==r['operations_ns']+r['checkpoint_ns']
        data[label]=raw
        records.extend(dict(package=label,**r) for r in raw)
    assert plans[0]==plans[1]
    for workload in plan['workloads']:
        b=[r for r in data['baseline'] if r['workload']==workload and r['candidate']=='refpot']
        c=[r for r in data['candidate'] if r['workload']==workload and r['candidate']=='refpot']
        old=statistics.median(r['service_ns'] for r in b)
        new=statistics.median(r['service_ns'] for r in c)
        sqlite={name:statistics.median(r['service_ns'] for r in data['candidate'] if r['workload']==workload and r['candidate']==name) for name in plan['candidates'] if name!='refpot'}
        best=min(sqlite,key=sqlite.get)
        pairs=[]
        for rep in range(5):
            rr={r['candidate']:r['service_ns'] for r in data['candidate'] if r['workload']==workload and r['repeat']==rep}
            pairs.append(rr[best]/rr['refpot'])
        summary.append(dict(rows=rows,workload=workload,operations=c[0]['operations'],baseline_ms=old/1e6,candidate_ms=new/1e6,improvement_over_baseline=old/new,best_sqlite=best,sqlite_ms=sqlite[best]/1e6,sqlite_relative_speedup=sqlite[best]/new,paired_sqlite_speedup_range=[min(pairs),max(pairs)]))
assert len(records)==len({(r['package'],r['rows'],r['workload'],r['candidate'],r['repeat']) for r in records})==300
recovery=[]
for label in ('baseline','candidate'):
    recovery.extend(json.loads(x) for x in (dest/f'recovery-{label}.jsonl').read_text().splitlines())
assert len(recovery)==len({(r['label'],r['repeat'],r['transactions']) for r in recovery})==12
recovery_summary=[]
for count in (128,1024):
    medians={label:statistics.median(r['reopen_ns'] for r in recovery if r['label']==label and r['transactions']==count)/1e6 for label in ('baseline','candidate')}
    assert all(r['verified'] for r in recovery)
    recovery_summary.append(dict(transactions=count,rows=10000,median_ms=medians,improvement=medians['baseline']/medians['candidate']))
result=dict(baseline='6cc633fac687dbdbfab211507b3d87caa5ffcd82',candidate='e784db03cf797518ec852a19e73202311eabce7f',harness='88626e10db9190b77ac0e46c1a3f05dfa5613ace',measured_records=len(records),recovery_records=len(recovery),summary=summary,recovery=recovery_summary,qualified_global_2x=False)
(dest/'comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
