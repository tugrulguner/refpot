#include "../../native/relational/sql.hpp"
#include <cassert>
#include <filesystem>
#include <string>
using namespace refpot::sqlpreview;
using Rows=std::vector<std::vector<std::optional<I>>>;
static void rows(Database& db,const std::string& q,Rows want){auto got=db.execute(q).rows;std::sort(got.begin(),got.end());std::sort(want.begin(),want.end());assert(got==want);}
static bool fails(Database& db,const std::string& q,const std::vector<I>& p={}){try{db.execute(q,p);return false;}catch(const std::exception&){return true;}}
static std::size_t tests(Database& db){return db.stats().at("predicate_tests");}
static void ordinary_modes(){
 for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}){
  Database db(mode);
  db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL, floor INTEGER NOT NULL)");
  db.execute("INSERT INTO items VALUES (1, 4, 2)");db.execute("INSERT INTO items VALUES (2, 4, 1)");db.execute("INSERT INTO items VALUES (3, 1, 0)");
  db.execute("CREATE MATERIALIZED VIEW eligible AS SELECT amount AS value FROM items AS source WHERE amount > 2");
  auto check=[&](const std::string& q,const Rows& expected,bool reuse){auto before=tests(db);auto r=db.execute(q);assert(r.rows==expected);assert(((r.plan.find("MAINTAINED_REUSE eligible")!=std::string::npos)==reuse) && q.c_str());assert((tests(db)==before)==reuse);};
  check("SELECT amount AS value FROM items AS i WHERE amount > 2",{{4},{4}},true);
  check("SELECT amount AS value FROM items AS i WHERE amount > 2 ORDER BY value",{{4},{4}},true);
  check("SELECT amount FROM items WHERE amount > 2",{{4},{4}},true);
  check("SELECT amount AS value FROM items WHERE amount >= 2",{{4},{4}},false);
  check("SELECT amount AS value FROM items WHERE amount > 1",{{4},{4}},false);
  check("SELECT floor AS value FROM items WHERE amount > 2",{{2},{1}},false);
  check("SELECT amount AS value FROM items WHERE amount > 2 ORDER BY value DESC",{{4},{4}},true);
  check("SELECT amount AS value FROM items WHERE amount > 2 LIMIT 1",{{4}},true);
  check("SELECT amount AS value FROM items AS other WHERE amount > 2",{{4},{4}},true);
  auto before=tests(db);auto explain=db.execute("SELECT amount AS value FROM items WHERE amount > 2",{},true);assert(explain.plan.find("MAINTAINED_REUSE eligible")!=std::string::npos&&tests(db)==before);
  before=tests(db);assert((db.execute("SELECT amount AS value FROM items WHERE amount > ?",{2}).rows==Rows{{4},{4}}));assert(tests(db)==before);
  assert(fails(db,"SELECT missing AS value FROM items WHERE amount > 2"));
  assert(fails(db,"SELECT amount AS value FROM items WHERE amount > 2 AND missing = 1"));
  db.execute("BEGIN");db.execute("UPDATE items SET amount = 8 WHERE id = 1");before=tests(db);rows(db,"SELECT amount AS value FROM items WHERE amount > 2",{{8},{4}});assert(tests(db)>before);db.execute("ROLLBACK");check("SELECT amount AS value FROM items WHERE amount > 2",{{4},{4}},true);
  db.execute("BEGIN");db.execute("UPDATE items SET amount = 8 WHERE id = 1");db.execute("COMMIT");rows(db,"SELECT amount AS value FROM items WHERE amount > 2",{{8},{4}});
  db.execute("INSERT INTO items VALUES (4, 9, 3)");rows(db,"SELECT amount AS value FROM items WHERE amount > 2",{{8},{4},{9}});db.execute("DELETE FROM items WHERE id = 2");rows(db,"SELECT amount AS value FROM items WHERE amount > 2",{{8},{9}});
  db.execute("ALTER MATERIALIZED VIEW eligible AS SELECT amount AS value FROM items WHERE amount > 7");before=tests(db);auto altered=db.execute("SELECT amount AS value FROM items WHERE amount > 7");assert((altered.rows==Rows{{8},{9}}&&altered.plan.find("MAINTAINED_REUSE eligible")!=std::string::npos&&tests(db)==before));
  before=tests(db);auto absent=db.execute("SELECT amount AS value FROM items WHERE amount > 2");assert((absent.rows==Rows{{8},{9}}&&absent.plan.find("MAINTAINED_REUSE")==std::string::npos&&tests(db)>before));
  assert(fails(db,"SELECT amount AS value FROM items WHERE amount > ?",{}));
 }
}
static void persistent(){auto path=std::filesystem::temp_directory_path()/"refpot-query-reuse-regression.db";for(auto s:{"",".wal",".lock",".tmp"})std::filesystem::remove(path.string()+s);{Database db(path.string());db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)");db.execute("INSERT INTO items VALUES (1, 4)");db.execute("CREATE MATERIALIZED VIEW eligible AS SELECT amount AS value FROM items WHERE amount > 2");db.execute("INSERT INTO items VALUES (2, 8)");db.checkpoint();}{Database db(path.string());auto before=tests(db);auto r=db.execute("SELECT amount AS value FROM items WHERE amount > 2");assert((r.rows==Rows{{4},{8}}&&r.plan.find("MAINTAINED_REUSE eligible")!=std::string::npos&&tests(db)==before));}for(auto s:{"",".wal",".lock",".tmp"})std::filesystem::remove(path.string()+s);}
static void semantic_controls(){
 Database db;
 db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, a INTEGER NOT NULL, b INTEGER NOT NULL)");
 db.execute("CREATE TABLE other (id INTEGER PRIMARY KEY, a INTEGER NOT NULL, b INTEGER NOT NULL)");
 db.execute("INSERT INTO source VALUES (1, 7, 2)");db.execute("INSERT INTO source VALUES (2, 3, 5)");
 db.execute("INSERT INTO other VALUES (1, 9, 1)");
 db.execute("CREATE MATERIALIZED VIEW matched AS SELECT b, a FROM source WHERE a > b AND b > 0");
 auto before=tests(db);auto result=db.execute("SELECT b AS second, a AS first FROM source WHERE a > b AND b > ? ORDER BY first DESC",{0});
 assert((result.rows==Rows{{2,7}}));assert((result.columns==std::vector<std::string>{"second","first"}));assert(tests(db)==before);
 before=tests(db);result=db.execute("SELECT b, a FROM source WHERE a > 2 AND b > 0 ORDER BY a");assert((result.rows==Rows{{5,3},{2,7}}));assert(tests(db)>before);
 before=tests(db);result=db.execute("SELECT b, a FROM other WHERE a > b AND b > 0");assert((result.rows==Rows{{1,9}}));assert(tests(db)>before);
 before=tests(db);result=db.execute("SELECT a, b FROM source WHERE a > b AND b > 0");assert((result.rows==Rows{{7,2}}));assert(tests(db)>before);
 before=tests(db);result=db.execute("SELECT b, a FROM source WHERE b > 0 AND a > b");assert((result.rows==Rows{{2,7}}));assert(tests(db)>before);
 const auto context=db.query_context({"source"});
 before=tests(db);result=db.execute_readonly("SELECT b, a FROM source WHERE a > b AND b > 0",{},{"source"},context.revision);
 assert((result.rows==Rows{{2,7}}));assert(tests(db)>before);assert(result.plan.find("matched")==std::string::npos);
}
int main(){ordinary_modes();persistent();semantic_controls();}
