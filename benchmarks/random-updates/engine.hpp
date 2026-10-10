#ifndef VALUE_BANKS
#define VALUE_BANKS 0
#endif
#include <type_traits>
#ifndef DSYNC_PACKED
#define DSYNC_PACKED 0
#endif
#ifndef RING_CAPACITY
#define RING_CAPACITY 512
#endif
#ifndef REGION_COUNT
#define REGION_COUNT 64
#endif
#ifndef PREFILL
#define PREFILL 0
#endif
#ifndef MAX_GROUP
#define MAX_GROUP 16
#endif
static_assert(MAX_GROUP==1||MAX_GROUP==4||MAX_GROUP==16||MAX_GROUP==64,"tested low-client group bounds");
#ifndef DENSE
#define DENSE 0
#endif
#ifndef FRAME_BYTES
#define FRAME_BYTES 512
#endif
// Fixed-schema single-writer experiment. No production or power-loss claim.
#include <sqlite3.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fcntl.h>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
namespace fs=std::filesystem;
using Clock=std::chrono::steady_clock;
double elapsed(Clock::time_point s){return std::chrono::duration<double>(Clock::now()-s).count();}
void need(bool b,const char*m){if(!b)throw std::runtime_error(m);}
uint64_t hash(const void*p,size_t n){uint64_t h=1469598103934665603ULL;auto*b=(const unsigned char*)p;while(n--){h^=*b++;h*=1099511628211ULL;}return h;}
void pw(int f,const void*p,size_t n,off_t off){auto*b=(const char*)p;while(n){auto z=pwrite(f,b,n,off);if(z<0&&errno==EINTR)continue;need(z>0,"pwrite");b+=z;n-=z;off+=z;}}
void pr(int f,void*p,size_t n,off_t off){auto*b=(char*)p;while(n){auto z=pread(f,b,n,off);if(z<0&&errno==EINTR)continue;need(z>0,"pread");b+=z;n-=z;off+=z;}}
constexpr uint64_t MAGIC=0x5246494e43303231ULL;constexpr size_t CAP=RING_CAPACITY,SLOT=FRAME_BYTES,REG=REGION_COUNT,COPIES=2;
struct Row{int64_t key,value;char text[32];bool operator==(const Row&o)const{return key==o.key&&value==o.value&&memcmp(text,o.text,32)==0;}};
using Stored=std::conditional_t<VALUE_BANKS,int64_t,Row>;
Stored stored(const Row&r){
#if VALUE_BANKS
return r.value;
#else
return r;
#endif
}
#include "dense.hpp"
#if DENSE
using Rows=DenseRows;
#else
using Rows=std::map<int64_t,Row>;
#endif
int64_t key_for_index(size_t i){return int64_t(3*i+1+(i%7==0));}
Rows fixture(size_t n){Rows out;for(size_t i=0;i<n;i++){Row r{};r.key=key_for_index(i);r.value=i%17;snprintf(r.text,32,"actual-row-%zu",i);out.emplace(r.key,r);}return out;}
struct Op{int64_t key,delta;uint64_t id;};
uint64_t request_mix(uint64_t x){x+=0x9e3779b97f4a7c15ULL;x=(x^(x>>30))*0xbf58476d1ce4e5b9ULL;x=(x^(x>>27))*0x94d049bb133111ebULL;return x^(x>>31);}
std::vector<Op> changes(size_t t,size_t batch,size_t n){std::vector<Op>v;for(size_t j=0;j<batch;j++)v.push_back({key_for_index(request_mix(t*batch+j)%n),1,t*batch+j+1});return v;}
Rows expected(size_t n,size_t b,size_t commits){auto r=fixture(n);for(size_t t=0;t<commits;t++)for(auto&o:changes(t,b,n))r.at(o.key).value+=o.delta;return r;}
struct Manifest{uint64_t magic,version,n,seq,cap,slot,regions,copies,frontier;uint64_t bank[REG],sums[REG],immutable_sum,value_banks,checksum;};
struct Head{uint64_t magic,seq,count,sum;};struct Tail{uint64_t magic,seq,sum;};
uint64_t framehash(Head h,const void*p,size_t bytes){h.sum=0;return hash(&h,sizeof h)^hash(p,bytes);}
struct Metrics{double lookup=0,encode=0,write=0,sync=0,publish=0,checkpoint=0;uint64_t regions=0,cpbytes=0,cps=0;};
struct Engine{
 fs::path dir;int log=-1,data=-1,immutable=-1;Manifest m{};Rows rows;std::map<int64_t,size_t>ordinal;std::array<bool,REG>dirty{};std::vector<char>buffer=std::vector<char>(SLOT);std::vector<char>packed=std::vector<char>(2*SLOT);bool incremental,poison=false;uint64_t seq=0,frontier=0;Metrics met;
 void addordinal(int64_t key,size_t i){
#if !DENSE
ordinal[key]=i;
#endif
}
 size_t rowindex(int64_t key)const{
#if DENSE
return rows.index(key);
#else
return ordinal.at(key);
#endif
}
 void syncdir(){int f=open(dir.c_str(),O_RDONLY|O_DIRECTORY);need(f>=0,"open directory");int rc=fsync(f);close(f);need(rc==0,"directory sync");}
 size_t lo(size_t r)const{return r*m.n/REG;}size_t hi(size_t r)const{return (r+1)*m.n/REG;}
 size_t region(size_t i)const{return std::min<size_t>(REG-1,((i+1)*REG-1)/m.n);}
 off_t at(size_t r,size_t bank)const{return (bank*m.n+lo(r))*sizeof(Stored);}
 void die(int stage,int target){if(stage==target)_exit(40+stage);}
 Engine(fs::path p,size_t n,bool inc):dir(p),incremental(inc){
  bool fresh=!fs::exists(dir/"manifest");if(fresh)need(fs::create_directory(dir),"new engine directory");
  data=open((dir/"base").c_str(),O_RDWR|O_CREAT,0600);log=open((dir/"ring").c_str(),O_RDWR|O_CREAT|(DSYNC_PACKED?O_DSYNC:0),0600);if(DSYNC_PACKED){need(log>=0&&(fcntl(log,F_GETFL)&O_DSYNC)==O_DSYNC,"actual O_DSYNC flag");io_dsync_fd=log;}need(data>=0&&log>=0,"engine files");if(VALUE_BANKS){immutable=open((dir/"immutable").c_str(),O_RDWR|O_CREAT,0600);need(immutable>=0,"immutable file");}
  if(fresh){m.magic=MAGIC;m.version=900+MAX_GROUP;m.copies=COPIES;m.n=n;m.cap=CAP;m.slot=SLOT;m.regions=REG;m.value_banks=VALUE_BANKS;need(posix_fallocate(data,0,2*n*sizeof(Stored))==0,"base allocation");need(posix_fallocate(log,0,CAP*SLOT*COPIES)==0,"ring allocation");if(PREFILL){std::array<char,65536> zero{};size_t bytes=CAP*SLOT*COPIES;for(size_t off=0;off<bytes;off+=zero.size())pw(log,zero.data(),std::min(zero.size(),bytes-off),off);}need(fsync(log)==0&&fsync(data)==0,"initialize sync");syncdir();rows=fixture(n);if(VALUE_BANKS){std::vector<Row>image;image.reserve(n);for(auto&x:rows)image.push_back(x.second);need(posix_fallocate(immutable,0,n*sizeof(Row))==0,"immutable allocation");pw(immutable,image.data(),image.size()*sizeof(Row),0);m.immutable_sum=hash(image.data(),image.size()*sizeof(Row));need(fsync(immutable)==0,"immutable sync before manifest");}size_t i=0;for(auto&x:rows)addordinal(x.first,i++);dirty.fill(true);checkpoint();met={};}
  else{int f=open((dir/"manifest").c_str(),O_RDONLY);need(f>=0,"manifest open");struct stat st{};need(fstat(f,&st)==0&&st.st_size==sizeof m,"manifest size");pr(f,&m,sizeof m,0);close(f);auto checksum=m.checksum;m.checksum=0;need(hash(&m,sizeof m)==checksum,"manifest checksum");m.checksum=checksum;need(m.magic==MAGIC&&m.version==900+MAX_GROUP&&m.copies==COPIES&&m.n==n&&n>=REG&&n<=1000000&&m.cap==CAP&&m.slot==SLOT&&m.regions==REG&&m.value_banks==VALUE_BANKS,"manifest metadata");need(fstat(data,&st)==0&&st.st_size==off_t(2*n*sizeof(Stored)),"base size");need(fstat(log,&st)==0&&st.st_size==off_t(CAP*SLOT*COPIES),"ring size");
   size_t ordinal_index=0;
#if VALUE_BANKS
need(fstat(immutable,&st)==0&&st.st_size==off_t(n*sizeof(Row)),"immutable size");std::vector<Row>image(n);pr(immutable,image.data(),image.size()*sizeof(Row),0);need(hash(image.data(),image.size()*sizeof(Row))==m.immutable_sum,"immutable checksum");for(auto&row:image){need(memchr(row.text,0,32)!=nullptr,"immutable text bounds");need(rows.emplace(row.key,row).second,"immutable duplicate key");addordinal(row.key,ordinal_index++);}for(size_t r=0;r<REG;r++){need(m.bank[r]<2,"bank bounds");std::vector<Stored>v(hi(r)-lo(r));pr(data,v.data(),v.size()*sizeof(Stored),at(r,m.bank[r]));need(hash(v.data(),v.size()*sizeof(Stored))==m.sums[r],"value region checksum");auto it=rows.begin()+lo(r);for(auto value:v){it->second.value=value;++it;}}
#else
for(size_t r=0;r<REG;r++){need(m.bank[r]<2,"bank bounds");std::vector<Row>v(hi(r)-lo(r));pr(data,v.data(),v.size()*sizeof(Row),at(r,m.bank[r]));need(hash(v.data(),v.size()*sizeof(Row))==m.sums[r],"region checksum");for(auto&row:v){need(memchr(row.text,0,32)!=nullptr,"text bounds");need(rows.emplace(row.key,row).second,"duplicate key");addordinal(row.key,ordinal_index++);}}
#endif
seq=m.seq;frontier=m.frontier;recover();met={};
  }
 }
 ~Engine(){if(io_dsync_fd==log)io_dsync_fd=-1;if(log>=0)close(log);if(data>=0)close(data);if(immutable>=0)close(immutable);}
 void checkpoint(int fault=0){auto start=Clock::now();try{Manifest next=m;next.seq=seq;next.frontier=frontier;std::vector<std::vector<Stored>>parts(REG);
#if DENSE
 for(size_t r=0;r<REG;r++)if(!incremental||dirty[r]){auto first=rows.begin()+lo(r),last=rows.begin()+hi(r);parts[r].reserve(hi(r)-lo(r));for(auto it=first;it!=last;++it)parts[r].push_back(stored(it->second));}
#else
 size_t i=0;for(auto&x:rows){size_t r=region(i++);if(!incremental||dirty[r])parts[r].push_back(stored(x.second));}
#endif

  for(size_t r=0;r<REG;r++)if(!incremental||dirty[r]){need(parts[r].size()==hi(r)-lo(r),"region partition");next.bank[r]=1-m.bank[r];auto bytes=parts[r].size()*sizeof(Stored);next.sums[r]=hash(parts[r].data(),bytes);pw(data,parts[r].data(),bytes,at(r,next.bank[r]));met.regions++;met.cpbytes+=bytes;}
  die(4,fault);need(fdatasync(data)==0,"checkpoint base sync");die(5,fault);next.checksum=0;next.checksum=hash(&next,sizeof next);int f=open((dir/"manifest.tmp").c_str(),O_CREAT|O_TRUNC|O_WRONLY,0600);need(f>=0,"manifest temp");pw(f,&next,sizeof next,0);need(fsync(f)==0,"manifest sync");close(f);die(6,fault);need(rename((dir/"manifest.tmp").c_str(),(dir/"manifest").c_str())==0,"manifest rename");die(7,fault);syncdir();die(8,fault);m=next;dirty.fill(false);met.cps++;met.checkpoint+=elapsed(start);
 }catch(...){poison=true;throw;}}
 void recover(){std::map<uint64_t,std::vector<Op>>pending;
 for(size_t slot=0;slot<CAP;slot++){std::vector<char>selected;Head chosen{};
  for(size_t copy=0;copy<COPIES;copy++){std::vector<char>f(SLOT);pr(log,f.data(),SLOT,(slot*COPIES+copy)*SLOT);Head h;Tail t;memcpy(&h,f.data(),sizeof h);memcpy(&t,f.data()+SLOT-sizeof t,sizeof t);
   bool valid=h.magic==MAGIC&&h.count>0&&h.count<=MAX_GROUP&&sizeof h+h.count*sizeof(Op)+sizeof t<=SLOT&&t.magic==MAGIC&&t.seq==h.seq&&t.sum==h.sum;
   if(valid)valid=framehash(h,f.data()+sizeof h,h.count*sizeof(Op))==h.sum;
   if(!valid||h.seq<=m.seq)continue;
   need(h.seq<=m.seq+CAP&&(h.seq-1)%CAP==slot,"record generation");
   if(!selected.empty())need(chosen.seq==h.seq&&chosen.count==h.count&&chosen.sum==h.sum&&selected==f,"conflicting valid copies");else{chosen=h;selected=std::move(f);}
  }
  if(selected.empty())continue;std::vector<Op>v(chosen.count);memcpy(v.data(),selected.data()+sizeof chosen,v.size()*sizeof(Op));need(pending.emplace(chosen.seq,v).second,"duplicate sequence");
 }
 for(auto&tx:pending){need(tx.first==seq+1,"sequence gap");for(auto&o:tx.second){need(rows.count(o.key)&&o.id==frontier+1,"recovery key/request sequence");frontier++;rows.at(o.key).value+=o.delta;dirty[region(rowindex(o.key))]=true;}seq=tx.first;}}
 void commit(const std::vector<Op>&v,int fault=0,bool sync_error=false){need(!poison&&v.size()>0&&v.size()<=MAX_GROUP&&sizeof(Head)+v.size()*sizeof(Op)+sizeof(Tail)<=SLOT,"commit bounds/state");if(seq-m.seq==CAP)checkpoint(fault);auto s=Clock::now();std::vector<Row*>targets;uint64_t requested=frontier;for(auto&o:v){need(o.id==++requested,"request sequence");auto it=rows.find(o.key);need(it!=rows.end(),"missing key");targets.push_back(&it->second);}met.lookup+=elapsed(s);s=Clock::now();std::fill(buffer.begin(),buffer.end(),0);Head h{MAGIC,seq+1,v.size(),0};h.sum=framehash(h,v.data(),v.size()*sizeof(Op));Tail t{MAGIC,h.seq,h.sum};memcpy(buffer.data(),&h,sizeof h);memcpy(buffer.data()+sizeof h,v.data(),v.size()*sizeof(Op));memcpy(buffer.data()+SLOT-sizeof t,&t,sizeof t);met.encode+=elapsed(s);
  try{s=Clock::now();off_t off=(seq%CAP)*SLOT*COPIES;if(DSYNC_PACKED&&(fault==0||fault==14)&&!sync_error){memcpy(packed.data(),buffer.data(),SLOT);memcpy(packed.data()+SLOT,buffer.data(),SLOT);pw(log,packed.data(),packed.size(),off);met.sync+=elapsed(s);die(14,fault);}else{if(fault==1){pw(log,buffer.data(),SLOT/2,off);die(1,fault);}if(fault==9||fault==10||fault==11){size_t len=fault==9?sizeof(Head)/2:fault==10?sizeof(Head)+v.size()*sizeof(Op)/2:SLOT-sizeof(Tail)/2;pw(log,buffer.data(),len,off);die(fault,fault);}pw(log,buffer.data(),SLOT,off);die(12,fault);if(fault==13){pw(log,buffer.data(),SLOT/2,off+SLOT);die(13,fault);}pw(log,buffer.data(),SLOT,off+SLOT);met.write+=elapsed(s);die(2,fault);s=Clock::now();if(sync_error)throw std::runtime_error("injected EIO at synchronization");need(fdatasync(log)==0,"commit sync");met.sync+=elapsed(s);die(3,fault);}s=Clock::now();for(size_t i=0;i<v.size();i++){targets[i]->value+=v[i].delta;frontier++;dirty[region(rowindex(v[i].key))]=true;}seq++;met.publish+=elapsed(s);}catch(...){poison=true;throw;}}
};
void sqlok(int rc){need(rc==SQLITE_OK,"SQLite rc");}void exec(sqlite3*d,const char*s){sqlok(sqlite3_exec(d,s,nullptr,nullptr,nullptr));}
Rows sqlrows(sqlite3*d){sqlite3_stmt*s;sqlok(sqlite3_prepare_v2(d,"SELECT id,value,text FROM t ORDER BY id",-1,&s,nullptr));Rows out;int rc;while((rc=sqlite3_step(s))==SQLITE_ROW){Row r{};r.key=sqlite3_column_int64(s,0);r.value=sqlite3_column_int64(s,1);const char*t=(const char*)sqlite3_column_text(s,2);need(t&&strlen(t)<32,"SQL text");strcpy(r.text,t);out.emplace(r.key,r);}need(rc==SQLITE_DONE,"SQL scan");sqlok(sqlite3_finalize(s));return out;}
double percentile(std::vector<double>x,double p){std::sort(x.begin(),x.end());return x[std::min(x.size()-1,size_t(p*(x.size()-1)))];}
void faults(fs::path root){for(bool inc:{false,true}){auto b=root/(inc?"inc-fault":"full-fault");need(fs::create_directory(b),"fault root");for(int stage=1;stage<=8;stage++){auto p=b/std::to_string(stage);size_t done=stage>=4?CAP:0;{Engine e(p,128,inc);for(size_t t=0;t<done;t++)e.commit(changes(t,16,128));}pid_t pid=fork();need(pid>=0,"fork");if(!pid){Engine e(p,128,inc);e.commit(changes(done,16,128),stage);_exit(9);}int status;waitpid(pid,&status,0);need(WIFEXITED(status)&&WEXITSTATUS(status)==40+stage,"fault exit");Engine e(p,128,inc);auto old=expected(128,16,done),next=expected(128,16,done+1);if(stage==3)need(e.rows==next,"post-sync lost");else if(stage==2)need(e.rows==old||e.rows==next,"atomicity");else need(e.rows==old,"acknowledged state");}
 auto p=b/"wrap";{Engine e(p,128,inc);for(size_t t=0;t<CAP*3+17;t++)e.commit(changes(t,16,128));}{Engine e(p,128,inc);need(e.rows==expected(128,16,CAP*3+17),"wrap reopen");for(size_t t=CAP*3+17;t<CAP*5+25;t++)e.commit(changes(t,16,128));}{Engine e(p,128,inc);need(e.rows==expected(128,16,CAP*5+25),"continue reopened dirty checkpoints");}
 for(bool manifest:{true}){auto c=b/(manifest?"bad-manifest":"bad-ring");{Engine e(c,128,inc);e.commit(changes(0,16,128));}int f=open((c/(manifest?"manifest":"ring")).c_str(),O_RDWR);char byte;off_t off=manifest?8:sizeof(Head)+3;pr(f,&byte,1,off);byte^=1;pw(f,&byte,1,off);close(f);bool rejected=false;try{Engine e(c,128,inc);}catch(...){rejected=true;}need(rejected,"corruption accepted");}
 auto u=b/"uncertain";{Engine e(u,128,inc);bool failed=false;try{e.commit(changes(0,16,128),0,true);}catch(...){failed=true;}need(failed&&e.poison&&e.rows==fixture(128),"uncertain publish");failed=false;try{e.commit(changes(1,16,128));}catch(...){failed=true;}need(failed,"poison reuse");}{Engine e(u,128,inc);need(e.rows==fixture(128)||e.rows==expected(128,16,1),"uncertain recovery");}
 }std::cout<<"PASS: 16 process-kill boundaries, wrap/reopen/continue, manifest corruption, injected sync failure poison\n";}
int benchmark_main(int argc,char**argv){try{need(argc==3||argc==4,"usage: checkpoint NEW_ROOT COMMITS [check-only]");fs::path root=argv[1];size_t commits=std::stoull(argv[2]);need(commits>=CAP*2,"need wraps");need(fs::create_directory(root),"root must be new");faults(root);if(argc==4)return 0;FILE*out=fopen((root/"raw.jsonl").c_str(),"wx");need(out,"raw output");const char*names[]={"full","incremental","sqlite_128","sqlite_1024","sqlite_1000"};std::cout<<"SQLite "<<sqlite3_libversion()<<" compiler "<<__VERSION__<<" commits "<<commits<<"\n";
 for(size_t n:{10000,100000})for(size_t batch:{1,16,256}){auto want=expected(n,batch,commits);for(int pair=0;pair<5;pair++)for(int phase=0;phase<5;phase++){int c=(pair+phase)%5;auto p=root/("n"+std::to_string(n)+"b"+std::to_string(batch)+"p"+std::to_string(pair)+names[c]);std::vector<double>lat;double maintenance=0,recover=0,total=0;Metrics met{};uint64_t storage=0;std::vector<std::vector<Op>>ops;for(size_t t=0;t<commits;t++)ops.push_back(changes(t,batch,n));
  if(c<2){{Engine e(p,n,c==1);for(auto&v:ops){auto s=Clock::now();e.commit(v);lat.push_back(elapsed(s));}auto s=Clock::now();e.checkpoint();maintenance=elapsed(s);met=e.met;need(e.rows==want,"native final state");}auto s=Clock::now();{Engine e(p,n,c==1);need(e.rows==want,"native reopen state");}recover=elapsed(s);for(auto&x:fs::directory_iterator(p))if(x.is_regular_file())storage+=x.file_size();}
  else{sqlite3*d;sqlok(sqlite3_open(p.c_str(),&d));exec(d,"PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;CREATE TABLE t(id INTEGER PRIMARY KEY,value INTEGER NOT NULL,text TEXT NOT NULL)");exec(d,("PRAGMA wal_autocheckpoint="+std::to_string(c==2?128:(c==3?1024:1000))).c_str());auto f=fixture(n);sqlite3_stmt*insert;sqlok(sqlite3_prepare_v2(d,"INSERT INTO t VALUES(?,?,?)",-1,&insert,nullptr));exec(d,"BEGIN");for(auto&x:f){sqlok(sqlite3_bind_int64(insert,1,x.second.key));sqlok(sqlite3_bind_int64(insert,2,x.second.value));sqlok(sqlite3_bind_text(insert,3,x.second.text,-1,SQLITE_TRANSIENT));need(sqlite3_step(insert)==SQLITE_DONE,"insert");sqlok(sqlite3_reset(insert));}sqlok(sqlite3_finalize(insert));exec(d,"COMMIT");exec(d,"PRAGMA wal_checkpoint(TRUNCATE)");sqlite3_stmt*update,*begin,*end;sqlok(sqlite3_prepare_v2(d,"UPDATE t SET value=value+? WHERE id=?",-1,&update,nullptr));sqlok(sqlite3_prepare_v2(d,"BEGIN IMMEDIATE",-1,&begin,nullptr));sqlok(sqlite3_prepare_v2(d,"COMMIT",-1,&end,nullptr));
   for(auto&v:ops){auto s=Clock::now();need(sqlite3_step(begin)==SQLITE_DONE,"begin");sqlok(sqlite3_reset(begin));for(auto&o:v){sqlok(sqlite3_bind_int64(update,1,o.delta));sqlok(sqlite3_bind_int64(update,2,o.key));need(sqlite3_step(update)==SQLITE_DONE&&sqlite3_changes(d)==1,"actual update");sqlok(sqlite3_reset(update));}need(sqlite3_step(end)==SQLITE_DONE,"commit");sqlok(sqlite3_reset(end));lat.push_back(elapsed(s));}auto s=Clock::now();exec(d,"PRAGMA wal_checkpoint(TRUNCATE)");maintenance=elapsed(s);need(sqlrows(d)==want,"SQLite final state");sqlok(sqlite3_finalize(update));sqlok(sqlite3_finalize(begin));sqlok(sqlite3_finalize(end));sqlok(sqlite3_close(d));s=Clock::now();sqlok(sqlite3_open(p.c_str(),&d));need(sqlrows(d)==want,"SQLite reopen state");sqlok(sqlite3_close(d));recover=elapsed(s);storage=fs::file_size(p);}
  for(auto x:lat)total+=x;fprintf(out,"{\"n\":%zu,\"batch\":%zu,\"pair\":%d,\"candidate\":\"%s\",\"commits\":%zu,\"commit_s\":%.9f,\"final_s\":%.9f,\"recovery_s\":%.9f,\"p95_s\":%.9f,\"p99_s\":%.9f,\"lookup_s\":%.9f,\"encode_s\":%.9f,\"write_s\":%.9f,\"sync_s\":%.9f,\"publish_s\":%.9f,\"checkpoint_s\":%.9f,\"checkpoint_regions\":%llu,\"checkpoint_bytes\":%llu,\"checkpoints\":%llu,\"storage_bytes\":%llu,\"valid\":true}\n",n,batch,pair,names[c],commits,total,maintenance,recover,percentile(lat,.95),percentile(lat,.99),met.lookup,met.encode,met.write,met.sync,met.publish,met.checkpoint,(unsigned long long)met.regions,(unsigned long long)met.cpbytes,(unsigned long long)met.cps,(unsigned long long)storage);fflush(out);std::cout<<n<<" "<<batch<<" "<<pair<<" "<<names[c]<<" "<<total+maintenance<<"\n";
 }}fclose(out);std::cout<<"PASS 150 records, complete final and reopened stored tuples verified\n";return 0;}catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<"\n";return 1;}}

int main(int argc,char**argv){try{need(argc==2,"fresh root required");fs::path root=argv[1];need(fs::create_directory(root),"new root");faults(root);
 for(bool inc:{false,true}){
  for(int stage:{1,2,3,9,10,11,12,13}){auto p=root/(std::string(inc?"inc-":"full-")+"partial-"+std::to_string(stage));size_t done=CAP+7;{Engine e(p,128,inc);for(size_t i=0;i<done;i++)e.commit(changes(i,16,128));}pid_t pid=fork();need(pid>=0,"fork");if(!pid){Engine e(p,128,inc);e.commit(changes(done,16,128),stage);_exit(9);}int st;waitpid(pid,&st,0);need(WIFEXITED(st)&&WEXITSTATUS(st)==40+stage,"partial exit");uint64_t recovered;{Engine e(p,128,inc);auto old=expected(128,16,done),next=expected(128,16,done+1);if(stage==3)need(e.rows==next,"ack lost");else if(stage==2||stage==12||stage==13)need(e.rows==old||e.rows==next,"unack atomic");else need(e.rows==old,"partial ack retention");recovered=e.seq;e.commit(changes(recovered,16,128));}{Engine e(p,128,inc);need(e.seq==recovered+1&&e.rows==expected(128,16,recovered+1),"continue exact reopen");}}
  for(int copy=0;copy<2;copy++)for(int kind=0;kind<3;kind++){auto p=root/(std::string(inc?"inc-":"full-")+"damage-"+std::to_string(copy)+"-"+std::to_string(kind));{Engine e(p,128,inc);for(size_t i=0;i<CAP+7;i++)e.commit(changes(i,16,128));}int f=open((p/"ring").c_str(),O_RDWR);off_t off=(6*COPIES+copy)*SLOT+(kind==0?0:kind==1?sizeof(Head)+3:SLOT-sizeof(Tail));char x;pr(f,&x,1,off);x^=1;pw(f,&x,1,off);need(fdatasync(f)==0,"damage sync");close(f);{Engine e(p,128,inc);need(e.rows==expected(128,16,CAP+7),"single-copy damage lost ack");e.commit(changes(CAP+7,16,128));}{Engine e(p,128,inc);need(e.rows==expected(128,16,CAP+8),"damage continued reopen");}}
 }std::cout<<"PASS 16 original crash stages +16 mid-wrap record stages +12 single-copy corruption cases; one sync per commit; both-copy damage unsupported\n";return 0;
 }catch(const std::exception&e){std::cerr<<"FAIL "<<e.what()<<"\n";return 1;}}
