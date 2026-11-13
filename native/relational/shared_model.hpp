#pragma once
#include "shared_plan.hpp"

namespace refpot::relational {
class SharedModel {
    SharedPlan plan_;
    std::unique_ptr<foundation::Model> model_;
    foundation::Mode mode_;
    const SharedModel* borrowed_=nullptr;
    std::map<std::string,std::string> reuse_;
    std::vector<std::string> canonical_required() const {
        std::vector<std::string> out;
        for(const auto& n:plan_.required)out.push_back(plan_.logical_to_physical.at(n));
        return out;
    }
    auto expand(const std::map<std::string,foundation::Bag>& physical) const {
        std::map<std::string,foundation::Bag> out;
        for(const auto& d:plan_.logical_definitions)out.emplace(d.name,physical.at(plan_.logical_to_physical.at(d.name)));
        return out;
    }
    void validate_mutations(const std::vector<foundation::Mutation>& mutations) const {
        for(const auto& m:mutations) {
            auto found=std::find_if(plan_.logical_definitions.begin(),plan_.logical_definitions.end(),[&](const auto& d){return d.name==m.table;});
            if(found==plan_.logical_definitions.end())throw std::invalid_argument("unknown mutation table");
            if(found->op!="source")throw std::invalid_argument("derived relation is read-only");
        }
    }
    std::unique_ptr<SharedModel> reconfigure(const std::vector<foundation::Definition>& defs) const {
        auto next=std::make_unique<SharedModel>(defs,plan_.required,mode_);
        using Signature=decltype(definition_signature(foundation::Definition{}));
        std::map<Signature,std::string> signatures;
        for(const auto& d:plan_.physical_definitions)if(d.op!="source")signatures.emplace(definition_signature(d),d.name);
        for(const auto& original:next->plan_.physical_definitions) {
            auto d=original;
            if(d.op=="source") {
                for(const auto& old:plan_.physical_definitions)
                    if(old.op=="source"&&old.name==d.name&&definition_signature(old)==definition_signature(d))next->reuse_.emplace(d.name,old.name);
                continue;
            }
            bool reusable=true;
            auto translate=[&](std::string& name){auto p=next->reuse_.find(name);if(p==next->reuse_.end())reusable=false;else name=p->second;};
            if(d.op=="map"||d.op=="filter"||d.op=="group")translate(d.input);
            else {translate(d.left);translate(d.right);}
            if(reusable) {auto p=signatures.find(definition_signature(d));if(p!=signatures.end())next->reuse_.emplace(original.name,p->second);}
        }
        next->model_=model_->prepare_reconfigured(next->plan_.physical_definitions,next->canonical_required(),next->reuse_);
        next->borrowed_=this;
        return next;
    }
    void swap(SharedModel& other) noexcept {
        using std::swap;swap(plan_,other.plan_);swap(model_,other.model_);swap(mode_,other.mode_);swap(borrowed_,other.borrowed_);swap(reuse_,other.reuse_);
    }
public:
    explicit SharedModel(std::vector<foundation::Definition> defs,std::vector<std::string> required={},foundation::Mode mode=foundation::Mode::Overlay)
      :plan_(compile_shared_plan(defs,required)),model_(std::make_unique<foundation::Model>(plan_.physical_definitions,canonical_required(),mode)),mode_(mode) {}
    SharedModel(std::vector<foundation::Definition> defs,std::vector<std::string> required,std::map<std::string,foundation::Bag> image,foundation::Mode mode)
      :SharedModel(defs,required,mode) {
        foundation::Model validated(defs,required,std::move(image),mode);
        std::map<std::string,foundation::Bag> physical;
        for(const auto& d:plan_.logical_definitions) {
            const auto& name=plan_.logical_to_physical.at(d.name);const auto& value=validated.bag(d.name);
            auto found=physical.find(name);
            if(found==physical.end())physical.emplace(name,value);
            else if(found->second!=value)throw std::invalid_argument("inconsistent shared recovery images");
        }
        model_=std::make_unique<foundation::Model>(plan_.physical_definitions,canonical_required(),std::move(physical),mode);
    }
    const auto& definitions() const noexcept{return plan_.logical_definitions;}
    const auto& logical_definitions() const noexcept{return plan_.logical_definitions;}
    const auto& physical_definitions() const noexcept{return plan_.physical_definitions;}
    const auto& logical_to_physical() const noexcept{return plan_.logical_to_physical;}
    const auto& required_empty() const noexcept{return plan_.required;}
    const auto& required_entries() const noexcept{return plan_.required;}
    auto stats() const{return model_->stats();}
    auto candidate_stats() const{return model_->candidate_stats();}
    auto epoch() const noexcept{return model_->epoch();}
    auto maintenance_steps() const noexcept{return model_->maintenance_steps();}
    auto materialized_entries() const noexcept{return model_->materialized_entries();}
    auto source_mutation_applications() const noexcept{return model_->source_mutation_applications();}
    bool has_prepared() const noexcept{return model_->has_prepared();}
    void prepare(const std::vector<foundation::Mutation>& changes,bool validate=true) {
        try{validate_mutations(changes);model_->prepare(changes,validate);}catch(...){rollback();throw;}
    }
    void append(const std::vector<foundation::Mutation>& changes,bool validate=true) {
        try{validate_mutations(changes);model_->append(changes,validate);}catch(...){rollback();throw;}
    }
    void rollback() noexcept{model_->rollback();}
    auto preview() const{return expand(model_->preview());}
    auto prepared_changes() const{return expand(model_->prepared_changes());}
    std::map<std::string,foundation::Bag> snapshot() const {
        std::map<std::string,foundation::Bag> out;
        for(const auto& d:plan_.logical_definitions)out.emplace(d.name,bag(d.name));return out;
    }
    auto committed_state() const{return snapshot();}
    const foundation::Bag& bag(const std::string& name) const {
        const auto& target=plan_.logical_to_physical.at(name);auto found=reuse_.find(target);
        if(borrowed_&&found!=reuse_.end())return borrowed_->model_->bag(found->second);
        return model_->bag(target);
    }
    template<class F>void scan(const std::string& name,bool candidate,F fn) const{model_->scan(plan_.logical_to_physical.at(name),candidate,std::move(fn));}
    void commit(){model_->commit();}
    template<class F>void commit(F&& before_publish){model_->commit([&](const auto& changes){auto logical=expand(changes);before_publish(logical);});}
    void apply(const std::vector<foundation::Mutation>& changes){prepare(changes);commit();}
    template<class F>void add_source(const foundation::Definition& d,F&& before_publish) {
        auto defs=plan_.logical_definitions;defs.push_back(d);auto next=compile_shared_plan(defs,plan_.required);
        model_->add_source(d,std::forward<F>(before_publish));using std::swap;swap(plan_,next);
    }
    void add_source(const foundation::Definition& d){add_source(d,[](const auto&){});}
    template<class F>void add_required_empty(const std::string& name,F&& before_publish) {
        auto required=plan_.required;required.push_back(name);
        model_->add_required_empty(plan_.logical_to_physical.at(name),[&](const auto&){before_publish(required);});plan_.required.swap(required);
    }
    void add_required_empty(const std::string& name){add_required_empty(name,[](const auto&){});}
    template<class F>void add_definitions(const std::vector<foundation::Definition>& additions,F&& before_publish) {
        auto defs=plan_.logical_definitions;defs.insert(defs.end(),additions.begin(),additions.end());auto next=reconfigure(defs);
        std::map<std::string,foundation::Bag> added;std::map<std::string,std::size_t> index;
        for(std::size_t i=0;i<defs.size();++i)index.emplace(defs[i].name,i);
        for(const auto& d:additions)added.emplace(d.name,next->bag(d.name));
        before_publish(defs,index,added);next->publish_retained_from(*this,{});swap(*next);
    }
    void add_definitions(const std::vector<foundation::Definition>& additions){add_definitions(additions,[](const auto&,const auto&,const auto&){});}
    std::unique_ptr<SharedModel> replace_definitions(const std::vector<foundation::Definition>& defs,const std::set<std::string>&) const{return reconfigure(defs);}
    void publish_retained_from(SharedModel& old,const std::set<std::string>&) noexcept {
        model_->publish_reconfigured_from(*old.model_,reuse_);borrowed_=nullptr;reuse_.clear();
    }
};
}
