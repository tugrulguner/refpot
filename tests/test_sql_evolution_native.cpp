#include "../native/relational/sql.hpp"
#include <cassert>
#include <cstdlib>
#include <filesystem>
#include <optional>
#include <string>
#include <unistd.h>

using refpot::foundation::Mode;
using refpot::foundation::I;
using refpot::sqlpreview::Database;

int main() {
    const char* scratch = std::getenv("TMPDIR");
    assert(scratch && *scratch);
    std::string root = std::string(scratch) + "/refpot-sql-evolution-XXXXXX";
    std::vector<char> path(root.begin(), root.end());
    path.push_back('\0');
    char* made = mkdtemp(path.data());
    assert(made);
    const std::string file = std::string(made) + "/model.db";
    {
        Database db(file, Mode::Overlay);
        db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        db.execute("INSERT INTO source VALUES (1, 10)");
        db.execute("INSERT INTO source VALUES (2, 20)");
        db.execute("CREATE MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM source");
        db.execute("CREATE MATERIALIZED VIEW downstream AS SELECT id AS id, value AS value FROM first");
        db.execute("CREATE MATERIALIZED VIEW independent AS SELECT id AS id, value AS value FROM source WHERE value > 10");
        db.execute("CREATE MATERIALIZED VIEW guard AS SELECT id AS id, value AS value FROM source WHERE value > 100");
        db.execute("CREATE ASSERTION guard_empty CHECK (NOT EXISTS (SELECT * FROM guard))");
        db.execute("ALTER MATERIALIZED VIEW guard AS SELECT id AS id, value AS value FROM source WHERE value < 0");
        bool assertion_rejected = false;
        try { db.execute("ALTER MATERIALIZED VIEW guard AS SELECT id AS id, value AS value FROM source WHERE value > 0"); }
        catch (const std::exception&) { assertion_rejected = true; }
        assert(assertion_rejected);
        assert(db.execute("SELECT id, value FROM guard").rows.empty());
        auto explain = db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM independent", {}, true);
        assert(explain.rows.empty());
        assert(db.execute("SELECT id, value FROM first").rows.size() == 2);
        db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM independent");
        assert((db.execute("SELECT id, value FROM first").rows ==
                std::vector<std::vector<std::optional<I>>>{{2, 20}}));
        assert((db.execute("SELECT id, value FROM downstream").rows ==
                std::vector<std::vector<std::optional<I>>>{{2, 20}}));
        assert(db.execute("SELECT id, value FROM source ORDER BY id").rows.size() == 2);
        assert((db.execute("SELECT id, value FROM independent").rows ==
                std::vector<std::vector<std::optional<I>>>{{2, 20}}));
        db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM source WHERE value >= 10");
        assert(db.execute("SELECT id, value FROM downstream").rows.size() == 2);
        bool shape_rejected = false;
        try { db.execute("ALTER MATERIALIZED VIEW first AS SELECT value AS value FROM source"); }
        catch (const std::exception&) { shape_rejected = true; }
        assert(shape_rejected);
        bool renamed_rejected = false;
        try { db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS renamed, value AS value FROM source"); }
        catch (const std::exception&) { renamed_rejected = true; }
        assert(renamed_rejected);
        bool cycle_rejected = false;
        try { db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM downstream"); }
        catch (const std::exception&) { cycle_rejected = true; }
        assert(cycle_rejected);
        // Rejection left the last accepted definitions and all bags intact.
        assert(db.execute("SELECT id, value FROM downstream").rows.size() == 2);
        db.execute("UPDATE source SET value = 30 WHERE id = 1");
        assert(db.execute("SELECT id, value FROM downstream WHERE id = 1").rows.size() == 1);
    }
    {
        Database db(file, Mode::Modular);
        assert(db.execute("SELECT id, value FROM first").rows.size() == 2);
        assert(db.execute("SELECT id, value FROM downstream").rows.size() == 2);
        db.checkpoint();
        db.execute("ALTER MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM independent");
        assert(db.execute("SELECT id, value FROM downstream").rows.size() == 2);
        db.execute("CREATE MATERIALIZED VIEW late AS SELECT id AS id, value AS value FROM downstream");
        assert(db.execute("SELECT id, value FROM late").rows.size() == 2);
    }
    {
        Database db(file, Mode::Overlay);
        assert(db.execute("SELECT id, value FROM first").rows.size() == 2);
        assert(db.execute("SELECT id, value FROM downstream").rows.size() == 2);
    }
    // A checksummed but incomplete evolution record must not expose mixed versions.
    {
        const std::string malformed=std::string(made)+"/malformed.db";
        {
            Database db(malformed,Mode::Overlay);
            db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
            db.execute("INSERT INTO source VALUES (1, 10)");
            db.execute("CREATE MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM source");
            db.execute("CREATE MATERIALIZED VIEW downstream AS SELECT id AS id, value AS value FROM first");
            db.checkpoint();
        }
        {
            refpot::sqlstorage::Store store(malformed);
            auto prior=refpot::sqlpersistence::decode_image(store.snapshot());
            auto catalog=prior;
            auto first=std::find_if(catalog.definitions.begin(),catalog.definitions.end(),[](const auto& d){return d.name=="first";});
            assert(first!=catalog.definitions.end());
            first->exprs={{"c1"},{"c0"}};
            std::map<std::string,refpot::foundation::Bag> changed{{"first",prior.bags.at("first")}};
            store.append(refpot::sqlpersistence::encode_evolution(catalog,changed,{}));
        }
        bool rejected=false;
        try { Database recovered(malformed,Mode::Overlay); }
        catch(const std::exception&) { rejected=true; }
        assert(rejected);
    }
    auto rejects_forged_evolution=[&](const std::string& filename,int kind){
        const std::string path=std::string(made)+"/"+filename;
        {
            Database db(path,Mode::Overlay);
            db.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
            db.execute("INSERT INTO source VALUES (1, 10)");
            db.execute("CREATE MATERIALIZED VIEW first AS SELECT id AS id, value AS value FROM source");
            db.execute("CREATE MATERIALIZED VIEW downstream AS SELECT id AS id, value AS value FROM first");
            db.checkpoint();
        }
        {
            refpot::sqlstorage::Store store(path);
            auto prior=refpot::sqlpersistence::decode_image(store.snapshot());
            auto catalog=prior;
            std::map<std::string,refpot::foundation::Bag> replaced{{"first",prior.bags.at("first")}};
            std::set<std::string> removed;
            if(kind==1) removed.insert("missing_definition");
            if(kind==2){
                refpot::foundation::Definition source_add;source_add.name="rogue_source";source_add.op="source";source_add.width=1;
                catalog.definitions.push_back(source_add);replaced.emplace(source_add.name,refpot::foundation::Bag{});
            }
            store.append(refpot::sqlpersistence::encode_evolution(catalog,replaced,removed));
        }
        try { Database recovered(path,Mode::Overlay); }
        catch(const std::exception&) { return true; }
        return false;
    };
    assert(rejects_forged_evolution("unknown-removed.db",1));
    assert(rejects_forged_evolution("new-source.db",2));
    // Offline migration must retain untouched relation nodes and cumulative diagnostics.
    {
        refpot::foundation::Definition source; source.name="source"; source.op="source"; source.width=3;
        refpot::foundation::Model model({source},{},Mode::Overlay);
        model.apply({{"insert","source",{1,7,9223372036854775807LL},0}, {"insert","source",{2,7,1},0}, {"insert","source",{3,7,2},0}});
        refpot::foundation::Definition kept; kept.name="kept"; kept.op="map"; kept.input="source"; kept.exprs={{"c0"},{"c1"},{"c2"}};
        refpot::foundation::Definition changed=kept; changed.name="changed";
        model.add_definitions({kept,changed});
        model.apply({{"insert","source",{4,7,3},0}});
        const auto* source_node=std::addressof(*model.bag("source").begin());
        const auto* kept_node=std::addressof(*model.bag("kept").begin());
        const auto old_applications=model.source_mutation_applications();
        const auto old_materialized=model.materialized_entries();
        const auto old_steps=model.maintenance_steps();
        const auto before_failed_recalc=model.maintenance_steps();
        auto invalid=changed; invalid.op="group"; invalid.input="source"; invalid.key=1; invalid.value_column=2; invalid.exprs.clear();
        bool recalculation_failed=false;
        try { (void)model.replace_definitions({source,kept,invalid},{"changed"}); }
        catch(const std::exception&) { recalculation_failed=true; }
        assert(recalculation_failed);
        assert(model.maintenance_steps()>before_failed_recalc);
        assert(model.bag("kept").size()==4);
        assert(model.bag("changed").size()==4);
        auto replacement=changed; replacement.exprs={{"c0"},{"c1"}};
        auto next=model.replace_definitions({source,kept,replacement},{"changed"});
        next->publish_retained_from(model,{"changed"});
        assert(std::addressof(*next->bag("source").begin())==source_node);
        assert(std::addressof(*next->bag("kept").begin())==kept_node);
        assert(next->source_mutation_applications()==old_applications);
        assert(next->materialized_entries()==old_materialized);
        assert(next->maintenance_steps()>old_steps);
    }
    std::filesystem::remove_all(made);
}
