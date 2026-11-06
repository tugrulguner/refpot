#include "../native/relational/sql.hpp"

#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <new>
#include <optional>
#include <string>
#include <unistd.h>
#include <vector>

namespace {
long fail_after = -1;
long allocation_attempts = 0;
void* allocate(std::size_t n) {
    if (fail_after >= 0 && allocation_attempts++ == fail_after) throw std::bad_alloc();
    if (void* p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void* allocate_aligned(std::size_t n, std::size_t a) {
    if (fail_after >= 0 && allocation_attempts++ == fail_after) throw std::bad_alloc();
    void* p = nullptr;
    if (posix_memalign(&p, a, n ? n : a) == 0) return p;
    throw std::bad_alloc();
}
void disarm() noexcept { fail_after = -1; }
std::filesystem::path fresh_path() {
    std::string pattern = (std::filesystem::temp_directory_path() / "refpot-evolution-alloc-XXXXXX").string();
    std::vector<char> name(pattern.begin(), pattern.end()); name.push_back('\0');
    char* dir = ::mkdtemp(name.data()); assert(dir);
    return std::filesystem::path(dir) / "db";
}
using Mode = refpot::foundation::Mode;
using Database = refpot::sqlpreview::Database;
using Rows = std::vector<std::vector<std::optional<refpot::sqlpreview::I>>>;
Rows rows(Database& d, const char* q) { return d.execute(q).rows; }
void seed(const std::string& p, Mode mode) {
    Database d(p, mode);
    d.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    d.execute("INSERT INTO source VALUES (1, 10)");
    d.execute("INSERT INTO source VALUES (2, 20)");
    d.execute("CREATE MATERIALIZED VIEW base AS SELECT id, value FROM source");
    d.execute("CREATE MATERIALIZED VIEW child AS SELECT id, value FROM base");
    d.execute("CREATE TABLE empty_source (id INTEGER PRIMARY KEY)");
    d.execute("CREATE ASSERTION empty_stays_empty CHECK (NOT EXISTS (SELECT * FROM empty_source))");
}
void sweep(Mode mode) {
    bool success = false; long refusals = 0;
    for (long cut = 0; cut < 2000 && !success; ++cut) {
        disarm(); auto path = fresh_path(); seed(path.string(), mode);
        auto db = std::make_unique<Database>(path.string(), mode);
        allocation_attempts = 0; fail_after = cut; bool refused = false;
        try { db->execute("ALTER MATERIALIZED VIEW base AS SELECT id, id AS value FROM source"); }
        catch (const std::bad_alloc&) { refused = true; }
        long attempts = allocation_attempts; disarm();
        if (refused) {
            ++refusals; assert(attempts == cut + 1);
            assert(!db->poisoned());
            assert((rows(*db, "SELECT * FROM child ORDER BY id") == Rows{{1,10},{2,20}}));
            db.reset();
            Database reopened(path.string());
            assert((rows(reopened, "SELECT * FROM child ORDER BY id") == Rows{{1,10},{2,20}}));
            reopened.execute("INSERT INTO source VALUES (3, 30)");
            assert((rows(reopened, "SELECT * FROM child ORDER BY id") == Rows{{1,10},{2,20},{3,30}}));
        } else {
            assert(attempts <= cut); success = true;
            assert(!db->poisoned());
            assert((rows(*db, "SELECT * FROM child ORDER BY id") == Rows{{1,1},{2,2}}));
            db.reset(); Database reopened(path.string());
            assert((rows(reopened, "SELECT * FROM child ORDER BY id") == Rows{{1,1},{2,2}}));
        }
        std::filesystem::remove_all(path.parent_path());
    }
    if (!(success && refusals > 0)) { std::cerr << "ALTER allocation sweep did not reach refusal and success\n"; std::abort(); }
}
}
void* operator new(std::size_t n) { return allocate(n); }
void* operator new[](std::size_t n) { return allocate(n); }
void* operator new(std::size_t n, const std::nothrow_t&) noexcept { try { return allocate(n); } catch (...) { return nullptr; } }
void* operator new[](std::size_t n, const std::nothrow_t&) noexcept { try { return allocate(n); } catch (...) { return nullptr; } }
void* operator new(std::size_t n, std::align_val_t a) { return allocate_aligned(n, static_cast<std::size_t>(a)); }
void* operator new[](std::size_t n, std::align_val_t a) { return allocate_aligned(n, static_cast<std::size_t>(a)); }
void* operator new(std::size_t n, std::align_val_t a, const std::nothrow_t&) noexcept { try { return allocate_aligned(n, static_cast<std::size_t>(a)); } catch (...) { return nullptr; } }
void* operator new[](std::size_t n, std::align_val_t a, const std::nothrow_t&) noexcept { try { return allocate_aligned(n, static_cast<std::size_t>(a)); } catch (...) { return nullptr; } }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete[](void* p, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }
void operator delete[](void* p, std::align_val_t) noexcept { std::free(p); }
void operator delete(void* p, std::size_t, std::align_val_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t, std::align_val_t) noexcept { std::free(p); }
void operator delete(void* p, std::align_val_t, const std::nothrow_t&) noexcept { std::free(p); }
void operator delete[](void* p, std::align_val_t, const std::nothrow_t&) noexcept { std::free(p); }
int main() {
    sweep(refpot::foundation::Mode::Overlay);
    sweep(refpot::foundation::Mode::Modular);
    std::cout << "SQL evolution allocation-refusal sweeps passed\n";
}
