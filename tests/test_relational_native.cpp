#include "../native/relational/sql.hpp"
#include <cassert>
#include <iostream>
#include <cstdlib>
#include <new>
static long fail_at=-1, allocations=0;
void* operator new(std::size_t n) {
  if(fail_at>=0 && allocations++==fail_at) throw std::bad_alloc();
  if(void* p=std::malloc(n?n:1)) return p; throw std::bad_alloc();
}
void operator delete(void* p) noexcept {std::free(p);}
void operator delete(void* p,std::size_t) noexcept {std::free(p);}
using namespace refpot::sqlpreview;
static void failure_sweeps() {
  for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}) {
    for(const std::string query:{"CREATE TABLE b (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)",
                                "UPDATE a SET value = 9 WHERE id = 1", "COMMIT"}) {
      bool complete=false; long cuts=0;
      for(long n=0;n<1000 && !complete;++n) {
        fail_at=-1;
        Database db(mode,3);
        db.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        db.execute("INSERT INTO a VALUES (1, 10)");
        const bool tx=query[0]!='C' || query=="COMMIT";
        if(tx){db.execute("BEGIN");db.execute("INSERT INTO a VALUES (2, 20)");}
        allocations=0;fail_at=n;
        try {db.execute(query);fail_at=-1;complete=true;}
        catch(const std::bad_alloc&) {
          fail_at=-1;++cuts;
          assert(!db.in_transaction());
          assert(db.execute("SELECT * FROM a").rows.size()==1);
          assert(db.execute("SELECT value FROM a").rows[0][0]==10);
          if(!tx)db.execute("CREATE TABLE b (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)");
          db.execute("INSERT INTO a VALUES (3, 30)");
        }
        if(complete && tx && query!="COMMIT")db.execute("COMMIT");
      }
      assert(complete && cuts>0);
      std::cout<<"allocation cuts: "<<query<<" "<<cuts<<"\n";
    }
    Database db(mode,3);
    db.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)");
    db.execute("CREATE TABLE b (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)");
    db.execute("INSERT INTO a VALUES (1, 1)");db.execute("INSERT INTO a VALUES (2, 2)");
    db.execute("INSERT INTO b VALUES (1, 3)");
    db.execute("BEGIN");db.execute("DELETE FROM a WHERE id = 1");
    db.execute("INSERT INTO b VALUES (2, 4)");db.execute("ROLLBACK");
    bool rejected=false;try{db.execute("INSERT INTO b VALUES (2, 4)");}catch(...){rejected=true;}
    assert(rejected && db.execute("SELECT COUNT(*) FROM a").rows[0][0]==2);
  }
}
static void shared_operators() {
  using namespace refpot::foundation;
  Definition a; a.name="a";a.op="source";a.width=3;
  Definition f;f.name="f";f.op="filter";f.input="a";f.column=2;f.cmp="ge";f.value=0;
  Definition g;g.name="g";g.op="group";g.input="f";g.key=1;g.value_column=2;
  for(auto mode:{Mode::Overlay,Mode::Modular}) {
    Model model({a,f,g},{},mode);
    model.prepare({{"insert","a",{1,7,10},0}});
    model.append({{"insert","a",{2,7,20},0}});
    assert(model.preview().at("g").count({7,30,2}));
    model.append({{"update","a",{1,7,-1},0}});
    assert(model.preview().at("g").count({7,20,1}));
    model.append({{"delete","a",{},2},{"update","a",{1,7,10},0}});
    model.commit();assert(model.bag("g").count({7,10,1}));
    Database db(mode);
    db.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, dept INTEGER NOT NULL, value INTEGER NOT NULL)");
    db.execute("INSERT INTO a VALUES (1,7,10)");
    const auto result=db.execute("SELECT dept,SUM(value),COUNT(*) FROM a WHERE value >= 0 GROUP BY dept");
    assert(result.rows.size()==1 && result.rows[0][0]==7 && result.rows[0][1]==10 && result.rows[0][2]==1);
  }
}
int main() {
  shared_operators();
  failure_sweeps();
  for (auto mode : {refpot::foundation::Mode::Overlay, refpot::foundation::Mode::Modular}) {
    Database db(mode);
    db.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    db.execute("INSERT INTO a VALUES (1, 10)");
    auto before=db.stats();
    db.execute("CREATE TABLE b (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    assert(db.stats().at("catalog_copied_rows")==before.at("catalog_copied_rows"));
    db.execute("INSERT INTO a VALUES (2, 20)");
    db.execute("INSERT INTO a VALUES (3, 30)");
    auto stats=db.stats();
    assert(stats.at("statement_mutations")==3);
    assert(stats.at("prior_mutation_replays")==0);
    assert(stats.at("catalog_copied_rows")==0);
    db.execute("BEGIN"); db.execute("INSERT INTO b VALUES (10, 1)"); db.execute("INSERT INTO b VALUES (11, 2)");
    assert(db.stats().at("prior_mutation_replays")==0);
    assert(db.stats().at("candidate_copied_entries")==0);
    db.execute("COMMIT");
    assert(db.execute("SELECT count(*) FROM b").rows[0][0]==std::optional<I>(2));
    auto bound_before=db.stats();
    assert(db.execute("SELECT SUM(value) FROM a WHERE value >= 10").rows[0][0]==60);
    auto bound_after=db.stats();
    assert(bound_after.at("predicate_bindings")==bound_before.at("predicate_bindings")+1);
    assert(bound_after.at("predicate_tests")==bound_before.at("predicate_tests")+3);
    auto r=db.execute("SELECT id, value FROM a ORDER BY id");
    assert(r.rows.size()==3 && r.rows[2][0]==3);
    db.execute("BEGIN"); db.execute("INSERT INTO b VALUES (1, 7)");
    bool failed=false; try { db.execute("INSERT INTO b VALUES (1, 8)"); } catch(...) {failed=true;}
    assert(failed && !db.in_transaction());
    assert(db.execute("SELECT count(*) FROM b").rows[0][0]==std::optional<I>(2));
    db.execute("BEGIN"); db.execute("INSERT INTO b VALUES (2, 9)"); db.rollback();
    assert(db.execute("SELECT count(*) FROM b").rows[0][0]==std::optional<I>(2));
  }
  std::cout << "relational native regression passed\n";
}
