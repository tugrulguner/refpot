import itertools,json,re,statistics,math
from pathlib import Path
p=Path(__file__).parent;rows={};med=statistics.median;names=['native','sqlite_64','sqlite_128','sqlite_256','sqlite_512','sqlite_1024','sqlite_serial_128']
for path in (p/'container-work').glob('run*-n*-g*-k*-p*-b*/raw.jsonl'):
 m=re.fullmatch(r'run(\d+)-n(\d+)-g(\d+)-k(\d+)-p(\d+)-b(\d+)',path.parent.name);assert m
 ca,n,g,k,pair,b=map(int,m.groups());lines=path.read_text().splitlines();assert len(lines)==1;r=json.loads(lines[0])
 assert (r['campaign'],r['clients'],r['sql_cache_kib'],r['pair'],r['candidate'])==(ca,g,k,pair,names[b])
 cap=32768//g;assert r['ring_capacity']==cap and r['frame_bytes']=={1:128,4:256,16:512,64:2048}[g] and r['region_count']==4096 and r['value_banks']==r['dsync_packed']==1
 assert r['direct_owner']==(g==1) and r['queue']==('direct-owner' if g==1 else 'targeted') and r['valid'] and r['requests']==r['frontier']==131072
 h=r['hist'];assert len(h)==g+1 and h[0]==0 and sum(h)==r['transactions'] and sum(i*c for i,c in enumerate(h))==131072
 if g==1 or b==6:assert h[1]==131072 and r['transactions']==131072
 assert r['dsync_write_calls']==(r['transactions'] if b==0 else 0) and r['sync_calls']>=r['transactions'] and r['write_bytes']>0
 assert r['sqlite_cache_used_bytes']==0 if b==0 else r['sqlite_cache_used_bytes']>0
 assert r['through_final_wall_s']+0.0001>=r['backend_setup_s']+r['commit_s']+r['final_s']
 if b==0:assert r['checkpoint_count']==math.ceil(r['transactions']/cap) and r['checkpoint_count']>=4 and 0<r['checkpoint_bytes']<=8*n*r['checkpoint_count']
 key=(ca,n,g,k,pair,b);assert key not in rows;rows[key]=r
expected=set(itertools.product([1,2],[100000,1000000],[1,4,16,64],[2000,131072],range(3),range(7)));assert set(rows)==expected,{'missing':sorted(expected-set(rows)),'extra':sorted(set(rows)-expected)}
summary=[]
for ca,n,g in itertools.product([1,2],[100000,1000000],[1,4,16,64]):
 eligible=range(1,7) if g==1 else range(1,6)
 best=min((med([rows[(ca,n,g,k,pair,b)]['commit_s']+rows[(ca,n,g,k,pair,b)]['final_s'] for pair in range(3)]),k,names[b]) for k,b in itertools.product([2000,131072],eligible))
 cold=min((med([rows[(ca,n,g,k,pair,b)]['through_final_wall_s'] for pair in range(3)]),k,names[b]) for k,b in itertools.product([2000,131072],eligible))
 rr=[rows[(ca,n,g,k,pair,0)] for k in [2000,131072] for pair in range(3)];total=med([r['commit_s']+r['final_s'] for r in rr]);cv=med([r['through_final_wall_s'] for r in rr])
 out={'campaign':ca,'n':n,'clients':g,'ring_slots':32768//g,'service_s':total,'cold_s':cv,'ratio_vs_best_same_policy_sql_service':best[0]/total,'ratio_vs_best_same_policy_sql_cold':cold[0]/cv,'best_sql_service':{'s':best[0],'cache_kib':best[1],'candidate':best[2]},'best_sql_cold':{'s':cold[0],'cache_kib':cold[1],'candidate':cold[2]}}
 for field in ['checkpoint_s','checkpoint_bytes','checkpoint_count','commit_sync_s','p99_s','recovery_s','backend_setup_s']:out[field]=med([r[field] for r in rr])
 out['native_mean_group']=med([131072/r['transactions'] for r in rr]);out['best_sql_p99_s']=min(med([rows[(ca,n,g,k,pair,b)]['p99_s'] for pair in range(3)]) for k,b in itertools.product([2000,131072],eligible))
 summary.append(out)
result={'record_count':len(rows),'summary':summary,'scope':'Currentvaluebankengineext4volume,100k/1Mnonaffine existingrows131072requests4/64trueclients;singletondirect,multiclientdrain-onlytargetedqueueequalSQL/native;32768logicaloperationredo upperbudget viaCAP8192/group,frames128/256/512/2048,coupledpolicygeometryexplicit;>=4maintenancecheckpointsallcells. TwoactualSQLcachebudgets,fiveWALthresholds,serialcontrol;nativepooledsixtrialmedians,strongestsame-policySQLpercell. NotgeneralCRUD,powerloss ornativephysicalLinuxqualification.'}
(p/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
