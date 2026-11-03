#pragma once
#include "../../native/model/model.hpp"
#include <memory>
#include <set>

namespace refpot::foundation {
using I = refpot::model::I;
using Row = refpot::model::Row;
using Bag = refpot::model::Bag;
using Definition = refpot::model::Definition;
using Mutation = refpot::model::Mutation;
namespace detail = refpot::model::detail;

enum class Mode { Modular, Overlay };
struct Stats {
    std::uint64_t source_delta_rows=0, derived_nodes=0, rows_visited=0, copied_rows=0;
    std::uint64_t delta_entries=0, publication_row_effects=0, retained_candidate_rows=0;
    std::uint64_t visibility_entries=0, delta_key_copies=0, staged_insert_rows=0;
    std::uint64_t source_lookup_row_copies=0;
};

// Volatile single-owner research engine. Both modes share this evaluator and catalog.
// copied_rows counts only full-bag materialization entries, NOT all vector/key copies.
class Model {
    struct Candidate {
        std::map<std::string, Bag> visible, changes, staged;
        Stats stats;
    };
    std::vector<Definition> defs_;
    std::vector<std::string> required_;
    std::map<std::string, std::size_t> index_;
    std::map<std::string, Bag> state_;
    std::uint64_t epoch_=0;
    Stats stats_;
    Mode mode_;
    std::unique_ptr<Candidate> active_;

    static void change(Bag& bag, const Row& row, I amount, Stats& stats) {
        if (amount && !bag.count(row)) ++stats.delta_key_copies;
        detail::change(bag, row, amount);
    }

    // Visit candidate rows in full tuple order. A false callback result stops the scan.
    // Overlay reads merge base and signed effects without a candidate bag allocation.
    template<class F>
    void visible(const Candidate& c, const std::string& name, F fn, Stats* stats=nullptr) const {
        const auto& base=state_.at(name);
        if (mode_==Mode::Modular) {
            auto materialized=c.visible.find(name);
            const auto& bag=materialized==c.visible.end() ? base : materialized->second;
            for (const auto& item:bag) {
                if (stats) ++stats->visibility_entries;
                if (!fn(item.first,item.second)) return;
            }
            return;
        }
        const auto& delta=c.changes.at(name);
        auto a=base.begin(), b=delta.begin();
        while (a!=base.end() || b!=delta.end()) {
            if (b==delta.end() || (a!=base.end() && a->first<b->first)) {
                if (stats) ++stats->visibility_entries;
                if (!fn(a->first,a->second)) return;
                ++a;
            } else if (a==base.end() || b->first<a->first) {
                if (stats) ++stats->visibility_entries;
                if (b->second<0) throw std::logic_error("negative candidate multiplicity");
                if (b->second && !fn(b->first,b->second)) return;
                ++b;
            } else {
                if (stats) stats->visibility_entries+=2;
                I count=detail::checked(static_cast<__int128>(a->second)+b->second);
                if (count<0) throw std::logic_error("negative candidate multiplicity");
                if (count && !fn(a->first,count)) return;
                ++a; ++b;
            }
        }
    }

    // Source keys are indexed in both modes. At most an old and a new tuple per key
    // survive in a canonical source delta. Return a pointer only until the next change.
    const Row* source_row(const Candidate& c, const std::string& name, I key) const {
        const auto& base=state_.at(name);
        if (mode_==Mode::Modular) {
            auto v=c.visible.find(name);
            const auto& bag=v==c.visible.end()?base:v->second;
            auto p=bag.lower_bound(Row{key});
            return p!=bag.end() && p->first[0]==key ? &p->first : nullptr;
        }
        const auto& delta=c.changes.at(name);
        for (auto p=delta.lower_bound(Row{key}); p!=delta.end() && p->first[0]==key; ++p)
            if (p->second>0) return &p->first;
        auto p=base.lower_bound(Row{key});
        if (p==base.end() || p->first[0]!=key) return nullptr;
        auto d=delta.find(p->first);
        if (d!=delta.end() && p->second+d->second==0) return nullptr;
        return &p->first;
    }

    Bag& materialize(Candidate& c, const std::string& name) const {
        auto p=c.visible.find(name);
        if (p==c.visible.end()) {
            p=c.visible.emplace(name,state_.at(name)).first;
            c.stats.copied_rows+=p->second.size();
        }
        return p->second;
    }

    void stage(Candidate& c, const std::vector<Mutation>& mutations) const {
        for (const auto& m:mutations) {
            auto p=index_.find(m.table);
            if (p==index_.end()) throw std::invalid_argument("unknown mutation table");
            const auto& definition=defs_[p->second];
            if (definition.op!="source") throw std::invalid_argument("derived relation is read-only");
            bool writing=m.op=="insert" || m.op=="update";
            if (!writing && m.op!="delete") throw std::invalid_argument("unknown mutation operation");
            if (writing && m.row.size()!=definition.width) throw std::invalid_argument("source row width mismatch");
            I key=writing?m.row[0]:m.key;
            const Row* old=source_row(c,m.table,key);
            if (m.op=="insert" && old) throw std::invalid_argument("duplicate source primary key");
            if (m.op!="insert" && !old) throw std::invalid_argument("missing source primary key");
            // Copy before editing delta: old may point at a delta node about to disappear.
            Row previous;
            if (old) { previous=*old; ++c.stats.source_lookup_row_copies; }
            Bag* bag=mode_==Mode::Modular?&materialize(c,m.table):nullptr;
            auto& delta=c.changes.at(m.table);
            if (old) {
                change(delta,previous,-1,c.stats);
                if (bag) bag->erase(previous);
            }
            if (writing) {
                change(delta,m.row,1,c.stats);
                if (bag) bag->emplace(m.row,1);
            }
        }
    }

    void derive(Candidate& c, const Definition& d) const {
        auto delta=[&](const std::string& name)->const Bag& { return c.changes.at(name); };
        bool binary=d.op=="join" || d.op=="anti" || d.op=="union";
        bool touched=binary?(!delta(d.left).empty() || !delta(d.right).empty()):!delta(d.input).empty();
        if (!touched) return;
        Bag out;
        const auto& prior=state_.at(d.name);
        auto add=[&](const Row& row,I count) { change(out,row,count,c.stats); };
        if (d.op=="map") {
            for (const auto& x:delta(d.input)) {
                ++c.stats.rows_visited;
                Row row; row.reserve(d.exprs.size());
                for (const auto& expression:d.exprs) row.push_back(detail::eval(expression,x.first));
                add(row,x.second);
            }
        } else if (d.op=="filter") {
            for (const auto& x:delta(d.input)) {
                ++c.stats.rows_visited;
                if (detail::cmp(x.first[d.column],d.cmp,d.value)) add(x.first,x.second);
            }
        } else if (d.op=="union") {
            for (const auto& x:delta(d.left)) { ++c.stats.rows_visited; add(x.first,x.second); }
            for (const auto& x:delta(d.right)) { ++c.stats.rows_visited; add(x.first,x.second); }
        } else if (d.op=="join") {
            std::map<Row,__int128> wide;
            auto pair=[&](const Row& a,I ac,const Row& b,I bc) {
                ++c.stats.rows_visited;
                if (a[d.left_key]==b[d.right_key]) {
                    Row row=a; row.insert(row.end(),b.begin(),b.end());
                    wide[row]+=static_cast<__int128>(ac)*bc;
                }
            };
            // delta_left * old_right + new_left * delta_right includes cross terms once.
            for (const auto& a:delta(d.left))
                for (const auto& b:state_.at(d.right)) pair(a.first,a.second,b.first,b.second);
            // Avoid scanning new_left when delta_right is empty, in both modes.
            if (!delta(d.right).empty()) visible(c,d.left,[&](const Row& a,I ac) {
                for (const auto& b:delta(d.right)) pair(a,ac,b.first,b.second);
                return true;
            },&c.stats);
            for (const auto& x:wide) add(x.first,detail::checked(x.second));
        } else if (d.op=="group") {
            std::set<I> keys;
            for (const auto& x:delta(d.input)) { ++c.stats.rows_visited; keys.insert(x.first[d.key]); }
            for (I key:keys) {
                for (const auto& x:prior) {
                    ++c.stats.rows_visited;
                    if (x.first[0]==key) add(x.first,-x.second);
                }
                __int128 sum=0,count=0;
                visible(c,d.input,[&](const Row& row,I multiplicity) {
                    ++c.stats.rows_visited;
                    if (row[d.key]==key) {
                        count+=multiplicity; (void)detail::checked(count);
                        sum+=static_cast<__int128>(row[d.value_column])*multiplicity;
                    }
                    return true;
                },&c.stats);
                if (count) add(Row{key,detail::checked(sum),detail::checked(count)},1);
            }
        } else if (d.op=="anti") {
            std::set<I> keys;
            for (const auto& x:delta(d.left)) { ++c.stats.rows_visited; keys.insert(x.first[d.left_key]); }
            for (const auto& x:delta(d.right)) { ++c.stats.rows_visited; keys.insert(x.first[d.right_key]); }
            for (I key:keys) {
                for (const auto& x:prior) {
                    ++c.stats.rows_visited;
                    if (x.first[d.left_key]==key) add(x.first,-x.second);
                }
                bool present=false;
                visible(c,d.right,[&](const Row& row,I) {
                    ++c.stats.rows_visited;
                    present=row[d.right_key]==key;
                    return !present;
                },&c.stats);
                if (!present) visible(c,d.left,[&](const Row& row,I count) {
                    ++c.stats.rows_visited;
                    if (row[d.left_key]==key) add(row,count);
                    return true;
                },&c.stats);
            }
        }
        // Check complete bag counts before any view consumes this delta.
        for (const auto& x:out) {
            auto old=prior.find(x.first);
            I count=detail::checked(static_cast<__int128>(old==prior.end()?0:old->second)+x.second);
            if (count<0) throw std::logic_error("negative derived multiplicity");
        }
        if (mode_==Mode::Modular && !out.empty()) {
            Bag& bag=materialize(c,d.name);
            for (const auto& x:out) detail::add(bag,x.first,x.second);
        }
        c.changes.at(d.name)=std::move(out);
        ++c.stats.derived_nodes;
    }

    void evaluate(Candidate& c,const std::vector<Mutation>& mutations) const {
        if (epoch_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("epoch exhausted");
        for (const auto& d:defs_) c.changes.emplace(d.name,Bag{});
        stage(c,mutations);
        for (const auto& d:defs_) {
            if (d.op=="source") c.stats.source_delta_rows+=c.changes.at(d.name).size();
            else derive(c,d);
        }
        for (const auto& name:required_) {
            bool nonempty=false;
            visible(c,name,[&](const Row&,I) { nonempty=true; return false; },&c.stats);
            if (nonempty) throw std::logic_error("required-empty relation is nonempty");
        }
        for (const auto& item:c.changes) {
            c.stats.delta_entries+=item.second.size();
            if (mode_==Mode::Overlay && !item.second.empty()) {
                auto& staged=c.staged.emplace(item.first,Bag{}).first->second;
                const auto& base=state_.at(item.first);
                for (const auto& x:item.second) if (x.second>0 && !base.count(x.first)) {
                    staged.emplace(x.first,x.second); ++c.stats.staged_insert_rows;
                }
            }
        }
        c.stats.publication_row_effects=c.stats.delta_entries;
        c.stats.retained_candidate_rows=c.stats.delta_entries+c.stats.staged_insert_rows;
        for (const auto& item:c.visible) c.stats.retained_candidate_rows+=item.second.size();
    }

public:
    explicit Model(std::vector<Definition> defs,std::vector<std::string> required,Mode mode=Mode::Overlay)
      : defs_(std::move(defs)),required_(std::move(required)),mode_(mode) {
        // Reuse the established binder's declared integer fragment, not its mutable storage.
        refpot::model::Model validate(defs_,required_);
        for (std::size_t i=0;i<defs_.size();++i) {
            index_.emplace(defs_[i].name,i); state_.emplace(defs_[i].name,Bag{});
        }
    }
    void prepare(const std::vector<Mutation>& mutations) {
        if (active_) { active_.reset(); throw std::logic_error("transaction already active"); }
        auto candidate=std::make_unique<Candidate>();
        evaluate(*candidate,mutations);
        active_=std::move(candidate);
    }
    std::map<std::string,Bag> preview() const {
        if (!active_) throw std::logic_error("no active transaction");
        std::map<std::string,Bag> output;
        for (const auto& item:state_) {
            auto& bag=output.emplace(item.first,Bag{}).first->second;
            visible(*active_,item.first,[&](const Row& row,I count) { bag.emplace(row,count); return true; });
        }
        return output;
    }
    // Borrow rows only for the callback lifetime; callbacks must not mutate this model.
    // Ad hoc queries can read the same candidate visibility without exporting all tables.
    template<class F>
    void scan(const std::string& name, bool candidate, F fn) const {
        if (candidate) {
            if (!active_) throw std::logic_error("no active transaction");
            visible(*active_,name,fn);
        } else {
            for (const auto& item:state_.at(name))
                if (!fn(item.first,item.second)) return;
        }
    }
    bool has_prepared() const noexcept { return static_cast<bool>(active_); }
    void commit() {
        if (!active_) throw std::logic_error("no active transaction");
        if (mode_==Mode::Modular) {
            // All map allocation and relation preparation finished in prepare().
            for (auto& item:active_->visible) state_.at(item.first).swap(item.second);
        } else {
            for (const auto& item:active_->changes) {
                auto& target=state_.at(item.first);
                for (const auto& x:item.second) {
                    auto old=target.find(x.first);
                    // Checked against this exact base during prepare; no intervening writers.
                    I count=static_cast<I>(static_cast<__int128>(old==target.end()?0:old->second)+x.second);
                    if (!count) { if (old!=target.end()) target.erase(old); }
                    else if (old!=target.end()) old->second=count;
                    else {
                        auto node=active_->staged.at(item.first).extract(x.first);
                        target.insert(std::move(node));
                    }
                }
            }
        }
        stats_=active_->stats; ++epoch_; active_.reset();
    }
    void rollback() noexcept { active_.reset(); }
    void apply(const std::vector<Mutation>& mutations) { prepare(mutations); commit(); }
    std::map<std::string,Bag> snapshot() const { return state_; }
    const Bag& bag(const std::string& name) const { return state_.at(name); }
    Stats stats() const { return stats_; }
    std::uint64_t epoch() const { return epoch_; }
};
}
