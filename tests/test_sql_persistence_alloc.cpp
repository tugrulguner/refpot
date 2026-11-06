#include "../native/relational/sql.hpp"

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <memory>
#include <new>
#include <optional>
#include <string>
#include <unistd.h>
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

std::filesystem::path fresh_path() {
    std::string pattern = (std::filesystem::temp_directory_path() / "refpot-sql-alloc-XXXXXX").string();
    std::vector<char> writable(pattern.begin(), pattern.end());
    writable.push_back('\0');
    char* dir = ::mkdtemp(writable.data());
    assert(dir != nullptr);
    return std::filesystem::path(dir) / "db";
}

using Mode = refpot::foundation::Mode;
using Database = refpot::sqlpreview::Database;
using Rows = std::vector<std::vector<std::optional<refpot::sqlpreview::I>>>;

Rows rows(Database& db, const std::string& query) { return db.execute(query).rows; }

void seed(const std::string& path, Mode mode) {
    Database db(path, mode);
    db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    db.execute("CREATE TABLE empty_source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    db.execute("INSERT INTO source VALUES (1, 10)");
    db.execute("CREATE MATERIALIZED VIEW projected AS SELECT value FROM source");
    db.execute("CREATE MATERIALIZED VIEW totals AS SELECT value, SUM(value) AS total, COUNT(*) AS n FROM source GROUP BY value");
    db.execute("CREATE MATERIALIZED VIEW unmatched AS SELECT e.id FROM empty_source AS e WHERE NOT EXISTS (SELECT * FROM source AS s WHERE s.id = e.id)");
}

enum class Operation { Autocommit, Commit, TableDdl, ViewDdl, AssertionDdl, Checkpoint, Recovery };

const char* label(Operation op) {
    switch (op) {
        case Operation::Autocommit: return "persistent autocommit";
        case Operation::Commit: return "explicit commit";
        case Operation::TableDdl: return "table DDL";
        case Operation::ViewDdl: return "view DDL";
        case Operation::AssertionDdl: return "assertion DDL";
        case Operation::Checkpoint: return "checkpoint";
        case Operation::Recovery: return "recovery";
    }
    return "unknown";
}

bool exists(Database& db, const std::string& query) {
    try { (void)db.execute(query); return true; }
    catch (const std::invalid_argument&) { return false; }
}

void verify_prefix(const std::string& path, bool expect_new) {
    disarm();
    Database reopened(path);
    assert((rows(reopened, "SELECT * FROM source") ==
            (expect_new ? Rows{{1, 10}, {2, 20}} : Rows{{1, 10}})));
    assert(!exists(reopened, "SELECT * FROM added"));
    assert((rows(reopened,"SELECT * FROM projected") == (expect_new?Rows{{10},{20}}:Rows{{10}})));
    assert((rows(reopened,"SELECT * FROM totals") == (expect_new?Rows{{10,10,1},{20,20,1}}:Rows{{10,10,1}})));
    assert(rows(reopened,"SELECT * FROM unmatched").empty());
}

void prepare_operation(Database& db, Operation op) {
    if (op == Operation::Commit) {
        db.execute("BEGIN");
        db.execute("INSERT INTO source VALUES (2, 20)");
    }
}

void perform(Database& db, Operation op) {
    switch (op) {
        case Operation::Autocommit: db.execute("INSERT INTO source VALUES (2, 20)"); break;
        case Operation::Commit: db.execute("COMMIT"); break;
        case Operation::TableDdl:
            db.execute("CREATE TABLE added (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"); break;
        case Operation::ViewDdl:
            db.execute("CREATE MATERIALIZED VIEW added AS SELECT id, value FROM source"); break;
        case Operation::AssertionDdl:
            db.execute("CREATE ASSERTION source_empty CHECK (NOT EXISTS (SELECT * FROM empty_source))"); break;
        case Operation::Checkpoint: db.checkpoint(); break;
        case Operation::Recovery: break;
    }
}

void verify_memory(Database& db, Operation op, bool success) {
    if (op == Operation::Autocommit || op == Operation::Commit) {
        assert((rows(db, "SELECT * FROM source") ==
                (success ? Rows{{1, 10}, {2, 20}} : Rows{{1, 10}})));
    } else {
        assert((rows(db, "SELECT * FROM source") == Rows{{1, 10}}));
        if (op == Operation::TableDdl) assert(exists(db, "SELECT * FROM added") == success);
        if (op == Operation::ViewDdl) {
            assert(exists(db, "SELECT * FROM added") == success);
            if (success) assert((rows(db, "SELECT * FROM added") == Rows{{1, 10}}));
        }
        if (op == Operation::AssertionDdl && success) {
            bool rejected = false;
            try { db.execute("INSERT INTO empty_source VALUES (2, 20)"); }
            catch (const std::logic_error&) { rejected = true; }
            assert(rejected);
        }
    }
}

void sweep(Operation op, Mode mode) {
    bool reached_success = false;
    long refusals = 0;
    for (long cut = 0; cut < 2000 && !reached_success; ++cut) {
        disarm();
        const auto path = fresh_path();
        seed(path.string(),mode);
        if (op == Operation::Recovery) {
            allocation_attempts = 0;
            fail_after = cut;
            bool refused = false;
            try { Database recovered(path.string(),mode); (void)recovered; }
            catch (const std::bad_alloc&) { refused = true; }
            const long attempts = allocation_attempts;
            disarm();
            if (refused) {
                ++refusals;
                assert(attempts == cut + 1);
                verify_prefix(path.string(), false);
            } else {
                assert(attempts <= cut);
                reached_success = true;
                verify_prefix(path.string(), false);
            }
        } else {
            auto db = std::make_unique<Database>(path.string(),mode);
            prepare_operation(*db, op);
            allocation_attempts = 0;
            fail_after = cut;
            bool refused = false;
            try { perform(*db, op); }
            catch (const std::bad_alloc&) { refused = true; }
            const long attempts = allocation_attempts;
            disarm();
            if (refused) {
                ++refusals;
                assert(attempts == cut + 1);
                // Allocation refusal must happen before durability/publication: it
                // must neither poison the live owner nor change its visible state.
                const bool poisoned = db->poisoned();
                if (poisoned) std::cerr << "allocation refusal poisoned owner: " << label(op) << " cut=" << cut << '\n';
                assert(!db->in_transaction());
                if (!poisoned) verify_memory(*db, op, false);
                db.reset();
                verify_prefix(path.string(), false);
                // Reopen and continued writing distinguish a durable-state error
                // from a merely unusable in-memory owner.
                Database continued(path.string());
                assert((rows(continued, "SELECT * FROM source") == Rows{{1, 10}}));
                continued.execute("INSERT INTO source VALUES (3, 30)");
                assert((rows(continued, "SELECT * FROM source") == Rows{{1, 10}, {3, 30}}));
                assert(!poisoned);
            } else {
                assert(attempts <= cut);
                reached_success = true;
                assert(!db->poisoned());
                verify_memory(*db, op, true);
                db.reset();
                if (op == Operation::Autocommit || op == Operation::Commit)
                    verify_prefix(path.string(), true);
                else if (op == Operation::TableDdl || op == Operation::ViewDdl || op == Operation::AssertionDdl) {
                    Database reopened(path.string());
                    if (op == Operation::TableDdl || op == Operation::ViewDdl)
                        assert(exists(reopened, "SELECT * FROM added"));
                    else {
                        bool rejected = false;
                        try { reopened.execute("INSERT INTO empty_source VALUES (2, 20)"); }
                        catch (const std::logic_error&) { rejected = true; }
                        assert(rejected);
                    }
                } else verify_prefix(path.string(), false);
            }
        }
        std::filesystem::remove_all(path.parent_path());
    }
    if (!(reached_success && refusals > 0)) {
        std::cerr << "allocation sweep incomplete: " << label(op) << " reached_success="
                  << reached_success << " refusals=" << refusals << '\n';
        std::abort();
    }
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
    for(Mode mode : {Mode::Overlay, Mode::Modular})
    for (Operation op : {Operation::Autocommit, Operation::Commit, Operation::TableDdl,
                         Operation::ViewDdl, Operation::AssertionDdl, Operation::Recovery,
                         Operation::Checkpoint}) sweep(op,mode);
    std::cout << "SQL persistence allocation-refusal sweeps passed\n";
}
