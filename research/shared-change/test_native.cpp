#include "native.hpp"
#include <cassert>
#include <cstdlib>
#include <new>
#include <stdexcept>
#include <vector>
#include <cstdint>
#include <iostream>
static long fail_at=-1, allocations=0;
void* operator new(std::size_t n) { if(fail_at>=0 && allocations++==fail_at) throw std::bad_alloc(); if(void* p=std::malloc(n?n:1)) return p; throw std::bad_alloc(); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
using namespace refpot::foundation;
static Definition source(const char* n,std::size_t w=2) { Definition d; d.name=n; d.op="source"; d.width=w; return d; }
static std::vector<Definition> defs() {
    auto a=source("a"), b=source("b");
    Definition m; m.name="mapped"; m.op="map"; m.input="a"; m.exprs={{"c0"},{"c1","2","*"}};
    Definition f; f.name="filtered"; f.op="filter"; f.input="mapped"; f.column=1; f.cmp="gt"; f.value=0;
    Definition u; u.name="united"; u.op="union"; u.left="mapped"; u.right="b";
    Definition j; j.name="self"; j.op="join"; j.left="a"; j.right="a"; j.left_key=j.right_key=0;
    Definition g; g.name="groups"; g.op="group"; g.input="a"; g.key=0; g.value_column=1;
    Definition x; x.name="missing"; x.op="anti"; x.left="a"; x.right="b"; x.left_key=x.right_key=0;
    return {a,b,m,f,u,j,g,x};
}
static void all_modes() {
    for(auto mode:{Mode::Overlay,Mode::Modular}) {
        Model m(defs(),{},mode);
        m.apply({{"insert","a",{1,3},0},{"insert","a",{2,4},0},{"insert","b",{2,9},0}});
        assert(m.bag("mapped").at({1,6})==1 && m.bag("united").at({2,9})==1);
        assert(m.bag("self").at({1,3,1,3})==1 && m.bag("groups").at({1,3,1})==1);
        assert(!m.bag("missing").count({2,4}));
        const auto before=m.snapshot(); const auto ep=m.epoch();
        m.prepare({{"delete","b",{},2},{"insert","b",{1,7},0}});
        assert(m.has_prepared()); assert(m.snapshot()==before); auto pv=m.preview();
        assert(pv.at("missing").at({2,4})==1); assert(pv.at("mapped").at({1,6})==1);
        m.rollback(); m.rollback(); assert(!m.has_prepared() && m.snapshot()==before && m.epoch()==ep);
        m.apply({{"delete","b",{},2},{"insert","b",{1,7},0}});
        assert(m.bag("missing").at({2,4})==1); assert(m.epoch()==ep+1);
        assert(m.stats().source_delta_rows==2 && m.stats().derived_nodes==2);
        if(mode==Mode::Overlay) assert(m.stats().retained_candidate_rows==m.stats().delta_entries+m.stats().staged_insert_rows);
        m.prepare({{"insert","a",{3,8},0}}); bool nested=false;
        try { m.prepare({}); } catch(const std::logic_error&) { nested=true; }
        assert(nested && !m.has_prepared() && m.epoch()==ep+1);

        bool duplicate=false, missing=false;
        try { m.apply({{"insert","a",{1,8},0}}); } catch(const std::invalid_argument&) { duplicate=true; }
        try { m.apply({{"delete","a",{},99}}); } catch(const std::invalid_argument&) { missing=true; }
        assert(duplicate&&missing&&m.epoch()==ep+1);
        Model constrained({source("left"),source("right"),[] { Definition d; d.name="bad";d.op="anti";d.left="left";d.right="right";return d;}()},{"bad"},mode);
        constrained.apply({{"insert","left",{5,1},0},{"insert","right",{5,0},0}});
        assert(constrained.bag("bad").empty());
    }
}
static void overflow_and_noop() {
    Definition s=source("s",3); Definition g;g.name="g";g.op="group";g.input="s";g.key=1;g.value_column=2;
    Model m({s,g},{}); m.apply({{"insert","s",{1,1,INT64_MAX},0}}); auto old=m.snapshot(); auto ep=m.epoch();
    bool overflow=false; try { m.apply({{"insert","s",{2,1,1},0}}); } catch(const std::overflow_error&) { overflow=true; }
    assert(overflow&&m.snapshot()==old&&m.epoch()==ep);
    m.apply({}); assert(m.snapshot()==old&&m.epoch()==ep+1);
}
static void allocation_failures() {
    for(auto mode:{Mode::Modular,Mode::Overlay}) {
        bool succeeded=false;
        long failures=0;
        const std::vector<Mutation> batch={{"update","a",{1,3},0},{"insert","a",{2,4},0}};
        for(long n=0;n<2000&&!succeeded;++n) {
            fail_at=-1;
            Model m(defs(),{},mode); m.apply({{"insert","a",{1,2},0}});
            const auto original=m.snapshot(); const auto epoch=m.epoch();
            allocations=0;
            try { fail_at=n; m.prepare(batch); fail_at=-1; succeeded=true; }
            catch(const std::bad_alloc&) {
                fail_at=-1; ++failures;
                assert(!m.has_prepared()); assert(m.snapshot()==original && m.epoch()==epoch);
                m.apply(batch);
                assert(m.bag("a").count({2,4})==1 && m.epoch()==epoch+1);
            }
            if(succeeded) {
                fail_at=0; allocations=0; m.commit(); fail_at=-1;
                assert(allocations==0 && m.bag("a").count({2,4})==1);
            }
        }
        assert(succeeded && failures>0);
        std::cout << "prepare allocation failures survived: "
                  << (mode==Mode::Modular?"modular":"overlay") << " " << failures << "\n";
    }
}
static void sparse_overlay_does_not_materialize_touched_bags() {
    for (auto mode : {Mode::Modular, Mode::Overlay}) {
        Model m({source("s")}, {}, mode);
        std::vector<Mutation> seed;
        for (I k=0; k<256; ++k) seed.push_back({"insert","s",{k,2},0});
        m.apply(seed);
        m.apply({{"update","s",{7,3},0}});
        assert(m.bag("s").at({7,3}) == 1);
        assert(m.stats().copied_rows == (mode == Mode::Overlay ? 0 : 256));
    }
}
static void both_publications_are_preallocated() {
    for (auto mode : {Mode::Modular, Mode::Overlay}) {
        Model m({source("s")}, {}, mode);
        m.apply({{"insert","s",{1,2},0}});
        m.prepare({{"update","s",{1,3},0},{"insert","s",{2,5},0}});
        allocations=0; fail_at=0;
        bool failed=false;
        try { m.commit(); } catch(const std::bad_alloc&) { failed=true; }
        fail_at=-1;
        assert(!failed);
        assert(allocations==0);
        assert(m.bag("s").at({1,3})==1 && m.bag("s").at({2,5})==1);
    }
}
int main() {
    all_modes(); overflow_and_noop(); allocation_failures();
    both_publications_are_preallocated();
    sparse_overlay_does_not_materialize_touched_bags();
}
