#include "../../native/relational/sql.hpp"
#include <cassert>
#include <cstdlib>
#include <new>
#include <limits>
static std::size_t remaining=std::numeric_limits<std::size_t>::max();
static void disarm(){remaining=std::numeric_limits<std::size_t>::max();}
void* operator new(std::size_t n){if(remaining!=std::numeric_limits<std::size_t>::max()){if(!remaining)throw std::bad_alloc();--remaining;}if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void* operator new[](std::size_t n){return ::operator new(n);}
void operator delete(void* p) noexcept{std::free(p);}
void operator delete[](void* p) noexcept{std::free(p);}
void operator delete(void* p,std::size_t) noexcept{std::free(p);}
void operator delete[](void* p,std::size_t) noexcept{std::free(p);}
void* operator new(std::size_t n,const std::nothrow_t&) noexcept{try{return ::operator new(n);}catch(...){return nullptr;}}
void* operator new[](std::size_t n,const std::nothrow_t&) noexcept{try{return ::operator new[](n);}catch(...){return nullptr;}}
void operator delete(void* p,const std::nothrow_t&) noexcept{std::free(p);}
void operator delete[](void* p,const std::nothrow_t&) noexcept{std::free(p);}
int main(){
 using refpot::sqlpreview::Database;
 const std::string query="SELECT value FROM items WHERE value > 7";
 const std::string old="SELECT value FROM items WHERE value > 2";
 std::size_t failures=0;bool reached_success=false;
 for(std::size_t nth=0;nth<2000;++nth){
  Database db;db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
  db.execute("INSERT INTO items VALUES (1, 9)");db.execute("CREATE MATERIALIZED VIEW eligible AS SELECT value FROM items WHERE value > 2");
  assert(db.execute(old).plan.find("MAINTAINED_REUSE")!=std::string::npos);
  db.execute("ALTER MATERIALIZED VIEW eligible AS SELECT value FROM items WHERE value > 7");
  remaining=nth;
  try{auto result=db.execute(query);disarm();assert(result.rows.size()==1);reached_success=true;}
  catch(const std::bad_alloc&){disarm();++failures;}
  // A failed rebuild cannot make the old index current, poison the owner,
  // change data, or prevent retry from building a complete replacement.
  assert(db.execute(query).plan.find("MAINTAINED_REUSE eligible")!=std::string::npos);
  assert(db.execute(old).plan.find("MAINTAINED_REUSE")==std::string::npos);
  assert(db.execute("SELECT * FROM items").rows.size()==1);
  if(reached_success)break;
 }
 assert(reached_success&&failures>20);
}
