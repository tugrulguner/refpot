#include "sql.hpp"
#include <cassert>
#include <iostream>
#include <random>
using namespace refpot::sqlpreview;
template<class F> static void rejects(F f){bool failed=false;try{f();}catch(const std::exception&){failed=true;}assert(failed);}
int main(){
    std::size_t prefixes=0,fuzz=0;
    for(auto mode:{refpot::foundation::Mode::Modular,refpot::foundation::Mode::Overlay}){
        Database db(mode);
        db.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, dept INTEGER NOT NULL, value INTEGER NOT NULL)");
        db.execute("INSERT INTO data VALUES (1, 4, 9)");
        const std::vector<std::string> statements={
            "CREATE TABLE extra (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)",
            "INSERT INTO data VALUES (2, 4, -7)",
            "UPDATE data SET value = 3 WHERE id = 1",
            "SELECT a.dept, COUNT(*) AS n, SUM(b.value) AS total FROM data AS a JOIN data AS b ON a.id = b.id WHERE a.value > 0 GROUP BY a.dept ORDER BY total DESC LIMIT 3"
        };
        for(const auto& q:statements)for(std::size_t n=0;n<q.size();++n){
            // Inspection must bind safely at every truncated boundary without changing state.
            try{db.execute(q.substr(0,n),{},true);}catch(const std::exception&){}
            assert(db.execute("SELECT value FROM data").rows[0][0]==9);++prefixes;
        }
        std::mt19937 rng(104);const std::string alphabet="abcXYZ019?.,;()=!<>-' \n\t";
        for(int i=0;i<2000;++i){std::string q;for(unsigned j=0,n=rng()%100;j<n;++j)q+=alphabet[rng()%alphabet.size()];try{db.execute(q,{},true);}catch(const std::exception&){}++fuzz;}
        rejects([&]{db.execute("SELECT * FROM data WHERE id =");});
        rejects([&]{db.execute("CREATE TABLE broken (id INTEGER PRIMARY KEY,");});
        rejects([&]{db.execute("UPDATE data SET id = 5");});
        rejects([&]{db.execute("SELECT missing FROM data WHERE id < 0");});
        db.execute("BEGIN");db.execute("UPDATE data SET value = 2");
        rejects([&]{db.execute("INSERT INTO data VALUES (1, 7, 1)");});
        assert(!db.in_transaction());assert(db.execute("SELECT value FROM data").rows[0][0]==9);
        db.execute("BEGIN");db.execute("COMMIT");
        db.execute("INSERT INTO data VALUES (2, 4, 8)");
        auto r=db.execute("SELECT a.dept, COUNT(*) AS n, SUM(b.value) AS total FROM data AS a INNER JOIN data AS b ON a.dept = b.dept GROUP BY a.dept ORDER BY total DESC LIMIT 5");
        assert(r.rows.size()==1&&r.rows[0][0]==4&&r.rows[0][1]==4&&r.rows[0][2]==34);
        db.execute("INSERT INTO data VALUES (3, 7, 9223372036854775807)");
        rejects([&]{db.execute("SELECT SUM(value) FROM data");});
        db.execute("INSERT INTO data VALUES (4, 7, -9223372036854775808)");
        assert(db.execute("SELECT SUM(value) FROM data").rows[0][0]==16);
        auto empty=db.execute("SELECT COUNT(*), SUM(value) FROM data WHERE id < 0");
        assert(empty.rows.size()==1&&empty.rows[0][0]==0&&!empty.rows[0][1]);
        db.execute("DELETE FROM data WHERE id > 0");assert(db.execute("SELECT * FROM data").rows.empty());
    }
    std::cout<<"native parser prefixes="<<prefixes<<" seeded malformed strings="<<fuzz<<"\n";
}
