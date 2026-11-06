#pragma once
#include "operators.hpp"
#include <memory>
#include <optional>
#include <set>

namespace refpot::foundation {
using I = refpot::model::I;
using Row = refpot::model::Row;
using Bag = refpot::model::Bag;
struct Definition : refpot::model::Definition {
    std::optional<std::size_t> right_column;
    Definition()=default;
    Definition(const refpot::model::Definition& base) : refpot::model::Definition(base) {}
};
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
        std::map<std::string,I> row_counts;
        bool validate=true;
    };
    std::vector<Definition> defs_;
    std::vector<std::string> required_;
    std::map<std::string, std::size_t> index_;
    std::map<std::string, Bag> state_;
    std::map<std::string,I> row_counts_;
    std::uint64_t epoch_=0;
    Stats stats_;
    Mode mode_;
    bool sources_only_=true;
    mutable std::uint64_t source_mutation_applications_=0, materialized_entries_=0, maintenance_steps_=0;
    std::unique_ptr<Candidate> active_;

    void maintenance_step(Stats& stats,std::size_t count=1,bool visibility=false) const {
        maintenance_steps_+=count;
        if(visibility)stats.visibility_entries+=count;else stats.rows_visited+=count;
        if(stats.rows_visited+stats.visibility_entries>1000000)throw std::length_error("maintenance work limit exceeded");
    }

    static void validate_column_references(const std::vector<Definition>& defs) {
        std::map<std::string,std::size_t> widths;
        for(const auto& d:defs) {
            std::size_t width=d.op=="source"?d.width:d.op=="map"?d.exprs.size():d.op=="group"?3:
                d.op=="join"?widths.at(d.left)+widths.at(d.right):widths.at(d.op=="filter"?d.input:d.left);
            if(d.right_column&&(d.op!="filter"||*d.right_column>=width))throw std::invalid_argument("filter column out of bounds");
            widths.emplace(d.name,width);
        }
    }

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
                if (stats) maintenance_step(*stats,1,true);
                if (!fn(item.first,item.second)) return;
            }
            return;
        }
        const auto& delta=c.changes.at(name);
        auto a=base.begin(), b=delta.begin();
        while (a!=base.end() || b!=delta.end()) {
            if (b==delta.end() || (a!=base.end() && a->first<b->first)) {
                if (stats) maintenance_step(*stats,1,true);
                if (!fn(a->first,a->second)) return;
                ++a;
            } else if (a==base.end() || b->first<a->first) {
                if (stats) maintenance_step(*stats,1,true);
                if (b->second<0) throw std::logic_error("negative candidate multiplicity");
                if (b->second && !fn(b->first,b->second)) return;
                ++b;
            } else {
                if (stats) maintenance_step(*stats,2,true);
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
            materialized_entries_+=p->second.size();
        }
        return p->second;
    }

    void stage(Candidate& c, const std::vector<Mutation>& mutations,
               std::map<std::string,Bag>* statement_delta=nullptr) const {
        for (const auto& m:mutations) {
            ++source_mutation_applications_;
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
                c.row_counts[m.table]=detail::checked(static_cast<__int128>(c.row_counts.at(m.table))-1);
                if (statement_delta) change((*statement_delta)[m.table],previous,-1,c.stats);
                if (bag) bag->erase(previous);
            }
            if (writing) {
                change(delta,m.row,1,c.stats);
                c.row_counts[m.table]=detail::checked(static_cast<__int128>(c.row_counts.at(m.table))+1);
                if (statement_delta) change((*statement_delta)[m.table],m.row,1,c.stats);
                if (bag) bag->emplace(m.row,1);
            }
        }
    }

    Bag derive_statement(Candidate& c, const Definition& d,
                         const std::map<std::string,Bag>& statement_delta) const {
        const auto& local=[&](const std::string& name)->const Bag& {
            static const Bag empty;
            auto p=statement_delta.find(name);
            return p==statement_delta.end()?empty:p->second;
        };
        const bool binary=d.op=="join"||d.op=="anti"||d.op=="union";
        const bool touched=binary?(!local(d.left).empty()||!local(d.right).empty()):!local(d.input).empty();
        if(!touched)return {};
        Bag out;
        auto add=[&](const Row& row,I amount) {
            if(!amount)return;
            auto p=out.find(row);
            I combined=detail::checked(static_cast<__int128>(p==out.end()?0:p->second)+amount);
            if(!combined) {if(p!=out.end())out.erase(p);return;}
            if(p==out.end()&&out.size()>=200000)throw std::length_error("derived delta limit exceeded");
            if(p==out.end())++c.stats.delta_key_copies;
            out[row]=combined;
        };
        if(d.op=="map") {
            for(const auto& x:local(d.input)) {
                maintenance_step(c.stats);Row row;
                for(const auto& expression:d.exprs)row.push_back(detail::eval(expression,x.first));
                add(row,x.second);
            }
        } else if(d.op=="filter") {
            auto predicate=relational::BoundPredicate::bind(d.column,d.cmp,d.value);
            predicate.right_column=d.right_column;
            for(const auto& x:local(d.input)){maintenance_step(c.stats);if(predicate.matches(x.first))add(x.first,x.second);}
        } else if(d.op=="union") {
            for(const auto& name:{d.left,d.right})for(const auto& x:local(name)){maintenance_step(c.stats);add(x.first,x.second);}
        } else if(d.op=="join") {
            std::map<Row,__int128> wide;
            auto pair=[&](const Row& a,I ac,const Row& b,I bc) {
                maintenance_step(c.stats);
                if(a[d.left_key]==b[d.right_key]) {
                    Row row=a;row.insert(row.end(),b.begin(),b.end());
                    if(!wide.count(row)&&wide.size()>=200000)throw std::length_error("derived delta limit exceeded");
                    wide[row]+=static_cast<__int128>(ac)*bc;
                }
            };
            // dL*newR + newL*dR - dL*dR: uses current candidate inputs,
            // including simultaneous deletion and self-join cross terms exactly once.
            for(const auto& a:local(d.left))visible(c,d.right,[&](const Row& b,I bc){pair(a.first,a.second,b,bc);return true;},&c.stats);
            if(!local(d.right).empty())visible(c,d.left,[&](const Row& a,I ac){for(const auto& b:local(d.right))pair(a,ac,b.first,b.second);return true;},&c.stats);
            for(const auto& a:local(d.left))for(const auto& b:local(d.right))pair(a.first,-a.second,b.first,b.second);
            for(const auto& x:wide)add(x.first,detail::checked(x.second));
        } else if(d.op=="group") {
            struct Effect { __int128 sum=0,count=0; };
            std::map<I,Effect> effects;
            for(const auto& x:local(d.input)) {
                maintenance_step(c.stats);
                auto& effect=effects[x.first[d.key]];
                effect.sum+=static_cast<__int128>(x.first[d.value_column])*x.second;
                effect.count+=x.second;
            }
            for(const auto& entry:effects) {
                maintenance_step(c.stats);
                const I key=entry.first;
                // Group output is uniquely keyed in column zero, just like a source.
                const Row* prior=source_row(c,d.name,key);
                const __int128 count=(prior?(*prior)[2]:0)+entry.second.count;
                const __int128 sum=(prior?(*prior)[1]:0)+entry.second.sum;
                if(prior)add(*prior,-1);
                if(count<0)throw std::logic_error("negative aggregate count");
                if(count)add({key,detail::checked(sum),detail::checked(count)},1);
            }
        } else if(d.op=="anti") {
            std::set<I> keys;
            for(const auto& x:local(d.left)){maintenance_step(c.stats);keys.insert(x.first[d.left_key]);}
            for(const auto& x:local(d.right)){maintenance_step(c.stats);keys.insert(x.first[d.right_key]);}
            // The output still holds the pre-statement candidate here. Replace
            // only affected keys; no reconstruction from surviving input rows.
            visible(c,d.name,[&](const Row& row,I count) {
                if(keys.count(row[d.left_key]))add(row,-count);
                return true;
            },&c.stats);
            std::set<I> present;
            visible(c,d.right,[&](const Row& row,I) {
                if(keys.count(row[d.right_key]))present.insert(row[d.right_key]);
                return true;
            },&c.stats);
            visible(c,d.left,[&](const Row& row,I count) {
                const I key=row[d.left_key];
                if(keys.count(key)&&!present.count(key))add(row,count);
                return true;
            },&c.stats);
        }
        __int128 row_change=0;
        auto& canonical_delta=c.changes.at(d.name);
        for(const auto& x:out) {
            maintenance_step(c.stats);
            auto p=canonical_delta.find(x.first);
            I canonical=detail::checked(static_cast<__int128>(p==canonical_delta.end()?0:p->second)+x.second);
            auto base=state_.at(d.name).find(x.first);
            I current=detail::checked(static_cast<__int128>(base==state_.at(d.name).end()?0:base->second)+canonical);
            if(current<0)throw std::logic_error("negative derived multiplicity statement check: "+d.name);
            row_change+=x.second;
        }
        const __int128 final_rows=static_cast<__int128>(c.row_counts.at(d.name))+row_change;
        if(final_rows<0||final_rows>100000)throw std::length_error("derived row limit exceeded");
        for(const auto& x:out) {maintenance_step(c.stats);change(canonical_delta,x.first,x.second,c.stats);}
        if(canonical_delta.size()>200000)throw std::length_error("derived delta limit exceeded");
        c.row_counts[d.name]=static_cast<I>(final_rows);
        if(mode_==Mode::Modular&&!out.empty()) {
            Bag& target=materialize(c,d.name);
            for(const auto& x:out)detail::add(target,x.first,x.second);
        }
        ++c.stats.derived_nodes;
        return out;
    }

    void derive(Candidate& c, const Definition& d) const {
        auto delta=[&](const std::string& name)->const Bag& { return c.changes.at(name); };
        bool binary=d.op=="join" || d.op=="anti" || d.op=="union";
        bool touched=binary?(!delta(d.left).empty() || !delta(d.right).empty()):!delta(d.input).empty();
        if (!touched) return;
        Bag out;
        const auto& prior=state_.at(d.name);
        auto add=[&](const Row& row,I count) {
            if(count&&!out.count(row)&&out.size()>=200000)throw std::length_error("derived delta limit exceeded");
            change(out,row,count,c.stats);
        };
        if (d.op=="map") {
            for (const auto& x:delta(d.input)) {
                maintenance_step(c.stats);
                Row row; row.reserve(d.exprs.size());
                for (const auto& expression:d.exprs) row.push_back(detail::eval(expression,x.first));
                add(row,x.second);
            }
        } else if (d.op=="filter") {
            auto predicate=relational::BoundPredicate::bind(d.column,d.cmp,d.value);
            predicate.right_column=d.right_column;
            for (const auto& x:delta(d.input)) {
                maintenance_step(c.stats);
                if (predicate.matches(x.first)) add(x.first,x.second);
            }
        } else if (d.op=="union") {
            for (const auto& x:delta(d.left)) { maintenance_step(c.stats); add(x.first,x.second); }
            for (const auto& x:delta(d.right)) { maintenance_step(c.stats); add(x.first,x.second); }
        } else if (d.op=="join") {
            std::map<Row,__int128> wide;
            auto pair=[&](const Row& a,I ac,const Row& b,I bc) {
                maintenance_step(c.stats);
                if (a[d.left_key]==b[d.right_key]) {
                    Row row=a; row.insert(row.end(),b.begin(),b.end());
                    if(!wide.count(row)&&wide.size()>=200000)throw std::length_error("derived delta limit exceeded");
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
            for (const auto& x:delta(d.input)) { maintenance_step(c.stats); keys.insert(x.first[d.key]); }
            for (I key:keys) {
                for (const auto& x:prior) {
                    maintenance_step(c.stats);
                    if (x.first[0]==key) add(x.first,-x.second);
                }
                relational::Aggregate aggregate;
                visible(c,d.input,[&](const Row& row,I multiplicity) {
                    maintenance_step(c.stats);
                    if (row[d.key]==key) {
                        aggregate.add(row[d.value_column],multiplicity);
                    }
                    return true;
                },&c.stats);
                if (aggregate.count) add(Row{key,aggregate.value(),aggregate.count},1);
            }
        } else if (d.op=="anti") {
            std::set<I> keys;
            for (const auto& x:delta(d.left)) { maintenance_step(c.stats); keys.insert(x.first[d.left_key]); }
            for (const auto& x:delta(d.right)) { maintenance_step(c.stats); keys.insert(x.first[d.right_key]); }
            for (I key:keys) {
                for (const auto& x:prior) {
                    maintenance_step(c.stats);
                    if (x.first[d.left_key]==key) add(x.first,-x.second);
                }
                bool present=false;
                visible(c,d.right,[&](const Row& row,I) {
                    maintenance_step(c.stats);
                    present=row[d.right_key]==key;
                    return !present;
                },&c.stats);
                if (!present) visible(c,d.left,[&](const Row& row,I count) {
                    maintenance_step(c.stats);
                    if (row[d.left_key]==key) add(row,count);
                    return true;
                },&c.stats);
            }
        }
        // Check logical rows, not just distinct tuples, before any consumer/publication.
        __int128 rows=0;
        for(const auto& x:prior){maintenance_step(c.stats);rows+=x.second;}
        for (const auto& x:out) {
            maintenance_step(c.stats);rows+=x.second;
            auto old=prior.find(x.first);
            I count=detail::checked(static_cast<__int128>(old==prior.end()?0:old->second)+x.second);
            if (count<0) throw std::logic_error("negative derived multiplicity");
        }
        if(rows<0||rows>100000)throw std::length_error("derived row limit exceeded");
        c.row_counts[d.name]=static_cast<I>(rows);
        if (mode_==Mode::Modular && !out.empty()) {
            Bag& bag=materialize(c,d.name);
            for (const auto& x:out) detail::add(bag,x.first,x.second);
        }
        c.changes.at(d.name)=std::move(out);
        ++c.stats.derived_nodes;
    }

    void evaluate(Candidate& c,const std::vector<Mutation>& mutations, bool append=false) const {
        if (epoch_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("epoch exhausted");
        std::map<std::string,Bag> statement_delta;
        if (!append) {
            for (const auto& d:defs_) c.changes.emplace(d.name,Bag{});
            stage(c,mutations);
            for (const auto& d:defs_) {
                if (d.op=="source") c.stats.source_delta_rows+=c.changes.at(d.name).size();
                else derive(c,d);
            }
        } else {
            c.stats={};
            stage(c,mutations,&statement_delta);
            for (const auto& d:defs_) {
                if(d.op=="source") c.stats.source_delta_rows+=statement_delta[d.name].size();
                else statement_delta[d.name]=derive_statement(c,d,statement_delta);
            }
        }
        if (c.validate) for (const auto& name:required_) {
            bool nonempty=false;
            visible(c,name,[&](const Row&,I) { nonempty=true; return false; },&c.stats);
            if (nonempty) throw std::logic_error("required-empty relation is nonempty");
        }
        const auto& changed=append?statement_delta:c.changes;
        if(mode_==Mode::Overlay)for(const auto& item:changed) {
            if(item.second.empty())continue;
            auto& staged=c.staged[item.first];
            const auto& base=state_.at(item.first);
            const auto& canonical=c.changes.at(item.first);
            for(const auto& x:item.second) {
                maintenance_step(c.stats);
                auto current=canonical.find(x.first);
                if(current!=canonical.end()&&current->second>0&&!base.count(x.first))
                    staged.insert_or_assign(x.first,current->second);
                else staged.erase(x.first);
            }
        }
        for(const auto& item:c.changes)c.stats.delta_entries+=item.second.size();
        for(const auto& item:c.staged)c.stats.staged_insert_rows+=item.second.size();
        c.stats.publication_row_effects=c.stats.delta_entries;
        c.stats.retained_candidate_rows=c.stats.delta_entries+c.stats.staged_insert_rows;
        for (const auto& item:c.visible) c.stats.retained_candidate_rows+=item.second.size();
    }

public:
    explicit Model(std::vector<Definition> defs,std::vector<std::string> required,Mode mode=Mode::Overlay)
      : defs_(std::move(defs)),required_(std::move(required)),mode_(mode) {
        if(defs_.size()>1024)throw std::length_error("catalog definition limit exceeded");
        // Reuse the established binder's declared integer fragment, not its mutable storage.
        std::vector<refpot::model::Definition> base_defs; for(const auto& d:defs_) base_defs.push_back(d);
        refpot::model::Model validate(std::move(base_defs),required_);
        validate_column_references(defs_);
        for (std::size_t i=0;i<defs_.size();++i) {
            index_.emplace(defs_[i].name,i); state_.emplace(defs_[i].name,Bag{});
            row_counts_.emplace(defs_[i].name,0);
            sources_only_ &= defs_[i].op=="source";
        }
    }
    // Restore a complete accepted image privately without rebuilding derived state.
    Model(std::vector<Definition> defs,std::vector<std::string> required,
          std::map<std::string,Bag> image,Mode mode)
      : Model(std::move(defs),std::move(required),mode) {
        if(image.size()!=defs_.size())throw std::invalid_argument("recovery relation count mismatch");
        std::map<std::string,std::size_t> widths;
        for(const auto& d:defs_) {
            const std::size_t width=d.op=="source"?d.width:d.op=="map"?d.exprs.size():d.op=="group"?3:
                d.op=="join"?widths.at(d.left)+widths.at(d.right):
                d.op=="filter"?widths.at(d.input):widths.at(d.left);
            auto found=image.find(d.name);
            if(found==image.end())throw std::invalid_argument("recovery relation missing");
            __int128 rows=0;
            std::set<I> source_keys;
            for(const auto& entry:found->second) {
                if(entry.second<=0||entry.first.size()!=width)
                    throw std::invalid_argument("invalid recovery tuple or multiplicity");
                rows+=entry.second;
                if(rows>100000)throw std::length_error("recovery relation row limit exceeded");
                if(d.op=="source") {
                    if(entry.second!=1)throw std::invalid_argument("source multiplicity must be one in recovery image");
                    if(!source_keys.insert(entry.first[0]).second)
                        throw std::invalid_argument("duplicate source primary key in recovery image");
                }
            }
            state_.at(d.name).swap(found->second);
            row_counts_.at(d.name)=static_cast<I>(rows);
            widths.emplace(d.name,width);
        }
        for(const auto& name:required_)if(!state_.at(name).empty())
            throw std::invalid_argument("recovery image violates required-empty constraint");
    }
    void add_source(const Definition& definition) { add_source(definition,[](const auto&){}); }
    template<class BeforePublish>
    void add_source(const Definition& definition,BeforePublish&& before_publish) {
        if(defs_.size()>=1024)throw std::length_error("catalog definition limit exceeded");
        if (active_) throw std::logic_error("cannot change catalog during transaction");
        if (epoch_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("epoch exhausted");
        if (definition.op!="source" || !definition.width) throw std::invalid_argument("invalid source definition");
        refpot::model::Model check({definition},{});
        if (index_.count(definition.name)) throw std::invalid_argument("duplicate relation");
        auto defs=defs_; auto index=index_;
        defs.push_back(definition); index.emplace(definition.name,defs.size()-1);
        std::map<std::string,Bag> empty; empty.emplace(definition.name,Bag{});
        auto node=empty.extract(definition.name);
        std::map<std::string,I> count_node_map;count_node_map.emplace(definition.name,0);
        auto count_node=count_node_map.extract(definition.name);
        before_publish(definition);
        defs_.swap(defs); index_.swap(index);
        state_.insert(std::move(node)); row_counts_.insert(std::move(count_node));
        ++epoch_;
    }
    void add_required_empty(const std::string& name) { add_required_empty(name,[](const auto&){}); }
    template<class BeforePublish>
    void add_required_empty(const std::string& name,BeforePublish&& before_publish) {
        if(active_) throw std::logic_error("cannot change constraints during transaction");
        auto p=index_.find(name); if(p==index_.end()) throw std::invalid_argument("unknown required-empty relation");
        if(!state_.at(name).empty()) throw std::logic_error("required-empty relation is nonempty");
        // Each SQL assertion keeps its own name-to-relation catalog entry, even
        // when another assertion already requires this relation to be empty.
        auto next=required_; next.push_back(name); before_publish(next); required_.swap(next);
    }
    void add_definitions(const std::vector<Definition>& additions) { add_definitions(additions,[](const auto&,const auto&,const auto&){}); }
    template<class BeforePublish>
    void add_definitions(const std::vector<Definition>& additions,BeforePublish&& before_publish) {
        if(active_) throw std::logic_error("cannot change catalog during transaction");
        if(additions.empty()) return;
        if(defs_.size()+additions.size()>1024) throw std::length_error("catalog definition limit exceeded");
        // Copy metadata only. Existing relation nodes are never copied or replaced.
        auto defs=defs_; auto index=index_;
        for(const auto& d:additions) {
            if(d.op=="source" || d.name.empty() || index.count(d.name)) throw std::invalid_argument("invalid or duplicate derived definition");
            index.emplace(d.name,defs.size());defs.push_back(d);
        }
        std::vector<refpot::model::Definition> base_defs;
        for(const auto& d:defs)base_defs.push_back(d);
        refpot::model::Model check(std::move(base_defs),{});
        validate_column_references(defs);
        std::map<std::string,Bag> added;
        std::map<std::string,I> added_counts;
        std::size_t visits=0;
        auto tick=[&] { ++maintenance_steps_;if(++visits>1000000)throw std::length_error("maintenance work limit exceeded"); };
        auto parent=[&](const std::string& name)->const Bag& {
            auto it=added.find(name);return it==added.end()?state_.at(name):it->second;
        };
        for(const auto& d:additions) {
            Bag out;I rows=0;
            auto add=[&](const Row& r,I n) {
                if(n<0||n>100000-rows)throw std::length_error("derived row limit exceeded");
                rows+=n;detail::change(out,r,n);
            };
            if(d.op=="map"||d.op=="filter") {
                auto pred=relational::BoundPredicate::bind(d.column,d.cmp.empty()?"eq":d.cmp,d.value);
                pred.right_column=d.right_column;
                for(const auto& x:parent(d.input)) {
                    tick();
                    if(d.op=="map") {Row r;for(const auto& e:d.exprs)r.push_back(detail::eval(e,x.first));add(r,x.second);}
                    else if(pred.matches(x.first))add(x.first,x.second);
                }
            } else if(d.op=="union") {
                for(const auto& name:{d.left,d.right})for(const auto& x:parent(name)){tick();add(x.first,x.second);}
            } else if(d.op=="join"||d.op=="anti") {
                for(const auto& left:parent(d.left)) {
                    tick();bool matched=false;
                    for(const auto& right:parent(d.right)) {
                        tick();if(left.first[d.left_key]!=right.first[d.right_key])continue;
                        matched=true;if(d.op=="anti")break;
                        const auto n=detail::checked(static_cast<__int128>(left.second)*right.second);
                        if(n>100000-rows)throw std::length_error("derived row limit exceeded");
                        Row r=left.first;r.insert(r.end(),right.first.begin(),right.first.end());add(r,n);
                    }
                    if(d.op=="anti"&&!matched)add(left.first,left.second);
                }
            } else if(d.op=="group") {
                std::map<I,relational::Aggregate> groups;
                for(const auto& x:parent(d.input)){tick();groups[x.first[d.key]].add(x.first[d.value_column],x.second);}
                for(const auto& x:groups){tick();add({x.first,x.second.value(),x.second.count},1);}
            } else throw std::invalid_argument("unsupported initialization operator");
            added.emplace(d.name,std::move(out));
            added_counts.emplace(d.name,rows);
        }
        // All allocation/validation has finished. Persist while the model is still
        // unchanged; node transfers and swaps below are allocation-free publication.
        before_publish(defs,index,added);
        state_.merge(added);row_counts_.merge(added_counts);defs_.swap(defs);index_.swap(index);sources_only_=false;++epoch_;
    }
    void prepare(const std::vector<Mutation>& mutations,bool validate=true) {
        if (active_) { rollback(); throw std::logic_error("transaction already active"); }
        auto candidate=std::make_unique<Candidate>(); candidate->validate=validate;
        candidate->row_counts=row_counts_;
        evaluate(*candidate,mutations);
        active_=std::move(candidate);
    }
    void append(const std::vector<Mutation>& mutations,bool validate=true) {
        if (!active_) { prepare(mutations,validate); return; }
        active_->validate=validate;
        // A failed statement invalidates the WHOLE transaction. This contract lets
        // us extend its private candidate in place instead of copying it first.
        try {
            if (!sources_only_) { evaluate(*active_,mutations,true); return; }
            auto& c=*active_;
            stage(c,mutations);
            if (mode_==Mode::Overlay) for (const auto& m:mutations) {
                I key=m.op=="delete"?m.key:m.row[0];
                auto& staged=c.staged[m.table];
                auto old=staged.lower_bound(Row{key});
                while(old!=staged.end() && old->first[0]==key) old=staged.erase(old);
                const auto& delta=c.changes.at(m.table);
                const auto& base=state_.at(m.table);
                for(auto row=delta.lower_bound(Row{key});row!=delta.end() && row->first[0]==key;++row)
                    if(row->second>0 && !base.count(row->first)) staged.emplace(row->first,row->second);
            }
            c.stats.source_delta_rows=0; c.stats.delta_entries=0;
            c.stats.staged_insert_rows=0; c.stats.retained_candidate_rows=0;
            for(const auto& item:c.changes) c.stats.delta_entries+=item.second.size();
            for(const auto& item:c.staged) c.stats.staged_insert_rows+=item.second.size();
            c.stats.source_delta_rows=c.stats.delta_entries;
            c.stats.publication_row_effects=c.stats.delta_entries;
            c.stats.retained_candidate_rows=c.stats.delta_entries+c.stats.staged_insert_rows;
            for(const auto& item:c.visible) c.stats.retained_candidate_rows+=item.second.size();
        } catch (...) { rollback(); throw; }
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
    std::uint64_t active_candidate_entries() const noexcept {
        if (!active_) return 0;
        std::uint64_t n=0;
        for (const auto& x:active_->visible) n+=x.second.size();
        for (const auto& x:active_->changes) n+=x.second.size();
        for (const auto& x:active_->staged) n+=x.second.size();
        return n;
    }
    void validate_constraints() const {
        for(const auto& name:required_) {
            bool nonempty=false;
            if(active_) visible(*active_,name,[&](const Row&,I){nonempty=true;return false;});
            else nonempty=!state_.at(name).empty();
            if(nonempty) throw std::logic_error("required-empty relation is nonempty");
        }
    }
    void commit() { commit([](const auto&){}); }
    template<class BeforePublish>
    void commit(BeforePublish&& before_publish) {
        if (!active_) throw std::logic_error("no active transaction");
        validate_constraints();
        before_publish(active_->changes);
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
        row_counts_.swap(active_->row_counts);
        stats_=active_->stats; ++epoch_; active_.reset();
    }
    void rollback() noexcept { active_.reset(); }
    void apply(const std::vector<Mutation>& mutations) { prepare(mutations,true); commit(); }
    std::map<std::string,Bag> snapshot() const { return state_; }
    const Bag& bag(const std::string& name) const { return state_.at(name); }
    Stats stats() const { return stats_; }
    Stats candidate_stats() const {
        if(!active_)throw std::logic_error("no active transaction");
        return active_->stats;
    }
    std::uint64_t maintenance_steps() const noexcept { return maintenance_steps_; }
    std::uint64_t source_mutation_applications() const { return source_mutation_applications_; }
    std::uint64_t materialized_entries() const { return materialized_entries_; }
    std::uint64_t epoch() const { return epoch_; }
    const std::vector<Definition>& definitions() const noexcept { return defs_; }
    const std::vector<std::string>& required_empty() const noexcept { return required_; }
    const std::map<std::string,Bag>& committed_state() const noexcept { return state_; }
    const std::map<std::string,Bag>& prepared_changes() const {
        if(!active_)throw std::logic_error("no active transaction");
        return active_->changes;
    }
};
}
