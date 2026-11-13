#include "../../native/relational/foundation.hpp"
#include <cassert>
using namespace refpot::foundation;
int main() {
    Definition source; source.name="source";source.op="source";source.width=2;
    Definition filter;filter.name="filter";filter.op="filter";filter.input="source";
    filter.column=1;filter.cmp="gt";filter.value=0;
    Model old({source,filter},{});
    old.apply({{"insert","source",{1,4},0}});
    const Row* original=&old.bag("source").begin()->first;
    Definition renamed=filter;renamed.name="renamed";
    Definition mapped;mapped.name="mapped";mapped.op="map";mapped.input="renamed";mapped.exprs={{"c1"}};
    std::map<std::string,std::string> reuse{{"source","source"},{"renamed","filter"}};
    auto next=old.prepare_reconfigured({source,renamed,mapped},{},reuse);
    assert(next->bag("mapped")==Bag({{{4},1}}));
    assert(old.bag("filter")==Bag({{{1,4},1}}));
    next->publish_reconfigured_from(old,reuse);
    assert(&next->bag("source").begin()->first==original);
    next->apply({{"update","source",{1,7},0}});
    assert(next->bag("mapped")==Bag({{{7},1}}));
}
