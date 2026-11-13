#include "../../native/relational/shared_model.hpp"
#include <cassert>
#include <stdexcept>
using namespace refpot::relational;
using namespace refpot::foundation;
int main() {
    Definition s; s.name="s";s.op="source";s.width=2;
    Definition a;a.name="a";a.op="map";a.input="s";a.exprs={{"c0"},{"c1"}};
    Definition b=a;b.name="b";
    Definition f;f.name="f";f.op="filter";f.input="a";f.column=1;f.cmp="ge";f.value=0;
    SharedModel m({s,a,b,f});
    assert(m.physical_definitions().size()==2);
    assert(m.logical_to_physical().at("a")==m.logical_to_physical().at("b"));
    m.prepare({{"insert","s",{1,4},0}});
    assert(m.bag("a").empty());
    assert(m.preview().at("b").at({1,4})==1);
    assert(m.prepared_changes().at("a").at({1,4})==1);
    m.append({{"insert","s",{2,5},0}});
    auto preview=m.preview(); assert(preview.at("b").size()==2);
    int callbacks=0;
    try { m.commit([&](const auto& d){++callbacks;assert(d.count("a")&&d.count("b"));throw std::runtime_error("reject");}); assert(false); }
    catch(const std::runtime_error&){}
    assert(callbacks==1 && m.bag("a").empty() && m.has_prepared());
    m.rollback(); assert(m.bag("a").empty());
    m.prepare({{"insert","s",{3,7},0}});
    std::map<std::string,Bag> seen;
    m.commit([&](const auto& d){seen=d;});
    assert(seen.at("a").at({3,7})==1 && seen.at("b").at({3,7})==1);
    assert(m.bag("a").at({3,7})==1 && m.bag("b").at({3,7})==1);
    assert(m.logical_definitions().size()==4 && m.logical_definitions()[2].name=="b");
}
