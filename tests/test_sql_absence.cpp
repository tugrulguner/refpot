#include "../native/relational/sql.hpp"
#include <cassert>
#include <iostream>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

using namespace refpot::sqlpreview;
using Rows = std::vector<std::vector<std::optional<I>>>;

static void expect_rows(Database& db,const std::string& query,const Rows& expected) {
    assert(db.execute(query).rows==expected);
}

template<class F> static void expect_rejected(F&& f) {
    bool rejected=false;
    try { f(); } catch(const std::exception&) { rejected=true; }
    assert(rejected);
}

static void correlated_view_tracks_presence() {
    for(auto mode:{refpot::foundation::Mode::Overlay,refpot::foundation::Mode::Modular}) {
        Database db(mode);
        db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)");
        db.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY)");
        db.execute("INSERT INTO reservations VALUES (1, 7)");
        db.execute("INSERT INTO reservations VALUES (2, 8)");
        db.execute("INSERT INTO resources VALUES (7)");
        db.execute("CREATE MATERIALIZED VIEW missing AS SELECT r.id AS id, r.resource AS resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM resources AS s WHERE s.id = r.resource)");
        expect_rows(db,"SELECT * FROM missing",{{2,8}});

        db.execute("INSERT INTO resources VALUES (8)");
        expect_rows(db,"SELECT * FROM missing",{});
        db.execute("DELETE FROM resources WHERE id = 8");
        expect_rows(db,"SELECT * FROM missing",{{2,8}});
        db.execute("DELETE FROM reservations WHERE id = 2");
        expect_rows(db,"SELECT * FROM missing",{});
        db.execute("INSERT INTO reservations VALUES (3, 8)");
        expect_rows(db,"SELECT * FROM missing",{{3,8}});
        db.execute("INSERT INTO resources VALUES (8)");
        expect_rows(db,"SELECT * FROM missing",{});
    }
}

static void ordinary_select_and_alias_binding() {
    Database db;
    db.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY, parent INTEGER NOT NULL)");
    db.execute("INSERT INTO entries VALUES (1, 1)");
    db.execute("INSERT INTO entries VALUES (2, 3)");
    expect_rows(db,"SELECT child.id AS id FROM entries AS child WHERE NOT EXISTS (SELECT 1 FROM entries AS parent WHERE parent.id = child.parent)",{{2}});
    expect_rows(db,"SELECT child.id AS id FROM entries AS child WHERE NOT EXISTS (SELECT * FROM entries AS parent WHERE child.parent = parent.id)",{{2}});
}

static void derived_bag_duplicates_and_populated_declaration() {
    Database db;
    db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)");
    db.execute("CREATE TABLE resource_observations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)");
    db.execute("INSERT INTO reservations VALUES (1, 7)");
    db.execute("INSERT INTO reservations VALUES (2, 7)");
    db.execute("INSERT INTO resource_observations VALUES (10, 7)");
    db.execute("INSERT INTO resource_observations VALUES (11, 7)");
    db.execute("CREATE MATERIALIZED VIEW repeated_resources AS SELECT resource AS id FROM resource_observations");
    db.execute("CREATE MATERIALIZED VIEW missing AS SELECT r.id AS id, r.resource AS resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM repeated_resources AS s WHERE s.id = r.resource)");
    expect_rows(db,"SELECT * FROM missing",{});
    db.execute("DELETE FROM resource_observations WHERE id = 10");
    expect_rows(db,"SELECT * FROM missing",{});
    db.execute("DELETE FROM resource_observations WHERE id = 11");
    expect_rows(db,"SELECT * FROM missing",{{1,7},{2,7}});
    db.execute("INSERT INTO resource_observations VALUES (12, 7)");
    expect_rows(db,"SELECT * FROM missing",{});
}

static void final_state_assertion_repair_and_rejection() {
    Database db;
    db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)");
    db.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY)");
    db.execute("INSERT INTO reservations VALUES (1, 7)");
    db.execute("INSERT INTO resources VALUES (7)");
    db.execute("CREATE MATERIALIZED VIEW missing AS SELECT r.id AS id, r.resource AS resource FROM reservations AS r WHERE NOT EXISTS (SELECT * FROM resources AS s WHERE s.id = r.resource)");
    db.execute("CREATE ASSERTION no_missing CHECK (NOT EXISTS (SELECT * FROM missing))");
    db.execute("BEGIN");
    db.execute("DELETE FROM resources WHERE id = 7");
    db.execute("INSERT INTO resources VALUES (7)");
    db.execute("COMMIT");
    expect_rows(db,"SELECT * FROM missing",{});

    expect_rejected([&]{db.execute("DELETE FROM resources WHERE id = 7");});
    db.execute("BEGIN");
    db.execute("DELETE FROM resources WHERE id = 7");
    expect_rejected([&]{db.execute("COMMIT");});
    assert(!db.in_transaction());
    expect_rows(db,"SELECT * FROM reservations",{{1,7}});
    expect_rows(db,"SELECT * FROM resources",{{7}});
    expect_rows(db,"SELECT * FROM missing",{});
}

static void rejects_unsupported_correlations_and_nonmutation() {
    Database db;
    db.execute("CREATE TABLE outer_rows (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL)");
    db.execute("CREATE TABLE inner_rows (id INTEGER PRIMARY KEY, other INTEGER NOT NULL)");
    db.execute("INSERT INTO outer_rows VALUES (1, 5)");
    db.execute("INSERT INTO inner_rows VALUES (1, 5)");
    const std::vector<std::string> invalid={
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = i.other)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = 5)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = resource)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS o WHERE o.id = o.resource)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource AND i.other = 5)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource AND i.other = o.resource)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource ORDER BY i.id)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource GROUP BY i.id)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource LIMIT 1)",
        "CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT * FROM inner_rows AS i WHERE i.id = o.resource) AND o.id = 1"
    };
    for(const auto& query:invalid)expect_rejected([&]{db.execute(query);});
    expect_rows(db,"SELECT * FROM outer_rows",{{1,5}});
    expect_rows(db,"SELECT * FROM inner_rows",{{1,5}});

    auto explanation=db.execute("CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT 1 FROM inner_rows AS i WHERE i.id = o.resource)",{},true);
    (void)explanation;
    expect_rows(db,"SELECT * FROM outer_rows",{{1,5}});
    db.execute("CREATE MATERIALIZED VIEW bad AS SELECT o.id AS id FROM outer_rows AS o WHERE NOT EXISTS (SELECT 1 FROM inner_rows AS i WHERE i.id = o.resource)");
    expect_rows(db,"SELECT * FROM bad",{{1}});
}

int main() {
    correlated_view_tracks_presence();
    ordinary_select_and_alias_binding();
    derived_bag_duplicates_and_populated_declaration();
    final_state_assertion_repair_and_rejection();
    rejects_unsupported_correlations_and_nonmutation();
    std::cout << "correlated SQL absence tests passed\n";
}
