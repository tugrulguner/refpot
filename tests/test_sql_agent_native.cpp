#include "../native/relational/sql.hpp"
#include <cassert>
#include <csignal>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <sys/resource.h>

using namespace refpot::sqlpreview;
static void poisoned_catalog_context_is_rejected() {
    const auto* temporary=std::getenv("TMPDIR");assert(temporary);
    std::string pattern=std::string(temporary)+"/agent-context-XXXXXX";
    auto* directory=::mkdtemp(pattern.data());assert(directory);
    const std::string path=std::string(directory)+"/store";
    {
        Database persistent(path);
        persistent.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY)");
        const auto context=persistent.query_context({"allowed"});
        struct rlimit prior{};assert(::getrlimit(RLIMIT_FSIZE,&prior)==0);
        auto limited=prior;limited.rlim_cur=std::filesystem::file_size(path+".wal");
        const auto handler=std::signal(SIGXFSZ,SIG_IGN);assert(handler!=SIG_ERR);
        assert(::setrlimit(RLIMIT_FSIZE,&limited)==0);
        bool write_failed=false;
        try {persistent.execute("INSERT INTO allowed VALUES (1)");}
        catch(const std::exception&) {write_failed=true;}
        assert(::setrlimit(RLIMIT_FSIZE,&prior)==0);
        assert(std::signal(SIGXFSZ,handler)!=SIG_ERR);
        assert(write_failed&&persistent.poisoned());
        bool refused=false;
        try {persistent.query_context({"allowed"});}
        catch(const std::runtime_error&) {refused=true;}
        assert(refused&&"poisoned native handles must not disclose catalog context");
        refused=false;
        try {persistent.execute_readonly("SELECT * FROM allowed",{}, {"allowed"},context.revision);}
        catch(const std::runtime_error&) {refused=true;}
        assert(refused);
    }
    { Database reopened(path);assert(reopened.query_context({"allowed"}).relations.size()==1); }
    std::filesystem::remove_all(directory);
}
int main() {
    poisoned_catalog_context_is_rejected();
    Database db;
    db.execute("CREATE TABLE allowed (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
    db.execute("CREATE TABLE secret (id INTEGER PRIMARY KEY)");
    db.execute("INSERT INTO allowed VALUES (1, 9)");
    const auto context=db.query_context({"allowed"});
    assert(context.revision==2 && context.relations.size()==1);
    assert(context.relations[0].name=="allowed" && context.relations[0].columns.size()==2 && !context.relations[0].derived);
    auto result=db.execute_readonly("SELECT * FROM allowed",{}, {"allowed"},context.revision);
    assert(result.rows.size()==1);
    auto denied=[&](const std::string& q){bool rejected=false;try{db.execute_readonly(q,{}, {"allowed"},context.revision);}catch(const std::exception&){rejected=true;}assert(rejected);};
    denied("SELECT * FROM secret");
    denied("SELECT * FROM allowed JOIN secret ON allowed.id = secret.id");
    denied("SELECT * FROM allowed WHERE NOT EXISTS (SELECT * FROM secret WHERE secret.id = allowed.id)");
    denied("INSERT INTO allowed VALUES (2, 3)");
    denied("SELECT * FROM allowed; INSERT INTO allowed VALUES (2,3)");
    db.execute("BEGIN");
    bool refused=false;try{db.execute_readonly("SELECT * FROM allowed",{}, {"allowed"},context.revision);}catch(const std::exception&){refused=true;}
    assert(refused && db.in_transaction());
    refused=false;try{db.execute("SELECT * FROM allowed @",{});}catch(const std::exception&){refused=true;}
    assert(refused && !db.in_transaction());
    db.execute("BEGIN");
    refused=false;try{db.execute("SELECT * FROM allowed @",{},true);}catch(const std::exception&){refused=true;}
    assert(refused && db.in_transaction());
    db.execute("ROLLBACK");
    db.execute("INSERT INTO allowed VALUES (2, 4)");
    assert(db.query_context({"allowed"}).revision==context.revision);
    db.execute("CREATE TABLE fresh (id INTEGER PRIMARY KEY)");
    refused=false;try{db.execute_readonly("SELECT * FROM allowed",{}, {"allowed"},context.revision);}catch(const std::exception&){refused=true;}
    assert(refused);
    db.execute("CREATE MATERIALIZED VIEW v AS SELECT id FROM allowed");
    const auto before_failed_ddl=db.query_context({"allowed"}).revision;
    refused=false;try{db.execute("CREATE TABLE broken (id INTEGER PRIMARY KEY,)");}catch(const std::exception&){refused=true;}
    assert(refused && db.query_context({"allowed"}).revision==before_failed_ddl);
    const auto before_alter=db.query_context({"allowed","v"});
    db.execute("ALTER MATERIALIZED VIEW v AS SELECT id FROM allowed WHERE value = 4");
    refused=false;try{db.execute_readonly("SELECT * FROM v",{}, {"v"},before_alter.revision);}catch(const std::exception&){refused=true;}
    assert(refused);
    refused=false;try{db.execute("SELECT * FROM missing");}catch(const std::exception& e){refused=std::string(e.what()).find("unknown table: missing")!=std::string::npos;}
    assert(refused);
    refused=false;try{db.execute_readonly("SELECT * FROM allowed @",{}, {"allowed"},db.query_context({"allowed"}).revision);}catch(const std::exception&){refused=true;}
    assert(refused);
    std::cout << "native agent boundary tests passed\n";
}