#include "../native/relational/sql.hpp"
#include <cassert>
#include <filesystem>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

using namespace refpot::sqlpreview;

namespace {
using Rows = std::vector<std::vector<std::optional<I>>>;

void expect(Database& db, const std::string& sql, const Rows& rows) {
    assert(db.execute(sql).rows == rows);
}

void run_mode(refpot::foundation::Mode mode, const std::filesystem::path& path, bool checkpoint) {
    const auto s = path.string();
    {
        Database db(s, mode);
        db.execute("CREATE TABLE resources (id INTEGER PRIMARY KEY, capacity INTEGER NOT NULL)");
        db.execute("CREATE TABLE reservations (id INTEGER PRIMARY KEY, resource INTEGER NOT NULL, units INTEGER NOT NULL)");
        db.execute("INSERT INTO resources VALUES (7, 5)");
        db.execute("INSERT INTO reservations VALUES (1, 7, 3)");
        db.execute("CREATE MATERIALIZED VIEW usage AS SELECT resource, SUM(units) AS total, COUNT(*) AS n FROM reservations GROUP BY resource");
        db.execute("CREATE MATERIALIZED VIEW violations AS SELECT u.resource AS resource, u.total AS total, r.capacity AS capacity FROM usage AS u JOIN resources AS r ON u.resource = r.id WHERE u.total > r.capacity");
        db.execute("CREATE ASSERTION within_capacity CHECK (NOT EXISTS (SELECT * FROM violations))");

        expect(db, "SELECT * FROM usage", {{7, 3, 1}});
        db.execute("BEGIN");
        db.execute("INSERT INTO reservations VALUES (2, 7, 4)");
        expect(db, "SELECT * FROM violations", {{7, 7, 5}});
        db.execute("UPDATE resources SET capacity = 7 WHERE id = 7");
        expect(db, "SELECT * FROM violations", {});
        db.execute("COMMIT");

        db.execute("BEGIN");
        db.execute("UPDATE resources SET capacity = 1 WHERE id = 7");
        bool rejected = false;
        try { db.execute("COMMIT"); } catch (const std::logic_error&) { rejected = true; }
        assert(rejected && !db.in_transaction());
        expect(db, "SELECT * FROM resources", {{7, 7}});
        expect(db, "SELECT * FROM usage", {{7, 7, 2}});
        expect(db, "SELECT * FROM violations", {});

        rejected = false;
        try { db.execute("INSERT INTO reservations VALUES (3, 7, 9)"); }
        catch (const std::logic_error&) { rejected = true; }
        assert(rejected);
        expect(db, "SELECT * FROM reservations", {{1, 7, 3}, {2, 7, 4}});

        db.execute("BEGIN");
        db.execute("UPDATE reservations SET units = 6 WHERE id = 1");
        expect(db, "SELECT * FROM usage", {{7, 10, 2}});
        db.execute("ROLLBACK");
        expect(db, "SELECT * FROM usage", {{7, 7, 2}});
        if(checkpoint)db.checkpoint();
        assert(!db.poisoned());
    }
    {
        Database reopened(s, mode);
        expect(reopened, "SELECT * FROM resources", {{7, 7}});
        expect(reopened, "SELECT * FROM reservations", {{1, 7, 3}, {2, 7, 4}});
        expect(reopened, "SELECT * FROM usage", {{7, 7, 2}});
        expect(reopened, "SELECT * FROM violations", {});
        bool rejected=false;
        try { reopened.execute("INSERT INTO reservations VALUES (4, 7, 1)"); }
        catch(const std::logic_error& e) {
            assert(std::string(e.what()) == "required-empty relation is nonempty");
            rejected=true;
        }
        assert(rejected);
        expect(reopened, "SELECT * FROM usage", {{7, 7, 2}});
        reopened.execute("BEGIN");
        reopened.execute("INSERT INTO reservations VALUES (4, 7, 1)");
        expect(reopened, "SELECT * FROM violations", {{7, 8, 7}});
        reopened.execute("UPDATE resources SET capacity = 8 WHERE id = 7");
        reopened.execute("COMMIT");
        expect(reopened, "SELECT * FROM usage", {{7, 8, 3}});
    }
    {
        Database reopened_again(s, mode);
        expect(reopened_again, "SELECT * FROM resources", {{7, 8}});
        expect(reopened_again, "SELECT * FROM reservations", {{1, 7, 3}, {2, 7, 4}, {4, 7, 1}});
        expect(reopened_again, "SELECT * FROM usage", {{7, 8, 3}});
        expect(reopened_again, "SELECT * FROM violations", {});
    }
}
}

int main() {
    // Column-to-column filters must retain their operand kind and index.
    refpot::sqlpersistence::Image image;
    refpot::foundation::Definition filter;
    filter.name="filter";filter.op="filter";filter.input="source";
    filter.column=1;filter.cmp=">";filter.right_column=2;
    image.definitions.push_back(filter);
    const auto decoded=refpot::sqlpersistence::decode_image(refpot::sqlpersistence::encode_image(image));
    assert(decoded.definitions.at(0).right_column==filter.right_column);

    const auto root = std::filesystem::temp_directory_path() / "refpot-sql-persistence-native";
    std::filesystem::create_directories(root);
    for(bool checkpoint : {false,true})
    for (auto mode : {refpot::foundation::Mode::Overlay, refpot::foundation::Mode::Modular}) {
        const auto path = root / (mode == refpot::foundation::Mode::Overlay ? "overlay.db" : "modular.db");
        std::filesystem::remove(path);
        std::filesystem::remove(path.string() + ".wal");
        std::filesystem::remove(path.string() + ".lock");
        run_mode(mode, path, checkpoint);
        std::filesystem::remove(path);
        std::filesystem::remove(path.string() + ".wal");
        std::filesystem::remove(path.string() + ".lock");
    }
    std::filesystem::remove(root);
    std::cout << "native SQL persistence tests passed\n";
}
