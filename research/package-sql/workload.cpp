#include <atomic>
#include <cstdlib>
#include <new>
#include <iostream>
#include <string>
#include <vector>
#include <optional>
#include <stdexcept>
#include <cstdint>
#ifdef PACKAGE_SQL_NEW
#include "../../native/relational/sql.hpp"
#else
#include "../native-sql/sql.hpp"
#endif

namespace allocation_counter {
thread_local bool enabled=false;
thread_local std::uint64_t calls=0, bytes=0;
void* allocate(std::size_t n) {
    if (enabled) { ++calls; bytes+=n; }
    if (void* p=std::malloc(n?n:1)) return p;
    throw std::bad_alloc();
}
}
void* operator new(std::size_t n) { return allocation_counter::allocate(n); }
void* operator new[](std::size_t n) { return allocation_counter::allocate(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
void operator delete[](void* p,std::size_t) noexcept { std::free(p); }

using namespace refpot::sqlpreview;
static std::string esc(const std::string& s) { std::string o="\""; for(char c:s){if(c=='\\'||c=='\"')o+='\\';if(c=='\n')o+="\\n";else o+=c;} return o+'"'; }
struct Op {std::string sql; std::uint64_t calls,bytes; std::size_t affected;};
static std::vector<Op> ops;
static Result run(Database& db,const std::string& q) {
 allocation_counter::calls=allocation_counter::bytes=0; allocation_counter::enabled=true;
 Result r; try {r=db.execute(q);} catch(...) {allocation_counter::enabled=false;throw;}
 allocation_counter::enabled=false; ops.push_back({q,allocation_counter::calls,allocation_counter::bytes,r.affected}); return r;
}
static std::string mode_name(const std::string& s){return s;}
int main(int argc,char**argv) try {
 if(argc!=4) throw std::runtime_error("usage: workload MODE SIZE CASE");
 std::string mode=argv[1], test=argv[3]; int n=std::stoi(argv[2]);
 Database db(mode=="overlay"?refpot::foundation::Mode::Overlay:refpot::foundation::Mode::Modular);
 run(db,"CREATE TABLE records (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
 for(int i=1;i<=n;++i)run(db,"INSERT INTO records VALUES ("+std::to_string(i)+", "+std::to_string(i*3)+")");
 bool own_write=false, rollback_ok=false;
 if(test=="repeated-key") {
   run(db,"BEGIN"); int rounds=n==32?16:64;
   for(int j=1;j<=rounds;++j)run(db,"UPDATE records SET value = "+std::to_string(1000+j)+" WHERE id = 1");
   auto r=run(db,"SELECT value FROM records WHERE id = 1");
   own_write=r.rows.size()==1&&r.rows[0][0]&&*r.rows[0][0]==1000+rounds;
   if(!own_write)throw std::runtime_error("read-your-writes failed in repeated-key");
   run(db,"COMMIT");
 } else if(test=="growing-key") {
   run(db,"BEGIN"); int add=n;
   for(int j=1;j<=add;++j)run(db,"INSERT INTO records VALUES ("+std::to_string(n+j)+", "+std::to_string(9000+j)+")");
   auto r=run(db,"SELECT COUNT(*) FROM records");
   own_write=r.rows.size()==1&&r.rows[0][0]&&*r.rows[0][0]==2*n;
   if(!own_write)throw std::runtime_error("read-your-writes failed in growing-key");
   run(db,"COMMIT");
   run(db,"BEGIN");
   for(int j=1;j<=8;++j)run(db,"INSERT INTO records VALUES ("+std::to_string(2*n+j)+", "+std::to_string(12000+j)+")");
   auto rb=run(db,"SELECT COUNT(*) FROM records");
   if(!rb.rows[0][0]||*rb.rows[0][0]!=2*n+8)throw std::runtime_error("rollback read-your-writes failed");
   run(db,"ROLLBACK");
   auto after=run(db,"SELECT COUNT(*) FROM records"); rollback_ok=after.rows.size()==1&&after.rows[0][0]&&*after.rows[0][0]==2*n;
   if(!rollback_ok)throw std::runtime_error("rollback state mismatch");
 } else if(test=="create-populated") {
   run(db,"CREATE TABLE second (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
   for(int i=1;i<=n;++i)run(db,"INSERT INTO second VALUES ("+std::to_string(i)+", "+std::to_string(i*7)+")");
   run(db,"CREATE TABLE late (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
   run(db,"INSERT INTO late VALUES (1, 42)");
   auto visible=run(db,"SELECT value FROM late WHERE id = 1");
   own_write=visible.rows.size()==1&&visible.rows[0][0]&&*visible.rows[0][0]==42;
   if(!own_write)throw std::runtime_error("read-your-writes failed after CREATE");
 } else throw std::runtime_error("unknown case");
 auto state=run(db,"SELECT * FROM records ORDER BY id");
 if(state.rows.size()!=static_cast<std::size_t>(n+(test=="growing-key"?n:0)))throw std::runtime_error("final row count mismatch");
 for(std::size_t i=0;i<state.rows.size();++i){
   I expected_id=static_cast<I>(i+1), expected_value=expected_id*3;
   if(test=="repeated-key"&&i==0)expected_value=(n==32?1016:1064);
   if(test=="growing-key"&&i>=static_cast<std::size_t>(n))expected_value=9000+static_cast<I>(i-n+1);
   if(!state.rows[i][0]||!state.rows[i][1]||*state.rows[i][0]!=expected_id||*state.rows[i][1]!=expected_value)throw std::runtime_error("final record mismatch");
 }
 if(test=="create-populated") {
   auto s2=run(db,"SELECT * FROM second ORDER BY id");
   if(s2.rows.size()!=static_cast<std::size_t>(n))throw std::runtime_error("second table lost rows after CREATE");
   for(int i=0;i<n;++i)if(!s2.rows[i][0]||!s2.rows[i][1]||*s2.rows[i][0]!=i+1||*s2.rows[i][1]!=(i+1)*7)throw std::runtime_error("second-table row mismatch");
   auto s3=run(db,"SELECT * FROM late ORDER BY id");if(s3.rows.size()!=1||!s3.rows[0][0]||!s3.rows[0][1]||*s3.rows[0][0]!=1||*s3.rows[0][1]!=42)throw std::runtime_error("late-table state mismatch");
 }
 std::cout<<"{\"mode\":"<<esc(mode)<<",\"size\":"<<n<<",\"case\":"<<esc(test)<<",\"control\":"<<esc(
#ifdef PACKAGE_SQL_NEW
 "package"
#else
 "baseline"
#endif
 )<<",\"read_your_writes\":"<<(own_write?"true":"false")<<",\"rollback_verified\":"<<(rollback_ok?"true":"false")<<",\"final_rows\":[";
 for(std::size_t i=0;i<state.rows.size();++i){if(i)std::cout<<',';std::cout<<'['<<*state.rows[i][0]<<','<<*state.rows[i][1]<<']';}
 std::cout<<"],\"final_tables\":{\"records\":[";
 for(std::size_t i=0;i<state.rows.size();++i){if(i)std::cout<<',';std::cout<<'['<<*state.rows[i][0]<<','<<*state.rows[i][1]<<']';}
 std::cout<<']';
 if(test=="create-populated") {
   auto s2=run(db,"SELECT * FROM second ORDER BY id"); auto s3=run(db,"SELECT * FROM late ORDER BY id");
   std::cout<<",\"second\":[";for(std::size_t i=0;i<s2.rows.size();++i){if(i)std::cout<<',';std::cout<<'['<<*s2.rows[i][0]<<','<<*s2.rows[i][1]<<']';}
   std::cout<<"],\"late\":[";for(std::size_t i=0;i<s3.rows.size();++i){if(i)std::cout<<',';std::cout<<'['<<*s3.rows[i][0]<<','<<*s3.rows[i][1]<<']';}std::cout<<']';
 }
 std::cout<<"},\"operations\":[";
 for(std::size_t i=0;i<ops.size();++i){if(i)std::cout<<',';const auto&o=ops[i];std::cout<<"{\"sql\":"<<esc(o.sql)<<",\"new_calls\":"<<o.calls<<",\"requested_bytes\":"<<o.bytes<<",\"affected\":"<<o.affected<<'}';}
 std::cout<<"]}\n"; return 0;
} catch(const std::exception&e){std::cerr<<"FAIL: "<<e.what()<<'\n';return 1;}
