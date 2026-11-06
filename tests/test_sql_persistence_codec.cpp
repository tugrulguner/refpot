#include "../native/relational/persistence.hpp"
#include "../native/relational/foundation.hpp"
#include <optional>
#include <cassert>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {
using namespace refpot;
using namespace refpot::sqlpersistence;
using foundation::Bag;
using foundation::Definition;
using foundation::I;
using foundation::Row;

template<class F> void rejects(F&& f) {
    bool did_reject=false;
    try { f(); } catch(const std::exception&) { did_reject=true; }
    assert(did_reject);
}

Definition source(const std::string& name, std::size_t width=2) {
    Definition d; d.name=name; d.op="source"; d.width=width; return d;
}

void codec_round_trips_typed_definition_and_relation_deltas() {
    Image image;
    image.tables.push_back(Table{"items", {"id", "value"}, false});
    auto src=source("items");
    Definition filter; filter.name="selected"; filter.op="filter"; filter.input="items";
    filter.column=1; filter.cmp="gt"; filter.value=4; filter.right_column=0;
    image.definitions={src,filter};
    image.bags["items"][Row{1,8}]=1;
    image.bags["selected"][Row{1,8}]=1;
    auto copy=decode_image(encode_image(image));
    assert(copy.definitions.size()==2);
    assert(equal_definition(copy.definitions[1],filter));
    assert(copy.bags==image.bags);

    std::map<std::string,Bag> delta;
    delta["selected"][Row{1,8}]=-2;
    delta["selected"][Row{2,9}]=1;
    assert(decode_delta(encode_delta(delta))==delta);
}

void rejects_malformed_codec_records_before_native_restore() {
    const auto good=encode_image(Image{});
    auto truncated=good; truncated.pop_back();
    rejects([&]{(void)decode_image(truncated);});
    auto trailing=good; trailing.push_back(0);
    rejects([&]{(void)decode_image(trailing);});
    auto bad_version=good; bad_version[8]=2;
    rejects([&]{(void)decode_image(bad_version);});

    // A codec-valid but structurally invalid definition must fail in typed recovery.
    Image invalid;
    invalid.definitions.push_back(source("items", 2));
    invalid.definitions[0].op="not-an-operator";
    invalid.bags["items"][Row{1,2}]=1;
    rejects([&]{foundation::Model model(invalid.definitions, invalid.required, invalid.bags,
                                        foundation::Mode::Overlay);});

    Image malformed_bag;
    malformed_bag.definitions.push_back(source("items", 2));
    malformed_bag.bags["items"][Row{1}]=1;
    auto decoded=decode_image(encode_image(malformed_bag));
    rejects([&]{foundation::Model model(decoded.definitions, decoded.required, decoded.bags,
                                        foundation::Mode::Overlay);});

    Image absent;
    absent.definitions.push_back(source("items", 2));
    rejects([&]{foundation::Model model(absent.definitions, absent.required, absent.bags,
                                        foundation::Mode::Overlay);});

    Image wrong_pk;
    wrong_pk.definitions.push_back(source("items", 2));
    wrong_pk.bags["items"][Row{7,10}]=1;
    wrong_pk.bags["items"][Row{7,11}]=1;
    rejects([&]{foundation::Model model(wrong_pk.definitions, wrong_pk.required, wrong_pk.bags,
                                        foundation::Mode::Overlay);});

    Image wrong_mult;
    wrong_mult.definitions.push_back(source("items", 2));
    wrong_mult.bags["items"][Row{7,10}]=2;
    rejects([&]{foundation::Model model(wrong_mult.definitions, wrong_mult.required, wrong_mult.bags,
                                        foundation::Mode::Overlay);});

    Image wrong_filter;
    wrong_filter.definitions.push_back(source("items", 2));
    Definition f; f.name="filtered"; f.op="filter"; f.input="items";
    f.column=0; f.cmp="gt"; f.right_column=2;
    wrong_filter.definitions.push_back(f);
    wrong_filter.bags["items"][Row{1,2}]=1;
    wrong_filter.bags["filtered"]={};
    rejects([&]{foundation::Model model(wrong_filter.definitions, wrong_filter.required,
                                        wrong_filter.bags, foundation::Mode::Overlay);});
}

void restore_accepted_source_and_internal_bags_without_recomputing() {
    auto src=source("items",2);
    Definition map; map.name="projected"; map.op="map"; map.input="items";
    map.exprs={{"c1"}};
    Definition filtered; filtered.name="filtered"; filtered.op="filter"; filtered.input="projected";
    filtered.column=0; filtered.cmp="gt"; filtered.value=0;
    std::vector<Definition> defs{src,map,filtered};
    std::map<std::string,Bag> state;
    state["items"][Row{1,3}]=1;
    state["items"][Row{2,3}]=1;
    state["projected"][Row{3}]=2;
    state["filtered"][Row{3}]=2;
    foundation::Model restored(defs, {}, state, foundation::Mode::Modular);
    assert(restored.bag("items")==state.at("items"));
    assert(restored.bag("projected")==state.at("projected"));
    assert(restored.bag("filtered")==state.at("filtered"));
    // A later accepted source change should continue from the recovered maintained state.
    restored.apply({foundation::Mutation{"insert", "items", Row{3,5}, 0}});
    assert(restored.bag("projected").at(Row{5})==1);
    assert(restored.bag("filtered").at(Row{5})==1);
}
}

int main() {
    codec_round_trips_typed_definition_and_relation_deltas();
    rejects_malformed_codec_records_before_native_restore();
    restore_accepted_source_and_internal_bags_without_recomputing();
    std::cout << "SQL persistence codec tests passed\n";
}
