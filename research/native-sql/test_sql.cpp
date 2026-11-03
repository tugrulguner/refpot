#include "sql.hpp"
#include <cassert>
#include <iostream>
using namespace refpot::sqlpreview;
int main() {
 Database db; db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
 db.execute("INSERT INTO items VALUES (?, ?)", {1,7});
 auto r=db.execute("SELECT id, value FROM items WHERE id = ?", {1});
 assert((r.columns==std::vector<std::string>{"id","value"})); assert(r.rows.size()==1 && r.rows[0][0]==1 && r.rows[0][1]==7);
 bool bad=false; try { db.execute("SELECT id FROM items; SELECT id FROM items"); } catch(...) {bad=true;} assert(bad);
 std::cout << "native SQL smoke tests passed\n";
}
