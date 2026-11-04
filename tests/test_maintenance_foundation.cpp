#include "../native/relational/foundation.hpp"
#include <cassert>
#include <iostream>
using namespace refpot::foundation;
int main() {
    refpot::model::Definition base;
    base.name="src"; base.op="source"; base.width=2;
    Definition source=base; // preserve existing base-definition construction
    Model model({source},{},Mode::Overlay);
    model.apply({{"insert","src",{1,4},0},{"insert","src",{2,9},0}});
    Definition filter;
    filter.name="picked"; filter.op="filter"; filter.input="src";
    filter.width=2; filter.column=1; filter.cmp="lt"; filter.value=2;
    const Row* retained=&model.bag("src").begin()->first;
    model.add_definitions({filter});
    assert(retained==&model.bag("src").begin()->first); // no old row/node copying
    assert(model.bag("picked").empty());

    model.add_required_empty("picked");
    model.prepare({{"update","src",{1,1},0}},false);
    assert(!model.preview().at("picked").empty());
    bool violation=false;
    try { model.commit(); } catch (const std::logic_error&) { violation=true; }
    assert(violation && model.bag("src").size()==2 && model.has_prepared());
    model.append({{"update","src",{1,4},0}},false);
    model.commit();
    assert(model.bag("src").size()==2 && model.bag("picked").empty());

    Definition right_filter;
    right_filter.name="same"; right_filter.op="filter"; right_filter.input="src";
    right_filter.width=2; right_filter.column=0; right_filter.cmp="="; right_filter.right_column=1;
    bool rejected=false;
    try { model.add_definitions({right_filter}); } catch (const std::invalid_argument&) { rejected=true; }
    assert(rejected); // generic foundation comparison spellings remain canonical
    right_filter.cmp="gt";right_filter.column=1;right_filter.right_column=0;
    model.add_definitions({right_filter});
    assert(model.bag("same").size()==2);
    right_filter.right_column=2;
    rejected=false;
    try{Model invalid({source,right_filter},{});}catch(const std::invalid_argument&){rejected=true;}
    assert(rejected); // validate the right-hand column even with no rows
    for(auto mode:{Mode::Overlay,Mode::Modular}) {
        Definition left;left.name="left";left.op="source";left.width=2;
        Definition right=left;right.name="right";
        Model bounded({left,right},{},mode);
        std::vector<Mutation> batch;
        for(int i=0;i<1001;++i)batch.push_back({"insert","left",{i,0},0});
        bounded.apply(batch);
        Definition join;join.name="joined";join.op="join";join.left="left";join.right="right";join.left_key=1;join.right_key=1;
        bounded.add_definitions({join});
        const auto before=bounded.snapshot();batch.clear();
        for(int i=0;i<1001;++i)batch.push_back({"insert","right",{i,1},0});
        bool exceeded=false;
        try{bounded.apply(batch);}catch(const std::length_error&){exceeded=true;}
        assert(exceeded&&!bounded.has_prepared()&&bounded.snapshot()==before);
    }
    {
        Model catalog({source},{});
        std::vector<Definition> views;
        for(int i=0;i<1023;++i) {
            Definition view;view.name="view"+std::to_string(i);view.op="map";
            view.input="src";view.exprs={{"c0"}};views.push_back(view);
        }
        catalog.add_definitions(views);
        const auto before=catalog.snapshot();
        Definition extra=source;extra.name="extra";
        bool refused=false;
        try{catalog.add_source(extra);}catch(const std::length_error&){refused=true;}
        assert(refused&&catalog.snapshot()==before);
        views.insert(views.begin(),source);views.push_back(extra);
        refused=false;
        try{Model too_many(views,{});}catch(const std::length_error&){refused=true;}
        assert(refused);
    }
    std::cout << "maintenance foundation tests passed\n";
}
