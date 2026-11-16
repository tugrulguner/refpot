#include "../../native/relational/sql.hpp"
#include <cassert>
int main(){
 refpot::sqlpreview::Database db;
 db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)");
 db.execute("INSERT INTO items VALUES (1, 9)");
 for(int i=0;i<100;++i)db.execute("CREATE MATERIALIZED VIEW view"+std::to_string(i)+" AS SELECT amount FROM items WHERE amount > "+std::to_string(i));
 db.execute("SELECT amount FROM items WHERE amount > 98");
 auto visits=db.stats().at("reuse_definition_visits");assert(visits>0);
 for(int i=0;i<20;++i){db.execute("SELECT amount FROM items WHERE amount > 98");db.execute("SELECT amount FROM items WHERE amount > 101");}
 assert(db.stats().at("reuse_definition_visits")==visits);
 db.execute("ALTER MATERIALIZED VIEW view98 AS SELECT amount FROM items WHERE amount > 102");
 assert(db.execute("SELECT amount FROM items WHERE amount > 98").plan.find("MAINTAINED_REUSE")==std::string::npos);
 assert(db.execute("SELECT amount FROM items WHERE amount > 102").plan.find("MAINTAINED_REUSE view98")!=std::string::npos);
 assert(db.stats().at("reuse_definition_visits")>visits);
}
