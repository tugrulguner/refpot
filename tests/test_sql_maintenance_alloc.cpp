#include "../native/relational/sql.hpp"

#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <new>
#include <optional>
#include <string>
#include <vector>

namespace {
long fail_after = -1;
long allocation_attempts = 0;

void* allocate(std::size_t size) {
    if (fail_after >= 0 && allocation_attempts++ == fail_after) throw std::bad_alloc();
    if (void* ptr = std::malloc(size ? size : 1)) return ptr;
    throw std::bad_alloc();
}

void* allocate_aligned(std::size_t size, std::size_t alignment) {
    if (fail_after >= 0 && allocation_attempts++ == fail_after) throw std::bad_alloc();
    void* ptr = nullptr;
    if (posix_memalign(&ptr, alignment, size ? size : alignment) == 0) return ptr;
    throw std::bad_alloc();
}

void disarm() noexcept { fail_after = -1; }

using Rows = std::vector<std::vector<std::optional<refpot::sqlpreview::I>>>;

Rows canonical(Rows rows) {
    std::sort(rows.begin(), rows.end());
    return rows;
}

void setup(refpot::sqlpreview::Database& db) {
    db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, k INTEGER NOT NULL, v INTEGER NOT NULL)");
    db.execute("CREATE TABLE limits (id INTEGER PRIMARY KEY, cap INTEGER NOT NULL)");
    db.execute("CREATE TABLE empty_relation (id INTEGER PRIMARY KEY, v INTEGER NOT NULL)");
    db.execute("INSERT INTO source VALUES (1, 7, 3)");
    db.execute("INSERT INTO source VALUES (2, 7, 4)");
    db.execute("INSERT INTO source VALUES (3, 8, 2)");
    db.execute("INSERT INTO limits VALUES (7, 5)");
    db.execute("INSERT INTO limits VALUES (8, 9)");
}

void assert_source(refpot::sqlpreview::Database& db, const Rows& expected) {
    assert(canonical(db.execute("SELECT * FROM source").rows) == canonical(expected));
}

void assert_group(refpot::sqlpreview::Database& db, const Rows& expected) {
    assert(canonical(db.execute("SELECT * FROM grouped").rows) == canonical(expected));
}

void assert_joined(refpot::sqlpreview::Database& db, const Rows& expected) {
    assert(canonical(db.execute("SELECT * FROM matching").rows) == canonical(expected));
}

void assert_limits(refpot::sqlpreview::Database& db) {
    assert(canonical(db.execute("SELECT * FROM limits").rows) == canonical(Rows{{7, 5}, {8, 9}}));
}

void materialized_view_sweeps(refpot::foundation::Mode mode) {
    const Rows source{{1, 7, 3}, {2, 7, 4}, {3, 8, 2}};
    const Rows grouped{{7, 7, 2}, {8, 2, 1}};
    const Rows matching{{7, 3}, {7, 4}, {8, 2}};
    const std::vector<std::string> queries{
        "CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total, COUNT(*) AS n FROM source WHERE v >= 0 GROUP BY k",
        "CREATE MATERIALIZED VIEW matching AS SELECT s.k AS k, s.v AS v FROM source AS s JOIN limits AS l ON s.k = l.id WHERE s.v > 1"
    };
    for (const auto& query : queries) {
        bool reached_success = false;
        long failures = 0;
        for (long cut = 0; cut < 1000 && !reached_success; ++cut) {
            disarm();
            refpot::sqlpreview::Database db(mode);
            setup(db);
            allocation_attempts = 0;
            fail_after = cut;
            bool refused = false;
            try {
                db.execute(query);
            } catch (const std::bad_alloc&) {
                refused = true;
            }
            const long observed_attempts = allocation_attempts;
            disarm();
            if (refused) {
                ++failures;
                assert(observed_attempts == cut + 1);
                // A failed declaration must leave its public name reusable.
                db.execute(query);
                if (query.find("grouped") != std::string::npos) {
                    assert_source(db, source);
                    assert_group(db, grouped);
                } else {
                    assert_source(db, source);
                    assert_joined(db, matching);
                }
            } else {
                assert(observed_attempts <= cut);
                reached_success = true;
                if (query.find("grouped") != std::string::npos) {
                    assert_source(db, source);
                    assert_group(db, grouped);
                } else {
                    assert_source(db, source);
                    assert_joined(db, matching);
                }
            }
        }
        assert(reached_success && failures > 0);
    }
}

void assertion_sweep(refpot::foundation::Mode mode) {
    const std::string query = "CREATE ASSERTION nonempty CHECK (NOT EXISTS (SELECT * FROM empty_relation))";
    bool reached_success = false;
    long failures = 0;
    for (long cut = 0; cut < 1000 && !reached_success; ++cut) {
        disarm();
        refpot::sqlpreview::Database db(mode);
        setup(db);
        db.execute("CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total FROM source GROUP BY k");
        allocation_attempts = 0;
        fail_after = cut;
        bool refused = false;
        try {
            db.execute(query);
        } catch (const std::bad_alloc&) {
            refused = true;
        }
        const long observed_attempts = allocation_attempts;
        disarm();
        if (refused) {
            ++failures;
            assert(observed_attempts == cut + 1);
            db.execute(query);
        } else {
            assert(observed_attempts <= cut);
            reached_success = true;
        }
        assert_source(db, {{1, 7, 3}, {2, 7, 4}, {3, 8, 2}});
        assert_group(db, {{7, 7}, {8, 2}});
        bool duplicate_rejected = false;
        try {
            db.execute(query);
        } catch (const std::invalid_argument&) {
            duplicate_rejected = true;
        }
        assert(duplicate_rejected);
    }
    assert(reached_success && failures > 0);
}

void statement_failure_sweep(refpot::foundation::Mode mode) {
    const std::string query = "INSERT INTO source VALUES (5, 8, 6)";
    const Rows source{{1, 7, 3}, {2, 7, 4}, {3, 8, 2}};
    const Rows grouped{{7, 7, 2}, {8, 2, 1}};
    bool reached_success = false;
    long failures = 0;
    for (long cut = 0; cut < 1000 && !reached_success; ++cut) {
        disarm();
        refpot::sqlpreview::Database db(mode);
        setup(db);
        db.execute("CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total, COUNT(*) AS n FROM source GROUP BY k");
        db.execute("CREATE MATERIALIZED VIEW matching AS SELECT s.k AS k, s.v AS v FROM source AS s JOIN limits AS l ON s.k = l.id WHERE s.v > 1");
        db.execute("BEGIN");
        db.execute("INSERT INTO source VALUES (4, 7, 5)");
        allocation_attempts = 0;
        fail_after = cut;
        bool refused = false;
        try {
            db.execute(query);
        } catch (const std::bad_alloc&) {
            refused = true;
        }
        const long observed_attempts = allocation_attempts;
        disarm();
        if (refused) {
            ++failures;
            assert(observed_attempts == cut + 1);
            assert(!db.in_transaction());
            assert_source(db, source);
            assert_group(db, grouped);
            assert_joined(db, {{7, 3}, {7, 4}, {8, 2}});
            assert_limits(db);
        } else {
            assert(observed_attempts <= cut);
            reached_success = true;
            // Successful explicit-statement path remains in the transaction;
            // abort it to avoid conflating it with the COMMIT sweep below.
            assert(db.in_transaction());
            db.execute("ROLLBACK");
            assert_source(db, source);
            assert_group(db, grouped);
            assert_joined(db, {{7, 3}, {7, 4}, {8, 2}});
            assert_limits(db);
        }
    }
    assert(reached_success && failures > 0);
}

void commit_failure_sweep(refpot::foundation::Mode mode) {
    const std::string query = "COMMIT";
    const Rows source_before{{1, 7, 3}, {2, 7, 4}, {3, 8, 2}};
    const Rows grouped_before{{7, 7, 2}, {8, 2, 1}};
    const Rows source_after{{1, 7, 6}, {3, 8, 2}, {4, 7, 5}};
    const Rows grouped_after{{7, 11, 2}, {8, 2, 1}};
    const Rows joined_before{{7, 3}, {7, 4}, {8, 2}};
    const Rows joined_after{{7, 6}, {7, 5}, {8, 2}};
    bool reached_success = false;
    long failures = 0;
    for (long cut = 0; cut < 1000 && !reached_success; ++cut) {
        disarm();
        refpot::sqlpreview::Database db(mode);
        setup(db);
        db.execute("CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total, COUNT(*) AS n FROM source GROUP BY k");
        db.execute("CREATE MATERIALIZED VIEW matching AS SELECT s.k AS k, s.v AS v FROM source AS s JOIN limits AS l ON s.k = l.id WHERE s.v > 1");
        db.execute("BEGIN");
        db.execute("INSERT INTO source VALUES (4, 7, 5)");
        db.execute("UPDATE source SET v = 6 WHERE id = 1");
        db.execute("DELETE FROM source WHERE id = 2");
        allocation_attempts = 0;
        fail_after = cut;
        bool refused = false;
        try {
            db.execute(query);
        } catch (const std::bad_alloc&) {
            refused = true;
        }
        const long observed_attempts = allocation_attempts;
        disarm();
        if (refused) {
            ++failures;
            assert(observed_attempts == cut + 1);
            assert(!db.in_transaction());
            assert_source(db, source_before);
            assert_group(db, grouped_before);
            assert_joined(db, joined_before);
            assert_limits(db);
        } else {
            assert(observed_attempts <= cut);
            reached_success = true;
            assert(!db.in_transaction());
            assert_source(db, source_after);
            assert_group(db, grouped_after);
            assert_joined(db, joined_after);
            assert_limits(db);
        }
    }
    assert(reached_success && failures > 0);
}
void rejected_commit_sweep(refpot::foundation::Mode mode) {
    bool reached_constraint=false;long failures=0;
    for(long cut=0;cut<1000&&!reached_constraint;++cut) {
        disarm();refpot::sqlpreview::Database db(mode);setup(db);
        db.execute("CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total FROM source GROUP BY k");
        db.execute("CREATE ASSERTION stay_empty CHECK (NOT EXISTS (SELECT * FROM empty_relation))");
        db.execute("BEGIN");db.execute("INSERT INTO empty_relation VALUES (1, 2)");
        const std::string commit="COMMIT";
        allocation_attempts=0;fail_after=cut;
        try {db.execute(commit);assert(false);}
        catch(const std::bad_alloc&){++failures;assert(allocation_attempts==cut+1);}
        catch(const std::logic_error&){reached_constraint=true;}
        disarm();
        assert(!db.in_transaction());
        assert(db.execute("SELECT * FROM empty_relation").rows.empty());
        assert_source(db,{{1,7,3},{2,7,4},{3,8,2}});
        assert_group(db,{{7,7},{8,2}});assert_limits(db);
    }
    assert(reached_constraint&&failures>0);
}

void absence_append_sweep(refpot::foundation::Mode mode) {
    const std::vector<std::string> queries{
        "DELETE FROM limits WHERE id = 8",
        "UPDATE source SET k = 9 WHERE id = 3",
        "INSERT INTO source VALUES (5, 9, 6)"
    };
    for (const auto& query:queries) {
        bool success=false;long failures=0;
        for(long cut=0;cut<2000&&!success;++cut) {
            disarm();refpot::sqlpreview::Database db(mode);setup(db);
            db.execute("CREATE MATERIALIZED VIEW missing AS SELECT s.id, s.k FROM source AS s WHERE NOT EXISTS (SELECT * FROM limits AS l WHERE l.id = s.k)");
            db.execute("CREATE MATERIALIZED VIEW grouped AS SELECT k, SUM(v) AS total, COUNT(*) AS n FROM source GROUP BY k");
            db.execute("CREATE ASSERTION present CHECK (NOT EXISTS (SELECT * FROM missing))");
            db.execute("BEGIN");
            db.execute("INSERT INTO source VALUES (4, 7, 5)");
            db.execute("UPDATE source SET v = 6 WHERE id = 1");
            allocation_attempts=0;fail_after=cut;
            bool refused=false;
            try {db.execute(query);} catch(const std::bad_alloc&){refused=true;}
            const long attempts=allocation_attempts;disarm();
            if(refused) {
                ++failures;assert(attempts==cut+1);assert(!db.in_transaction());
            } else {
                success=true;assert(attempts<=cut);assert(db.in_transaction());
                assert(!db.execute("SELECT * FROM missing").rows.empty());
                db.execute("ROLLBACK");
            }
            assert_source(db,{{1,7,3},{2,7,4},{3,8,2}});
            assert_group(db,{{7,7,2},{8,2,1}});assert_limits(db);
            assert(db.execute("SELECT * FROM missing").rows.empty());
            // Continued usability after every refused allocation, not only final cut.
            db.execute("INSERT INTO source VALUES (6, 8, 1)");
            db.execute("DELETE FROM source WHERE id = 6");
        }
        assert(success&&failures>0);
    }
}

void allocation_free_absence_publication(refpot::foundation::Mode mode) {
    using namespace refpot::foundation;
    Definition left;left.name="left";left.op="source";left.width=2;
    Definition right;right.name="right";right.op="source";right.width=2;
    Definition missing;missing.name="missing";missing.op="anti";
    missing.left="left";missing.right="right";missing.left_key=1;missing.right_key=1;
    Model model({left,right,missing},{"missing"},mode);
    model.prepare({{"insert","left",{1,7},0}},false);
    model.append({{"insert","right",{2,7},0}},false);
    model.append({{"delete","right",{},2}},false);
    model.append({{"insert","right",{3,7},0}},false);
    allocation_attempts=0;fail_after=0;model.commit();
    disarm();assert(allocation_attempts==0);
    assert(model.bag("missing").empty());
    assert((model.bag("right")==Bag{{Row{3,7},1}}));
}

void allocation_free_publication(refpot::foundation::Mode mode) {
    using namespace refpot::foundation;
    Definition source;source.name="source";source.op="source";source.width=2;
    Definition projected;projected.name="projected";projected.op="map";projected.input="source";projected.exprs={{"c0"},{"c1"}};
    Definition negative;negative.name="negative";negative.op="filter";negative.input="projected";negative.column=1;negative.cmp="lt";negative.value=0;
    Model model({source,projected,negative},{"negative"},mode);
    model.prepare({{"insert","source",{1,4},0}},false);
    allocation_attempts=0;fail_after=0;
    model.commit();
    disarm();assert(allocation_attempts==0);
    assert((model.bag("projected")==Bag{{Row{1,4},1}}));
}
}  // namespace

void* operator new(std::size_t size) { return allocate(size); }
void* operator new[](std::size_t size) { return allocate(size); }
void* operator new(std::size_t size, const std::nothrow_t&) noexcept {
    try { return allocate(size); } catch (...) { return nullptr; }
}
void* operator new[](std::size_t size, const std::nothrow_t&) noexcept {
    try { return allocate(size); } catch (...) { return nullptr; }
}
void* operator new(std::size_t size, std::align_val_t alignment) {
    return allocate_aligned(size, static_cast<std::size_t>(alignment));
}
void* operator new[](std::size_t size, std::align_val_t alignment) {
    return allocate_aligned(size, static_cast<std::size_t>(alignment));
}
void* operator new(std::size_t size, std::align_val_t alignment, const std::nothrow_t&) noexcept {
    try { return allocate_aligned(size, static_cast<std::size_t>(alignment)); } catch (...) { return nullptr; }
}
void* operator new[](std::size_t size, std::align_val_t alignment, const std::nothrow_t&) noexcept {
    try { return allocate_aligned(size, static_cast<std::size_t>(alignment)); } catch (...) { return nullptr; }
}
void operator delete(void* ptr) noexcept { std::free(ptr); }
void operator delete[](void* ptr) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete(void* ptr, const std::nothrow_t&) noexcept { std::free(ptr); }
void operator delete[](void* ptr, const std::nothrow_t&) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::align_val_t) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::align_val_t) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::size_t, std::align_val_t) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::size_t, std::align_val_t) noexcept { std::free(ptr); }
void operator delete(void* ptr, std::align_val_t, const std::nothrow_t&) noexcept { std::free(ptr); }
void operator delete[](void* ptr, std::align_val_t, const std::nothrow_t&) noexcept { std::free(ptr); }

int main() {
    for (const auto mode : {refpot::foundation::Mode::Overlay, refpot::foundation::Mode::Modular}) {
        materialized_view_sweeps(mode);
        assertion_sweep(mode);
        statement_failure_sweep(mode);
        commit_failure_sweep(mode);
        rejected_commit_sweep(mode);
        allocation_free_publication(mode);
        absence_append_sweep(mode);
        allocation_free_absence_publication(mode);
    }
    std::cout << "SQL maintenance allocation-failure sweeps passed\n";
}
