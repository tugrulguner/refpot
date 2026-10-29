#include "../../native/model/model.hpp"

#include <cassert>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>

using namespace refpot::model;

namespace {
bool refuse_allocations = false;
long allocations_before_failure = -1;
int assertion_count = 0;
void check(bool condition, const char* message) {
    ++assertion_count;
    if (!condition) throw std::runtime_error(message);
}
bool same_stats(const Stats& a,const Stats& b) {
    return a.source_delta_rows==b.source_delta_rows && a.derived_nodes==b.derived_nodes &&
           a.rows_visited==b.rows_visited && a.copied_rows==b.copied_rows;
}
template<class F> void must_throw(F&& fn) {
    bool threw = false;
    try { fn(); } catch (const std::exception&) { threw = true; }
    check(threw, "expected std::exception");
}
Definition source(std::string name, std::size_t width) {
    Definition d; d.name=std::move(name); d.op="source"; d.width=width; return d;
}
Definition map1(std::string name, std::string input,
                std::vector<std::string> expression) {
    Definition d; d.name=std::move(name); d.op="map"; d.input=std::move(input);
    d.exprs.push_back(std::move(expression)); return d;
}
Definition filter(std::string name, std::string input, std::size_t column,
                  std::string cmp, I value) {
    Definition d; d.name=std::move(name); d.op="filter"; d.input=std::move(input);
    d.column=column; d.cmp=std::move(cmp); d.value=value; return d;
}
Definition join(std::string name, std::string left, std::string right,
                std::size_t lk, std::size_t rk) {
    Definition d; d.name=std::move(name); d.op="join"; d.left=std::move(left);
    d.right=std::move(right); d.left_key=lk; d.right_key=rk; return d;
}
Definition group(std::string name, std::string input, std::size_t key, std::size_t value) {
    Definition d; d.name=std::move(name); d.op="group"; d.input=std::move(input);
    d.key=key; d.value_column=value; return d;
}
Definition anti(std::string name, std::string left, std::string right,
                std::size_t lk, std::size_t rk) {
    Definition d; d.name=std::move(name); d.op="anti"; d.left=std::move(left);
    d.right=std::move(right); d.left_key=lk; d.right_key=rk; return d;
}
Mutation insert(std::string table, Row row) {
    Mutation m; m.op="insert"; m.table=std::move(table); m.row=std::move(row); return m;
}
Mutation erase(std::string table, I key) {
    Mutation m; m.op="delete"; m.table=std::move(table); m.key=key; return m;
}
void transactional_basics() {
    Model m({source("items",2), map1("copy","items",{"c0"}),
             filter("positive","copy",0,"gt",100)}, {"positive"});
    check(m.epoch()==0, "initial epoch");
    must_throw([&]{ m.apply({insert("items",{1,7}), insert("items",{101,8})}); });
    check(m.epoch()==0 && m.bag("items").empty(), "constraint rollback");
    m.apply({insert("items",{1,7}), insert("items",{-1,9})});
    check(m.epoch()==1, "accepted batch epoch");
    check(m.bag("copy").at({1})==1 && m.bag("positive").empty(),
          "map/filter materialization");
    auto old=m.snapshot();
    m.apply({erase("items",1)});
    check(old.at("items").at({1,7})==1 && m.epoch()==2, "snapshot isolation");
    must_throw([&]{m.apply({insert("items",{2,3}),insert("items",{2,4})});});
    check(!m.bag("items").count({2,3}) && m.epoch()==2, "ordered atomic rejection");
}
void source_update_and_mutation_validation() {
    Model m({source("records",2), map1("keys","records",{"c0"})},{});
    m.apply({insert("records",{1,10})});
    auto before=m.snapshot(); auto stats=m.stats();
    must_throw([&]{m.apply({insert("records",{1,99})});});
    must_throw([&]{m.apply({Mutation{"update","records",{2,20},0}});});
    must_throw([&]{m.apply({erase("records",2)});});
    must_throw([&]{m.apply({insert("keys",{2})});});
    check(m.epoch()==1 && m.snapshot()==before, "invalid mutations roll back");
    check(m.stats().source_delta_rows==stats.source_delta_rows, "failed batch preserves stats");
    m.apply({Mutation{"update","records",{1,11},0}});
    check(m.bag("records").at({1,11})==1 && m.bag("keys").at({1})==1,
          "source update propagates a retraction and insertion");
}
void join_self_join_union() {
    Definition self=join("pairs","edges","edges",1,0);
    Definition uni; uni.name="all"; uni.op="union"; uni.left="edges"; uni.right="edges";
    Model m({source("edges",2), self, uni}, {});
    m.apply({insert("edges",{1,2}),insert("edges",{2,3})});
    check(m.bag("pairs").at({1,2,2,3})==1, "self join");
    check(m.bag("all").at({1,2})==2, "bag union multiplicity");
    m.apply({insert("edges",{3,1})});
    check(m.bag("pairs").at({2,3,3,1})==1 && m.bag("pairs").size()==3,
          "self join simultaneous cross terms");
    m.apply({erase("edges",2)});
    check(m.bag("pairs").size()==1, "join retraction");
}
void anti_join_presence() {
    Definition copy=map1("parent_twice","parents",{"c0"});
    Definition u; u.name="parent_keys"; u.op="union"; u.left="parent_twice"; u.right="parent_twice";
    Model m({source("parents",1), source("children",2), copy, u,
      anti("orphans","children","parent_keys",1,0)}, {});
    m.apply({insert("parents",{7}),insert("children",{10,7}),insert("children",{11,7})});
    check(m.bag("orphans").empty(), "anti matched");
    m.apply({erase("parents",7)});
    check(m.bag("orphans").at({10,7})==1 && m.bag("orphans").at({11,7})==1,
          "anti exposes rows when key presence disappears");
    m.apply({insert("parents",{7})});
    check(m.bag("orphans").empty(), "anti ignores duplicate right multiplicity and tracks presence");
}
void high_multiplicity_join_retraction() {
    std::vector<Definition> defs{source("seed",1)};
    std::string prior="seed";
    for(int i=0;i<31;++i) {
        Definition d; d.name="d"+std::to_string(i); d.op="union";
        d.left=prior; d.right=prior; defs.push_back(d); prior=d.name;
    }
    Definition amount; amount.name="amount"; amount.op="union";
    amount.left="d30"; amount.right="d28"; defs.push_back(amount);
    defs.push_back(join("pairs","amount","amount",0,0));
    Model m(defs,{});
    m.apply({insert("seed",{1})});
    check(m.bag("pairs").at({1,1})==static_cast<I>(7205759403792793600LL),
          "large but representable self join");
    m.apply({erase("seed",1)});
    check(m.bag("pairs").empty(), "large self join retracts without transient overflow");
}
void scan_counters_include_nonmatching_rows() {
    Model m({source("entries",3),group("totals","entries",1,2)},{});
    std::vector<Mutation> initial;
    for(I i=0;i<20;++i) initial.push_back(insert("entries",{i,i,1}));
    m.apply(initial);
    m.apply({Mutation{"update","entries",{0,0,2},0}});
    check(m.stats().derived_nodes==1, "work counters describe last commit only");
    check(m.stats().rows_visited>=40, "group scans count nonmatching rows too");
}
void group_final_fit_and_disappearance() {
    Model m({source("entries",3),group("totals","entries",1,2)}, {});
    I max=std::numeric_limits<I>::max();
    m.apply({insert("entries",{1,4,max}),insert("entries",{2,4,1}),insert("entries",{3,4,-1})});
    check(m.bag("totals").at({4,max,3})==1, "wide sum final-fit cancellation");
    m.apply({erase("entries",1),erase("entries",2),erase("entries",3)});
    check(m.bag("totals").empty(), "empty group disappears");
    must_throw([&]{m.apply({insert("entries",{8,9,max}),insert("entries",{9,9,1})});});
    check(m.epoch()==2 && !m.bag("entries").count({8,9,max}), "group overflow rollback");
}
void expression_checked_and_invalid_definition() {
    Model m({source("nums",1),map1("squares","nums",{"c0","c0","*"})},{});
    I max=std::numeric_limits<I>::max();
    must_throw([&]{m.apply({insert("nums",{max})});});
    check(m.epoch()==0 && m.bag("nums").empty(), "expression overflow rollback");
    must_throw([]{Model bad({source("rows",1),map1("bad","rows",{"c+0"})},{});});
    must_throw([]{Model bad({source("rows",1),map1("bad","rows",{"9223372036854775808"})},{});});
    must_throw([]{Model bad({source("bad",0)},{});});
}
void batch_candidate_final_state_and_epoch_overflow() {
    Model m({source("parents",1),source("children",2),
             anti("missing","children","parents",1,0)}, {"missing"});
    m.apply({insert("children",{1,5}),insert("parents",{5})});
    check(m.epoch()==1 && m.bag("missing").empty(), "final candidate validates repaired violation");
    m.apply({erase("parents",5),insert("parents",{5})});
    check(m.epoch()==2 && m.bag("missing").empty(), "ordered temporary anti violation is allowed");
    m.apply({});
    check(m.epoch()==3, "successful empty batch advances epoch");
}
void allocation_refusal_is_atomic_and_recoverable() {
    Model m({source("rows",2),map1("mapped","rows",{"c0"})},{});
    m.apply({insert("rows",{1,2})});
    long failures=0; bool committed=false;
    for(long n=0;n<10000 && !committed;++n) {
        const auto before=m.snapshot(); const auto epoch=m.epoch(); const auto prior_stats=m.stats();
        allocations_before_failure=n;
        try { m.apply({insert("rows",{2,3})}); committed=true; }
        catch(const std::bad_alloc&) { ++failures; }
        allocations_before_failure=-1;
        check(committed ? m.epoch()==epoch+1 :
              (m.epoch()==epoch && m.snapshot()==before && same_stats(m.stats(),prior_stats)),
              "every injected allocation failure preserves snapshot, epoch, and stats");
    }
    check(committed && failures>=4, "allocation failure swept preparation points");
    check(m.bag("mapped").at({2})==1, "model usable after allocation failures");
    m.apply({insert("rows",{3,4})});
    check(m.bag("mapped").at({3})==1, "model remains usable for a later commit");
}
}

void* operator new(std::size_t n) {
    if (refuse_allocations || allocations_before_failure==0) throw std::bad_alloc();
    if (allocations_before_failure>0) --allocations_before_failure;
    if (void* p=std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void* operator new[](std::size_t n) {
    if (refuse_allocations || allocations_before_failure==0) throw std::bad_alloc();
    if (allocations_before_failure>0) --allocations_before_failure;
    if (void* p=std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }

int main() {
    try {
        transactional_basics(); source_update_and_mutation_validation();
        join_self_join_union(); anti_join_presence(); high_multiplicity_join_retraction();
        batch_candidate_final_state_and_epoch_overflow();
        group_final_fit_and_disappearance(); expression_checked_and_invalid_definition(); scan_counters_include_nonmatching_rows();
        allocation_refusal_is_atomic_and_recoverable();
        std::cout << "PASS " << assertion_count << " assertions\n";
    } catch (const std::exception& e) {
        refuse_allocations=false;
        std::cerr << "FAIL after " << assertion_count << " assertions: " << e.what() << '\n';
        return 1;
    }
}
