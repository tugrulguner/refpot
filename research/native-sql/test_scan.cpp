#include "../shared-change/native.hpp"
#include <cassert>
#include <type_traits>
#include <utility>
using namespace refpot::foundation;
struct Visit { bool operator()(const Row&,I) const { return true; } };
template<class T,class=void> struct HasScan:std::false_type {};
template<class T> struct HasScan<T,std::void_t<decltype(std::declval<const T&>().scan(std::string{},false,Visit{}))>>:std::true_type {};
template<class T> void test() {
    if constexpr(!HasScan<T>::value) { assert(false && "native candidate scan required"); }
    else for(auto mode:{Mode::Modular,Mode::Overlay}) {
        Definition d; d.name="t";d.op="source";d.width=2;
        T m({d},{},mode);
        m.apply({{"insert","t",{1,10},0},{"insert","t",{2,20},0}});
        m.prepare({{"update","t",{1,30},0},{"delete","t",{},2},{"insert","t",{3,40},0}});
        std::vector<Row> rows;
        m.scan("t",true,[&](const Row& r,I n){assert(n==1);rows.push_back(r);return true;});
        assert((rows==std::vector<Row>{{1,30},{3,40}}));
        rows.clear();
        m.scan("t",false,[&](const Row& r,I){rows.push_back(r);return false;});
        assert((rows==std::vector<Row>{{1,10}}));
        m.rollback(); bool rejected=false;
        try { m.scan("t",true,Visit{}); } catch(const std::logic_error&) { rejected=true; }
        assert(rejected);
    }
}
int main(){test<Model>();}
