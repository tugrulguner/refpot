#include "../native/relational/sql.hpp"
#include <cassert>
#include <iostream>
using namespace refpot::sqlpreview;
int main() {
    Database db;
    db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL)");
    db.execute("INSERT INTO reservations VALUES (1, 7, 3)");
    db.execute("CREATE MATERIALIZED VIEW usage AS SELECT resource, SUM(units) AS total, COUNT(*) AS n FROM reservations GROUP BY resource");
    auto result=db.execute("SELECT * FROM usage");
    assert((result.rows==std::vector<std::vector<std::optional<I>>>{{7,3,1}}));
    db.execute("BEGIN");
    db.execute("INSERT INTO reservations VALUES (2, 7, 4)");
    assert((db.execute("SELECT * FROM usage").rows==std::vector<std::vector<std::optional<I>>>{{7,7,2}}));
    db.execute("ROLLBACK");
    assert((db.execute("SELECT * FROM usage").rows==std::vector<std::vector<std::optional<I>>>{{7,3,1}}));
    bool rejected=false;
    try { db.execute("DELETE FROM usage WHERE resource = 7"); } catch (const std::invalid_argument&) { rejected=true; }
    assert(rejected);
    for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}) {
        Database capacity(mode);
        capacity.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY, capacity INTEGER NOT NULL)");
        capacity.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL)");
        capacity.execute("INSERT INTO resources VALUES (7, 5)");
        capacity.execute("INSERT INTO reservations VALUES (1, 7, 3)");
        capacity.execute("CREATE MATERIALIZED VIEW usage AS SELECT resource, SUM(units) AS total FROM reservations GROUP BY resource");
        capacity.execute("CREATE MATERIALIZED VIEW violations AS SELECT u.resource AS resource, u.total AS total, r.capacity AS capacity FROM usage AS u JOIN resources AS r ON u.resource = r.id WHERE u.total > r.capacity");
        capacity.execute("CREATE ASSERTION within_capacity CHECK (NOT EXISTS (SELECT * FROM violations))");
        capacity.execute("BEGIN");
        capacity.execute("INSERT INTO reservations VALUES (2, 7, 4)");
        assert(capacity.execute("SELECT * FROM violations").rows.size()==1);
        capacity.execute("UPDATE resources SET capacity = 7 WHERE id = 7");
        assert(capacity.execute("SELECT * FROM violations").rows.empty());
        capacity.execute("COMMIT");
        capacity.execute("BEGIN");
        capacity.execute("UPDATE resources SET capacity = 1 WHERE id = 7");
        bool failed=false;
        try {capacity.execute("COMMIT");}catch(const std::logic_error&){failed=true;}
        assert(failed&&!capacity.in_transaction());
        assert((capacity.execute("SELECT * FROM resources").rows==std::vector<std::vector<std::optional<I>>>{{7,7}}));
        assert((capacity.execute("SELECT * FROM usage").rows==std::vector<std::vector<std::optional<I>>>{{7,7}}));
        assert(capacity.execute("SELECT * FROM violations").rows.empty());
        failed=false;
        try {capacity.execute("UPDATE reservations SET units = 8 WHERE id = 1");}catch(const std::logic_error&){failed=true;}
        assert(failed);
        assert((capacity.execute("SELECT * FROM usage").rows==std::vector<std::vector<std::optional<I>>>{{7,7}}));
    }
    for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}) {
        Database bags(mode);
        bags.execute("CREATE TABLE input (id INTEGER PRIMARY KEY, k INTEGER NOT NULL, v INTEGER NOT NULL)");
        bags.execute("INSERT INTO input VALUES (1, 7, 3)");
        bags.execute("INSERT INTO input VALUES (2, 7, 3)");
        bags.execute("CREATE MATERIALIZED VIEW projected AS SELECT k, v FROM input");
        assert((bags.execute("SELECT * FROM projected").rows==std::vector<std::vector<std::optional<I>>>{{7,3},{7,3}}));
        assert((bags.execute("SELECT k, SUM(v), COUNT(*) FROM projected GROUP BY k").rows==std::vector<std::vector<std::optional<I>>>{{7,6,2}}));
        bags.execute("CREATE MATERIALIZED VIEW multiplied AS SELECT a.k AS k, a.v AS v FROM projected AS a JOIN projected AS b ON a.k = b.k");
        assert(bags.execute("SELECT * FROM multiplied").rows.size()==4);
        assert((bags.execute("SELECT COUNT(*) FROM projected AS a JOIN projected AS b ON a.k = b.k").rows==std::vector<std::vector<std::optional<I>>>{{4}}));
        bags.execute("BEGIN");
        bags.execute("DELETE FROM input WHERE id = 1");
        assert(bags.execute("SELECT * FROM multiplied").rows.size()==1);
        bags.execute("ROLLBACK");
        assert(bags.execute("SELECT * FROM multiplied").rows.size()==4);
        bags.execute("UPDATE input SET k = 8 WHERE id = 2");
        assert(bags.execute("SELECT * FROM multiplied").rows.size()==2);
        bags.execute("DELETE FROM input WHERE id = 1");
        assert((bags.execute("SELECT * FROM multiplied").rows==std::vector<std::vector<std::optional<I>>>{{8,3}}));
    }
    for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}) {
        Database bounded(mode);
        bounded.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, k INTEGER NOT NULL)");
        for(int i=0;i<316;++i)bounded.execute("INSERT INTO source VALUES (?, 1)",{i});
        bounded.execute("CREATE MATERIALIZED VIEW same AS SELECT k FROM source");
        bounded.execute("CREATE MATERIALIZED VIEW product AS SELECT a.k AS k FROM same AS a JOIN same AS b ON a.k = b.k");
        assert((bounded.execute("SELECT COUNT(*) FROM product").rows==std::vector<std::vector<std::optional<I>>>{{99856}}));
        bool failed=false;
        try{bounded.execute("INSERT INTO source VALUES (316, 1)");}catch(const std::exception&){failed=true;}
        assert(failed);
        assert((bounded.execute("SELECT COUNT(*) FROM source").rows==std::vector<std::vector<std::optional<I>>>{{316}}));
        assert((bounded.execute("SELECT COUNT(*) FROM product").rows==std::vector<std::vector<std::optional<I>>>{{99856}}));
    }
    std::cout << "maintained SQL native tests passed\n";
}
