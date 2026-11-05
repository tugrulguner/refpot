#include "../native/relational/foundation.hpp"
#include <cassert>
#include <iostream>

using namespace refpot::foundation;

int main() {
    Definition source; source.name="src"; source.op="source"; source.width=3;
    Definition projected; projected.name="projected"; projected.op="map";
    projected.input="src"; projected.exprs={{"c0"},{"c1"},{"c2"}};
    {
        Model model({source,projected},{},Mode::Overlay);
        std::vector<Mutation> seed;
        for(I i=0;i<200;++i)seed.push_back({"insert","src",{i,i%10,1},0});
        model.apply(seed);
        model.prepare({{"insert","src",{300,3,7},0}});
        model.append({{"insert","src",{301,3,11},0}});
        const auto stats=model.candidate_stats();
        assert(stats.rows_visited<=8); // bounded statement work, not a 200-row prior scan
        assert(model.preview().at("projected").count({301,3,11}));
        model.rollback();
    }

    {
        Definition bag;bag.name="bag";bag.op="map";bag.input="src";bag.exprs={{"c1"}};
        Model model({source,bag},{},Mode::Overlay);
        model.prepare({{"insert","src",{1,7,0},0}});
        model.append({{"insert","src",{2,7,0},0}});
        const auto preview=model.preview();
        model.commit();
        assert(model.snapshot()==preview); // staged absent-base node must have count 2
        model.prepare({{"insert","src",{3,8,0},0}});
        model.append({{"delete","src",{},3}});
        assert(model.active_candidate_entries()==0); // cancelled publication nodes reclaimed
        model.rollback();
    }

    Definition grouped; grouped.name="grouped"; grouped.op="group";
    grouped.input="projected"; grouped.key=1; grouped.value_column=2;
    Definition right; right.name="right"; right.op="source"; right.width=2;
    Definition joined; joined.name="joined"; joined.op="join";
    joined.left="projected"; joined.right="right"; joined.left_key=1; joined.right_key=0;
    Definition absent; absent.name="absent"; absent.op="anti";
    absent.left="projected"; absent.right="right"; absent.left_key=1; absent.right_key=0;

    for (auto mode : {Mode::Overlay, Mode::Modular}) {
        Model model({source, projected, grouped, right, joined, absent}, {}, mode);
        std::vector<Mutation> seed;
        for (I i=0; i<200; ++i) seed.push_back({"insert","src",{i,i%10,1},0});
        model.apply(seed);
        model.apply({{"insert","right",{3,30},0}});

        model.prepare({{"insert","src",{300,3,7},0}});
        assert(model.preview().at("grouped").count({3,27,21}));
        model.append({{"insert","src",{301,3,11},0}});
        auto candidate=model.preview();
        assert(candidate.at("grouped").count({3,38,22}));
        assert(candidate.at("joined").count({300,3,7,3,30}));
        assert(candidate.at("joined").count({301,3,11,3,30}));
        assert(candidate.at("absent").count({300,3,7})==0);
        model.append({{"delete","right",{},3}});
        candidate=model.preview();
        assert(candidate.at("joined").count({300,3,7,3,30})==0);
        assert(candidate.at("absent").count({300,3,7}));
        model.append({{"insert","right",{3,31},0}});
        candidate=model.preview();
        assert(candidate.at("joined").count({300,3,7,3,31}));
        assert(candidate.at("absent").count({300,3,7})==0);
        model.commit();
        assert(model.snapshot()==candidate);
    }
    std::cout << "transaction delta tests passed\n";
}
