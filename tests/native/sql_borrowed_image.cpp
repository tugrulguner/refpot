#include "../../native/relational/sql.hpp"
#include <cassert>
#include <iostream>

int main(){
    using namespace refpot;
    using namespace refpot::sqlpersistence;
    foundation::Definition source;source.name="source";source.op="source";source.width=1;
    foundation::Definition left;left.name="left";left.op="map";left.input="source";left.width=1;left.exprs={{"c0"}};
    foundation::Definition alias=left;alias.name="alias";
    foundation::Definition right;right.name="right";right.op="source";right.width=1;
    relational::SharedModel model({source,left,alias,right});
    model.apply({{"insert","source",{4},0},{"insert","right",{9},0}});
    Image shared;shared.definitions=model.definitions();
    for(const auto&definition:model.definitions())shared.bags.emplace(definition.name,model.bag(definition.name));
    const auto materialized=encode_image(shared);
    model.with_committed([&](const auto& borrowed){
        assert(encode_image_range(shared,borrowed)==materialized);
        assert(encoded_image_size_range(shared,borrowed)==materialized.size());
        assert(&borrowed.at("left")==&borrowed.at("alias"));
    });
    auto unpublished=model.replace_definitions(model.definitions(),{"alias"});
    bool refused=false;
    try{unpublished->with_committed([](const auto&){});}catch(const std::logic_error&){refused=true;}
    assert(refused);
    const auto path=std::filesystem::temp_directory_path()/"refpot-borrowed-image-checkpoint.db";
    std::filesystem::remove(path);std::filesystem::remove(path.string()+".wal");
    {
        refpot::sqlpreview::Database db(path.string());
        db.execute("CREATE TABLE rows (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)");
        db.execute("INSERT INTO rows VALUES (2, 7)");
        db.checkpoint();
    }
    {
        refpot::sqlpreview::Database reopened(path.string());
        assert(reopened.execute("SELECT * FROM rows").rows.size()==1);
        reopened.checkpoint();
    }
    std::filesystem::remove(path);std::filesystem::remove(path.string()+".wal");
    std::cout<<"borrowed image bytes="<<materialized.size()<<"\n";
}
