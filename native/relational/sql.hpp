#pragma once
#include "shared_model.hpp"
#include "persistence.hpp"
#include <charconv>
#include <functional>
#include <limits>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace refpot::sqlpreview {
using I = foundation::I;
using Row = foundation::Row;
struct Result {
    std::vector<std::string> columns;
    std::vector<std::vector<std::optional<I>>> rows;
    std::size_t affected=0;
    std::string plan;
};
namespace syntax {
inline bool alpha(char c) {return (c>='a'&&c<='z')||(c>='A'&&c<='Z');}
inline bool digit(char c) {return c>='0'&&c<='9';}
inline std::string lower(std::string s) {for(char& c:s)if(c>='A'&&c<='Z')c+=32;return s;}
inline std::vector<std::string> lex(const std::string& q) {
    if(q.size()>65536)throw std::invalid_argument("SQL exceeds 65536 bytes");
    std::vector<std::string> tokens;
    for(std::size_t i=0;i<q.size();) {
        char c=q[i];
        if(c==' '||c=='\t'||c=='\r'||c=='\n'){++i;continue;}
        std::size_t begin=i++;
        if(alpha(c)) {while(i<q.size()&&(alpha(q[i])||digit(q[i])||q[i]=='_'))++i;}
        else if(digit(c)||c=='-') {while(i<q.size()&&digit(q[i]))++i;}
        else if(std::string("(),;.*?=<>!").find(c)!=std::string::npos) {
            if(i<q.size()&&((c=='<'&&(q[i]=='='||q[i]=='>'))||((c=='>'||c=='!')&&q[i]=='=')))++i;
        } else throw std::invalid_argument("unsupported SQL token");
        tokens.push_back(lower(q.substr(begin,i-begin)));
        if(tokens.size()>8192)throw std::invalid_argument("SQL token limit exceeded");
    }
    if(!tokens.empty()&&tokens.back()==";")tokens.pop_back();
    for(const auto& t:tokens)if(t==";")throw std::invalid_argument("multiple SQL statements unsupported");
    return tokens;
}
struct Ref {std::string qualifier,name;};
class Parser {
    std::vector<std::string> tokens_;
    const std::vector<I>& params_;
    std::size_t at_=0,param_=0;
public:
    Parser(const std::string& q,const std::vector<I>& p):tokens_(lex(q)),params_(p){}
    std::string peek(std::size_t ahead=0)const{return at_+ahead<tokens_.size()?tokens_[at_+ahead]:"";}
    std::string take(){if(at_==tokens_.size())throw std::invalid_argument("unexpected end of SQL");return tokens_[at_++];}
    bool match(const char* s){if(peek()!=s)return false;++at_;return true;}
    void need(const char* s){if(!match(s))throw std::invalid_argument(std::string("expected ")+s);}
    std::string name(){auto s=take();if(s.size()>64||!alpha(s[0]))throw std::invalid_argument("expected identifier (max 64 bytes)");return s;}
    Ref ref(){auto a=name();if(match("."))return {a,name()};return {"",a};}
    I value(){auto s=take();if(s=="?"){if(param_==params_.size())throw std::invalid_argument("parameter arity mismatch");return params_[param_++];}
        I n=0;auto r=std::from_chars(s.data(),s.data()+s.size(),n);
        if(r.ec!=std::errc{}||r.ptr!=s.data()+s.size())throw std::invalid_argument("expected signed 64-bit literal or parameter");return n;}
    void end(){if(!peek().empty())throw std::invalid_argument("unsupported or trailing SQL: "+peek());if(param_!=params_.size())throw std::invalid_argument("parameter arity mismatch");}
};
}
class Database {
    using Table=sqlpersistence::Table;
    using Bag=foundation::Bag;
    struct Source {std::size_t table;std::string alias;std::size_t offset;};
    struct Item {std::string kind;syntax::Ref ref;std::string alias;std::size_t column=0;};
    struct Absence {std::size_t table=0,outer_key=0,inner_key=0;};
    using Predicate=relational::BoundPredicate;
    mutable std::uint64_t predicate_bindings_=0, predicate_tests_=0;
    struct Budget {std::size_t visits=0;void step(){if(++visits>1000000)throw std::runtime_error("query work budget exceeded");}};
    std::size_t row_limit_;
    foundation::Mode mode_=foundation::Mode::Overlay;
    std::vector<Table> tables_;
    std::vector<std::string> assertions_;
    std::unique_ptr<relational::SharedModel> model_;
    std::unique_ptr<sqlstorage::Store> store_;
    std::size_t encoded_state_size_=0;
    std::size_t pending_mutations_=0, committed_rows_=0, visible_rows_=0;
    bool in_tx_=false;
    std::uint64_t catalog_revision_=0;
    const std::set<std::string>* authorized_relations_=nullptr;
public:
    struct RelationMetadata { std::string name; std::vector<std::string> columns; bool derived=false; };
    struct QueryContext { std::uint64_t revision=0; std::vector<RelationMetadata> relations; };
private:
    static std::vector<Table> copy_tables(const std::vector<Table>& source){return source;}
    static sqlpersistence::Image catalog_image(const std::vector<Table>& tables,const std::vector<std::string>& assertions,
            const std::vector<foundation::Definition>& definitions,const std::vector<std::string>& required) {
        sqlpersistence::Image im;im.tables=tables;im.assertions=assertions;im.definitions=definitions;im.required=required;return im;
    }
    std::size_t encoded_size_for(const sqlpersistence::Image& catalog,const std::map<std::string,Bag>& added={})const {
        std::size_t total=sqlpersistence::encode_image(catalog).size();
        auto add=[&](const std::string&name,const Bag&bag){auto n=sqlpersistence::bag_size(name,bag);if(n>sqlstorage::Store::max_payload-total)throw std::length_error("encoded relational state exceeds 64 MiB");total+=n;};
        model_->with_committed([&](const auto& committed){for(const auto&x:committed)add(x.first,x.second);});
        for(const auto&x:added)add(x.first,x.second);
        if(total>sqlstorage::Store::max_payload)throw std::length_error("encoded relational state exceeds 64 MiB");
        return total;
    }
    void append_record(const sqlstorage::Bytes& record) {
        if(!store_)return;
        if(store_->needs_checkpoint(record.size()))throw std::length_error("WAL capacity requires explicit checkpoint");
        store_->append(record);
    }
    void recover_store() {
        sqlpersistence::Image image;
        if(!store_->snapshot().empty())image=sqlpersistence::decode_image(store_->snapshot());
        auto apply_delta=[&](const std::map<std::string,Bag>& changes){
            for(const auto&rel:changes){auto target=image.bags.find(rel.first);if(target==image.bags.end())throw std::invalid_argument("change references unknown relation");
                for(const auto&x:rel.second){if(target->second.find(x.first)==target->second.end()&&x.second<0)throw std::invalid_argument("negative recovered relation multiplicity");foundation::detail::change(target->second,x.first,x.second);auto p=target->second.find(x.first);if(p!=target->second.end()&&p->second<=0)throw std::invalid_argument("invalid recovered relation multiplicity");}
            }
        };
        for(const auto&record:store_->records()){
            if(record.size()<13)throw std::invalid_argument("truncated relational record");
            const std::uint8_t kind=record[12];
            if(kind==1)apply_delta(sqlpersistence::decode_delta(record));
            else if(kind==2){auto ddl=sqlpersistence::decode_ddl(record);auto&next=ddl.catalog;
                if(next.definitions.size()<image.definitions.size()||next.tables.size()<image.tables.size()||next.assertions.size()<image.assertions.size()||next.required.size()<image.required.size())throw std::invalid_argument("relational DDL catalog shrank");
                for(std::size_t i=0;i<image.definitions.size();++i)if(!sqlpersistence::equal_definition(image.definitions[i],next.definitions[i]))throw std::invalid_argument("relational DDL rewrote prior definition");
                for(std::size_t i=0;i<image.tables.size();++i)if(image.tables[i].name!=next.tables[i].name||image.tables[i].columns!=next.tables[i].columns||image.tables[i].derived!=next.tables[i].derived)throw std::invalid_argument("relational DDL rewrote prior table");
                for(std::size_t i=0;i<image.assertions.size();++i)if(image.assertions[i]!=next.assertions[i])throw std::invalid_argument("relational DDL rewrote prior assertion");
                for(std::size_t i=0;i<image.required.size();++i)if(image.required[i]!=next.required[i])throw std::invalid_argument("relational DDL rewrote prior constraint");
                next.bags=image.bags;
                for(const auto&x:ddl.added)if(image.bags.count(x.first)||!next.bags.emplace(x.first,x.second).second)throw std::invalid_argument("relational DDL duplicates relation state");
                if(next.bags.size()!=next.definitions.size())throw std::invalid_argument("relational DDL relation state mismatch "+std::to_string(next.bags.size())+"/"+std::to_string(next.definitions.size()));
                image.tables=std::move(next.tables);image.assertions=std::move(next.assertions);image.definitions=std::move(next.definitions);image.required=std::move(next.required);image.bags=std::move(next.bags);
            }else if(kind==3){
                auto evolution=sqlpersistence::decode_evolution(record);auto& next=evolution.catalog;
                if(next.tables.size()!=image.tables.size()||next.assertions!=image.assertions||next.required!=image.required)
                    throw std::invalid_argument("relational evolution rewrote table or assertion catalog");
                for(std::size_t i=0;i<image.tables.size();++i)
                    if(image.tables[i].name!=next.tables[i].name||image.tables[i].columns!=next.tables[i].columns||image.tables[i].derived!=next.tables[i].derived)
                        throw std::invalid_argument("relational evolution rewrote prior table");
                std::map<std::string,foundation::Definition> prior,updated;
                for(const auto& d:image.definitions)prior.emplace(d.name,d);
                for(const auto& d:next.definitions)updated.emplace(d.name,d);
                std::set<std::string> changed;
                for(const auto& d:image.definitions)if(d.op=="source"){
                    auto found=updated.find(d.name);
                    if(found==updated.end()||!sqlpersistence::equal_definition(d,found->second)||evolution.affected.count(d.name))
                        throw std::invalid_argument("relational evolution rewrote source definition");
                }
                for(const auto& name:evolution.removed){
                    auto found=prior.find(name);
                    if(!evolution.affected.count(name)||updated.count(name)||found==prior.end()||found->second.op=="source")
                        throw std::invalid_argument("invalid removed evolution definition");
                    changed.insert(name);
                }
                for(const auto& d:image.definitions){auto found=updated.find(d.name);if(found==updated.end()||!sqlpersistence::equal_definition(d,found->second)){
                    if(!evolution.affected.count(d.name))throw std::invalid_argument("relational evolution rewrote unaffected definition");
                    changed.insert(d.name);
                }}
                for(const auto& d:next.definitions)if(!prior.count(d.name)){
                    if(d.op=="source")throw std::invalid_argument("relational evolution added a source definition");
                    if(!evolution.affected.count(d.name))throw std::invalid_argument("relational evolution added unaffected definition");
                    changed.insert(d.name);
                }
                for(const auto& name:evolution.affected)
                    if(!prior.count(name)&&!updated.count(name))throw std::invalid_argument("evolution references unknown affected definition");
                auto depends=[](const foundation::Definition& d,const std::string& name){
                    return ((d.op=="map"||d.op=="filter"||d.op=="group")&&d.input==name)||
                        ((d.op=="join"||d.op=="anti"||d.op=="union")&&(d.left==name||d.right==name));
                };
                std::set<std::string> closure=changed;
                bool grew=true;
                while(grew){grew=false;
                    for(const auto& d:image.definitions)if(!closure.count(d.name))
                        for(const auto& dep:closure)if(depends(d,dep)){closure.insert(d.name);grew=true;break;}
                    for(const auto& d:next.definitions)if(!closure.count(d.name))
                        for(const auto& dep:closure)if(depends(d,dep)){closure.insert(d.name);grew=true;break;}
                }
                for(const auto& name:closure)if(!evolution.affected.count(name))
                    throw std::invalid_argument("evolution omitted dependent relation");
                for(const auto& name:evolution.affected)if(!evolution.removed.count(name)&&!updated.count(name))
                    throw std::invalid_argument("evolution affected relation has no definition");
                next.bags=image.bags;
                for(const auto& name:evolution.affected)next.bags.erase(name);
                for(const auto& name:evolution.removed)if(updated.count(name))throw std::invalid_argument("relational evolution retained removed definition");
                for(const auto& x:evolution.replaced){if(!updated.count(x.first)||!next.bags.emplace(x.first,x.second).second)throw std::invalid_argument("invalid evolved relation bag");}
                for(const auto& name:evolution.affected)if(updated.count(name)&&!evolution.replaced.count(name))throw std::invalid_argument("evolution omitted affected relation bag");
                if(next.bags.size()!=next.definitions.size())throw std::invalid_argument("relational evolution relation state mismatch");
                image.tables=std::move(next.tables);image.assertions=std::move(next.assertions);image.definitions=std::move(next.definitions);image.required=std::move(next.required);image.bags=std::move(next.bags);
            }else throw std::invalid_argument("unknown relational record type");
        }
        validate_image_catalog(image);
        model_=std::make_unique<relational::SharedModel>(image.definitions,image.required,std::move(image.bags),mode_);
        tables_=std::move(image.tables);assertions_=std::move(image.assertions);
        for(const auto&t:tables_)if(!t.derived){const auto&bag=model_->bag(t.name);for(const auto&x:bag)committed_rows_+=static_cast<std::size_t>(x.second);}
        if(committed_rows_>row_limit_)throw std::length_error("recovered source rows exceed catalog row budget");
        visible_rows_=committed_rows_;
        encoded_state_size_=encoded_size_for(catalog_image(tables_,assertions_,model_->definitions(),model_->required_empty()));
    }
    static void validate_image_catalog(const sqlpersistence::Image& image) {
        if(image.tables.size()>128||image.assertions.size()>128)throw std::length_error("recovered catalog exceeds limit");
        std::set<std::string> names,assertions;
        for(const auto&t:image.tables){if(!names.insert(t.name).second||t.columns.empty()||t.columns.size()>64)throw std::invalid_argument("invalid recovered table catalog");
            auto d=std::find_if(image.definitions.begin(),image.definitions.end(),[&](const auto&x){return x.name==t.name;});
            if(d==image.definitions.end()||(t.derived==(d->op=="source"))||((d->op=="source")!=( !t.derived))||
               (d->op=="source"&&d->width!=t.columns.size())||(d->op=="map"&&d->exprs.size()!=t.columns.size()))throw std::invalid_argument("recovered table definition mismatch");
        }
        for(const auto&a:image.assertions)if(!assertions.insert(a).second)throw std::invalid_argument("duplicate recovered assertion");
        if(image.required.size()!=image.assertions.size())throw std::invalid_argument("recovered assertion catalog mismatch");
    }
    std::size_t table(const std::string& name)const {
        if(authorized_relations_&&!authorized_relations_->count(name))
            throw std::invalid_argument("relation is not authorized");
        for(std::size_t i=0;i<tables_.size();++i)if(tables_[i].name==name)return i;
        if(authorized_relations_)throw std::invalid_argument("unknown relation");
        throw std::invalid_argument("unknown table: "+name);
    }
    template<class F> void scan(std::size_t n,F fn)const {model_->scan(tables_[n].name,model_->has_prepared(),fn);}
    std::size_t bind(const syntax::Ref& r,const std::vector<Source>& sources)const {
        std::optional<std::size_t> result;
        for(const auto& s:sources) {
            if(!r.qualifier.empty()&&s.alias!=r.qualifier)continue;
            const auto& cols=tables_[s.table].columns;
            for(std::size_t c=0;c<cols.size();++c)if(cols[c]==r.name){
                if(result)throw std::invalid_argument("ambiguous column: "+r.name);
                result=s.offset+c;
            }
        }
        if(!result)throw std::invalid_argument("unknown column: "+r.name);
        return *result;
    }
    std::vector<Predicate> predicates(syntax::Parser& p,const std::vector<Source>& sources)const {
        std::vector<Predicate> result;
        if(p.match("where"))do {
            auto column=bind(p.ref(),sources);auto op=p.take();
            if(op!="="&&op!="!="&&op!="<>"&&op!="<"&&op!="<="&&op!=">"&&op!=">=")throw std::invalid_argument("unsupported comparison");
            auto predicate=Predicate::bind(column,op,0);
            if(!p.peek().empty()&&syntax::alpha(p.peek()[0]))predicate.right_column=bind(p.ref(),sources);
            else predicate.value=p.value();
            result.push_back(predicate); ++predicate_bindings_;
        }while(p.match("and"));
        return result;
    }
    bool matches(const Row& row,const std::vector<Predicate>& where) const {
        for(const auto& w:where){++predicate_tests_;if(!w.matches(row))return false;}return true;
    }
    std::uint64_t statement_mutations_=0;
    template<class Changes> std::size_t persist_changes(const Changes& changes) {
        if(!store_)return encoded_state_size_;
        const auto payload=sqlpersistence::encode_delta_range(changes);
        __int128 next=encoded_state_size_;
        for(const auto&rel:changes){
            const auto&base=model_->bag(rel.first);
            for(const auto&x:rel.second){const auto old=base.find(x.first);const bool had=old!=base.end();
                const __int128 final=static_cast<__int128>(had?old->second:0)+x.second;
                if(final<0)throw std::logic_error("negative persisted candidate multiplicity");
                if(!had&&final>0)next+=static_cast<__int128>(12+8*x.first.size());
                else if(had&&final==0)next-=static_cast<__int128>(12+8*x.first.size());
            }
        }
        if(next<0||next>sqlstorage::Store::max_payload)throw std::length_error("encoded relational state exceeds 64 MiB");
        append_record(payload);return static_cast<std::size_t>(next);
    }
    void apply(std::vector<foundation::Mutation> mutations) {
        if(pending_mutations_+mutations.size()>10000)throw std::runtime_error("transaction mutation limit exceeded");
        I next_rows=static_cast<I>(visible_rows_);
        for(const auto& m:mutations) next_rows+=m.op=="insert"?1:m.op=="delete"?-1:0;
        if(next_rows<0 || static_cast<std::size_t>(next_rows)>row_limit_)throw std::runtime_error("global catalog row limit exceeded");
        if(in_tx_) { model_->append(mutations,false); pending_mutations_+=mutations.size(); }
        else if(store_) {
            model_->prepare(mutations,true);
            try { std::size_t next_size=encoded_state_size_;model_->commit_borrowed([&](const auto&changes){next_size=persist_changes(changes);});encoded_state_size_=next_size; }
            catch(...) { model_->rollback();throw; }
            committed_rows_=static_cast<std::size_t>(next_rows);
        } else { model_->apply(mutations); committed_rows_=static_cast<std::size_t>(next_rows); }
        visible_rows_=static_cast<std::size_t>(next_rows);
        statement_mutations_+=mutations.size();
    }
    Result select(syntax::Parser& p,bool explain,const std::string& view="",bool alter=false) {
        std::vector<Item> items;
        bool star=p.match("*");
        if(!star)do {
            Item item;
            if((p.peek()=="count"||p.peek()=="sum")&&p.peek(1)=="(") {
                item.kind=p.take();p.need("(");if(item.kind=="count")p.need("*");else item.ref=p.ref();p.need(")");
            }else {item.kind="column";item.ref=p.ref();}
            if(p.match("as"))item.alias=p.name();
            items.push_back(std::move(item));
        }while(p.match(","));
        p.need("from");auto name=p.name();std::vector<Source> sources{{table(name),name,0}};
        if(p.match("as"))sources[0].alias=p.name();
        bool joined=p.match("join");if(p.match("inner")){p.need("join");joined=true;}
        std::size_t left=0,right=0;
        if(joined) {
            name=p.name();std::size_t offset=tables_[sources[0].table].columns.size();sources.push_back({table(name),name,offset});
            if(p.match("as"))sources[1].alias=p.name();
            if(sources[0].alias==sources[1].alias)throw std::invalid_argument("duplicate table alias");
            p.need("on");left=bind(p.ref(),sources);p.need("=");right=bind(p.ref(),sources);
            if((left<offset)==(right<offset))throw std::invalid_argument("join must relate both inputs");
        }
        std::optional<Absence> absence;
        // Bounded correlated form: one inner source, SELECT * or SELECT 1, and
        // exactly one qualified cross-scope equality. Extra clauses fail below.
        if(p.peek()=="where"&&p.peek(1)=="not") {
            p.need("where");p.need("not");p.need("exists");p.need("(");p.need("select");
            if(!p.match("*"))p.need("1");
            p.need("from");auto inner_name=p.name();auto inner_table=table(inner_name);
            std::size_t inner_offset=tables_[sources[0].table].columns.size();
            std::vector<Source> scoped{sources[0],Source{inner_table,inner_name,inner_offset}};
            if(p.match("as"))scoped[1].alias=p.name();
            if(scoped[0].alias==scoped[1].alias)throw std::invalid_argument("duplicate table alias");
            p.need("where");auto first=p.ref();p.need("=");auto second=p.ref();
            if(first.qualifier.empty()||second.qualifier.empty())throw std::invalid_argument("correlated references must be qualified");
            auto first_column=bind(first,scoped),second_column=bind(second,scoped);
            if((first_column<inner_offset)==(second_column<inner_offset))throw std::invalid_argument("NOT EXISTS equality must correlate outer and inner sources");
            absence=first_column<inner_offset?Absence{inner_table,first_column,second_column-inner_offset}:
                Absence{inner_table,second_column,first_column-inner_offset};
            p.need(")");
            if(joined)throw std::invalid_argument("correlated NOT EXISTS requires one outer source");
        }
        if(star)for(const auto& s:sources)for(const auto& c:tables_[s.table].columns)items.push_back({"column",{s.alias,c},"",0});
        bool aggregate=false;
        Result result;
        for(auto& item:items) {
            if(item.kind!="count")item.column=bind(item.ref,sources);
            aggregate|=item.kind!="column";
            result.columns.push_back(item.alias.empty()?(item.kind=="column"?item.ref.name:item.kind=="count"?"count(*)":"sum("+(item.ref.qualifier.empty()?"":item.ref.qualifier+".")+item.ref.name+")"):item.alias);
        }
        auto where=absence?std::vector<Predicate>{}:predicates(p,sources);
        std::optional<std::size_t> group;
        if(p.match("group")){p.need("by");group=bind(p.ref(),sources);}
        if(aggregate||group)for(const auto& item:items)if(item.kind=="column"&&(!group||item.column!=*group))throw std::invalid_argument("nonaggregate projection must be grouping column");
        std::vector<std::pair<std::size_t,bool>> order;
        if(p.match("order")) {
            p.need("by");do {
                auto ref=p.ref();std::optional<std::size_t> column;
                for(std::size_t j=0;j<items.size();++j) {
                    bool match=ref.qualifier.empty()?result.columns[j]==ref.name:
                        items[j].kind=="column"&&items[j].ref.name==ref.name&&items[j].ref.qualifier==ref.qualifier;
                    if(match){if(column)throw std::invalid_argument("ambiguous ORDER BY column");column=j;}
                }
                if(!column)throw std::invalid_argument("ORDER BY must name a selected column or alias");
                bool descending=p.match("desc");if(!descending)p.match("asc");order.emplace_back(*column,descending);
            }while(p.match(","));
        }
        std::optional<std::size_t> limit;
        if(p.match("limit")){I n=p.value();if(n<0||n>100000)throw std::invalid_argument("LIMIT must be between 0 and 100000");limit=static_cast<std::size_t>(n);}
        p.end();
        if(absence&&(aggregate||group||!order.empty()||limit))throw std::invalid_argument("correlated NOT EXISTS supports projection only");
        result.plan="SCAN "+tables_[sources[0].table].name;
        if(joined)result.plan+=" NESTED_LOOP_JOIN "+tables_[sources[1].table].name;
        if(absence)result.plan+=" ANTI_JOIN "+tables_[absence->table].name;
        if(!where.empty())result.plan+=" FILTER";if(aggregate||group)result.plan+=" AGGREGATE";
        if(!order.empty())result.plan+=" SORT";if(limit)result.plan+=" LIMIT";
        if(!view.empty()) {
            if(in_tx_)throw std::invalid_argument("DDL inside a transaction is unsupported");
            std::size_t view_index=tables_.size();
            for(std::size_t i=0;i<tables_.size();++i)if(tables_[i].name==view){view_index=i;break;}
            if(alter) {
                if(view_index==tables_.size()||!tables_[view_index].derived)
                    throw std::invalid_argument("ALTER MATERIALIZED VIEW target must be an existing view");
                if(tables_[view_index].columns!=result.columns)
                    throw std::invalid_argument("ALTER MATERIALIZED VIEW must preserve output columns");
            } else {
                if(tables_.size()>=128)throw std::invalid_argument("relation limit exceeded");
                if(view_index!=tables_.size())throw std::invalid_argument("relation already exists");
                if(view.rfind("refpot_internal_",0)==0)throw std::invalid_argument("reserved internal relation prefix");
            }
            if(!order.empty()||limit)throw std::invalid_argument("unsupported maintained query clause");
            if(aggregate&&!group)throw std::invalid_argument("maintained aggregates require GROUP BY");
            if(items.size()>64)throw std::invalid_argument("view column limit exceeded");
            std::set<std::string> names;
            for(std::size_t i=0;i<items.size();++i) {
                if(items[i].kind!="column"&&items[i].alias.empty())throw std::invalid_argument("maintained aggregates require aliases");
                if(!names.insert(result.columns[i]).second)throw std::invalid_argument("duplicate view column");
            }
            std::vector<foundation::Definition> definitions;
            std::string input=tables_[sources[0].table].name;
            std::size_t internal_serial=0;
            auto add=[&](foundation::Definition d) {
                if(alter)d.name="refpot_internal_"+std::to_string(view_index)+"_evo_"+std::to_string(internal_serial++);
                else d.name="refpot_internal_"+std::to_string(tables_.size())+"_"+std::to_string(definitions.size());
                input=d.name;definitions.push_back(std::move(d));
            };
            if(joined) {
                const auto offset=sources[1].offset;
                if(left>=offset)std::swap(left,right);
                foundation::Definition d;d.op="join";d.left=input;d.right=tables_[sources[1].table].name;
                d.left_key=left;d.right_key=right-offset;add(std::move(d));
            }
            if(absence) {
                foundation::Definition d;d.op="anti";d.left=input;d.right=tables_[absence->table].name;
                d.left_key=absence->outer_key;d.right_key=absence->inner_key;add(std::move(d));
            }
            for(const auto& predicate:where) {
                static const char* comparisons[]={"eq","ne","lt","le","gt","ge"};
                foundation::Definition d;d.op="filter";d.input=input;d.column=predicate.column;
                d.cmp=comparisons[static_cast<std::size_t>(predicate.operation)];d.value=predicate.value;d.right_column=predicate.right_column;
                add(std::move(d));
            }
            if(group) {
                std::optional<std::size_t> sum_column;
                for(const auto& item:items)if(item.kind=="sum") {
                    if(sum_column&&*sum_column!=item.column)throw std::invalid_argument("only one maintained SUM input is supported");
                    sum_column=item.column;
                }
                foundation::Definition mapped;mapped.op="map";mapped.input=input;
                mapped.exprs={{"c"+std::to_string(*group)},{sum_column?"c"+std::to_string(*sum_column):"0"}};add(std::move(mapped));
                foundation::Definition grouped;grouped.op="group";grouped.input=input;grouped.key=0;grouped.value_column=1;add(std::move(grouped));
            }
            foundation::Definition projected;projected.name=view;projected.op="map";projected.input=input;
            for(const auto& item:items) projected.exprs.push_back({"c"+std::to_string(group?(item.kind=="column"?0:item.kind=="sum"?1:2):item.column)});
            definitions.push_back(std::move(projected));
            result.rows.clear();result.plan=alter?"ALTER MATERIALIZED VIEW "+view:"CREATE MATERIALIZED VIEW "+view;
            if(explain&&!alter)return result;
            Table added{view,result.columns,true};
            if(!alter) {
                tables_.reserve(tables_.size()+1);
                auto next_tables=tables_;next_tables.push_back(added);
                std::size_t next_size=encoded_state_size_;
                model_->add_definitions(definitions,[&](const auto&all_defs,const auto&,const auto&new_bags){
                    if(store_){auto catalog=catalog_image(next_tables,assertions_,all_defs,model_->required_empty());auto payload=sqlpersistence::encode_ddl(catalog,new_bags);next_size=encoded_size_for(catalog,new_bags);append_record(payload);}
                });
                tables_.push_back(std::move(added));encoded_state_size_=next_size;return result;
            }
            const auto old_definitions=model_->definitions();
            std::map<std::string,foundation::Definition> by_name;
            for(const auto& d:old_definitions)by_name.emplace(d.name,d);
            const auto public_def=by_name.find(view);
            if(public_def==by_name.end())throw std::logic_error("view definition missing from catalog");
            std::set<std::string> obsolete_internal;
            std::function<void(const std::string&)> collect_internal=[&](const std::string& name){
                auto found=by_name.find(name);if(found==by_name.end()||name.rfind("refpot_internal_",0)!=0||!obsolete_internal.insert(name).second)return;
                const auto& d=found->second;
                if(d.op=="map"||d.op=="filter"||d.op=="group")collect_internal(d.input);
                else if(d.op=="join"||d.op=="anti"||d.op=="union"){collect_internal(d.left);collect_internal(d.right);}
            };
            collect_internal(public_def->second.input);
            std::vector<foundation::Definition> candidate_defs;
            for(const auto& d:old_definitions)if(!obsolete_internal.count(d.name)&&d.name!=view)candidate_defs.push_back(d);
            candidate_defs.insert(candidate_defs.end(),definitions.begin(),definitions.end());
            std::map<std::string,std::size_t> positions;
            for(std::size_t i=0;i<candidate_defs.size();++i)
                if(!positions.emplace(candidate_defs[i].name,i).second)throw std::invalid_argument("duplicate internal definition");
            std::vector<unsigned char> marks(candidate_defs.size());std::vector<foundation::Definition> ordered;ordered.reserve(candidate_defs.size());
            std::function<void(std::size_t)> visit=[&](std::size_t i){
                if(marks[i]==1)throw std::invalid_argument("materialized view dependency cycle");
                if(marks[i]==2)return;marks[i]=1;const auto& d=candidate_defs[i];
                auto dep=[&](const std::string& name){auto p=positions.find(name);if(p==positions.end())throw std::invalid_argument("unknown materialized view dependency: "+name);visit(p->second);};
                if(d.op=="map"||d.op=="filter"||d.op=="group")dep(d.input);
                else if(d.op=="join"||d.op=="anti"||d.op=="union"){dep(d.left);dep(d.right);}
                marks[i]=2;ordered.push_back(d);
            };
            for(std::size_t i=0;i<candidate_defs.size();++i)visit(i);
            std::set<std::string> affected{view};
            for(const auto& d:definitions)affected.insert(d.name);
            bool grew=true;
            while(grew){grew=false;for(const auto& d:ordered){
                if(affected.count(d.name))continue;
                bool depends=(d.op=="map"||d.op=="filter"||d.op=="group")?affected.count(d.input)!=0:
                    (d.op=="join"||d.op=="anti"||d.op=="union")?(affected.count(d.left)!=0||affected.count(d.right)!=0):false;
                if(depends){affected.insert(d.name);grew=true;}
            }}
            for(const auto& name:obsolete_internal)affected.insert(name);
            foundation::Model checked(ordered,model_->required_empty(),mode_);
            (void)checked;
            if(explain)return result;
            auto next_model=model_->replace_definitions(ordered,affected);
            std::set<std::string> removed;
            for(const auto& name:obsolete_internal)if(!positions.count(name))removed.insert(name);
            std::map<std::string,Bag> replacements;
            for(const auto& name:affected)if(positions.count(name))replacements.emplace(name,next_model->bag(name));
            std::size_t next_size=encoded_state_size_;
            if(store_){
                auto catalog=catalog_image(tables_,assertions_,next_model->definitions(),next_model->required_empty());
                next_size=sqlpersistence::encoded_evolved_image_size(catalog,model_->committed_state(),replacements,removed);
                auto payload=sqlpersistence::encode_evolution(catalog,replacements,removed);
                append_record(payload);
            }
            next_model->publish_retained_from(*model_,affected);
            model_.swap(next_model);encoded_state_size_=next_size;return result;
        }
        if(explain)return result;
        Budget budget;
        struct Accumulator {I count=0;std::vector<relational::Aggregate> sums;};
        std::map<I,Accumulator> groups;
        std::set<I> excluded;
        if(absence)scan(absence->table,[&](const Row& row,I multiplicity) {
            budget.step();if(multiplicity<=0)throw std::logic_error("invalid relation multiplicity");
            excluded.insert(row[absence->inner_key]);return true;
        });
        if(aggregate&&!group)groups.emplace(0,Accumulator{0,std::vector<relational::Aggregate>(items.size())});
        auto emit=[&](const Row& row,I multiplicity) {
            if(absence&&excluded.count(row[absence->outer_key]))return;
            if(!matches(row,where))return;
            if(aggregate||group) {
                I key=group?row[*group]:0;
                auto it=groups.find(key);
                if(it==groups.end()){if(groups.size()>=100000)throw std::runtime_error("group limit exceeded");it=groups.emplace(key,Accumulator{0,std::vector<relational::Aggregate>(items.size())}).first;}
                it->second.count=foundation::detail::checked(static_cast<__int128>(it->second.count)+multiplicity);
                for(std::size_t j=0;j<items.size();++j)if(items[j].kind=="sum")it->second.sums[j].add(row[items[j].column],multiplicity);
            }else {
                if(multiplicity<0||static_cast<std::uint64_t>(multiplicity)>100000-result.rows.size())throw std::runtime_error("result limit exceeded");
                std::vector<std::optional<I>> projected;for(const auto& item:items)projected.push_back(row[item.column]);
                for(I n=0;n<multiplicity;++n){budget.step();result.rows.push_back(projected);}
            }
        };
        scan(sources[0].table,[&](const Row& a,I ac) {
            budget.step();if(ac<=0)throw std::logic_error("invalid relation multiplicity");
            if(joined)scan(sources[1].table,[&](const Row& b,I bc) {
                budget.step();if(bc<=0)throw std::logic_error("invalid relation multiplicity");
                Row row=a;row.insert(row.end(),b.begin(),b.end());if(row[left]==row[right])emit(row,foundation::detail::checked(static_cast<__int128>(ac)*bc));return true;
            });else emit(a,ac);
            return true;
        });
        for(const auto& [key,acc]:groups) {
            std::vector<std::optional<I>> row;
            for(std::size_t j=0;j<items.size();++j) {
                if(items[j].kind=="column")row.push_back(key);
                else if(items[j].kind=="count")row.push_back(acc.count);
                else row.push_back(acc.count?std::optional<I>(acc.sums[j].value()):std::nullopt);
            }
            result.rows.push_back(std::move(row));
        }
        if(!order.empty())std::stable_sort(result.rows.begin(),result.rows.end(),[&](const auto& a,const auto& b){
            for(const auto& [column,desc]:order)if(a[column]!=b[column])return desc?a[column]>b[column]:a[column]<b[column];return false;
        });
        if(limit&&result.rows.size()>*limit)result.rows.resize(*limit);
        return result;
    }
    void commit_model() {
        std::size_t next_size=encoded_state_size_;
        if(store_)model_->commit_borrowed([&](const auto&changes){next_size=persist_changes(changes);});
        else model_->commit();
        encoded_state_size_=next_size;
    }
    Result execute_impl(const std::string& query,const std::vector<I>& params,bool explain,bool& ddl) {
        syntax::Parser p(query,params);auto op=p.take();Result result;
        ddl=op=="create"||op=="alter";
        if(ddl&&!explain&&catalog_revision_==std::numeric_limits<std::uint64_t>::max())
            throw std::overflow_error("catalog revision exhausted");
        if(authorized_relations_&&op!="select")throw std::invalid_argument("read-only query requires SELECT");
        if(store_&&store_->poisoned()&&op!="rollback")throw std::runtime_error("database is poisoned");
        if(op=="select")return select(p,explain);
        if(op=="begin"||op=="commit"||op=="rollback") {
            p.end();result.plan=op;
            if(op=="begin"&&in_tx_)throw std::invalid_argument("nested transaction");
            if(op=="commit"&&!in_tx_)throw std::invalid_argument("no transaction");
            if(explain)return result;
            if(op=="begin")in_tx_=true;
            else if(op=="rollback")rollback();
            else {if(model_->has_prepared())commit_model();pending_mutations_=0;committed_rows_=visible_rows_;in_tx_=false;}
            return result;
        }
        if(op=="alter") {
            p.need("materialized");p.need("view");auto name=p.name();p.need("as");p.need("select");
            return select(p,explain,name,true);
        }
        if(op=="create") {
            if(p.match("assertion")) {
                auto name=p.name();p.need("check");p.need("(");p.need("not");p.need("exists");p.need("(");p.need("select");p.need("*");p.need("from");
                auto relation=p.name();table(relation);p.need(")");p.need(")");p.end();
                if(in_tx_)throw std::invalid_argument("DDL inside a transaction is unsupported");
                if(assertions_.size()>=128)throw std::invalid_argument("assertion limit exceeded");
                if(std::find(assertions_.begin(),assertions_.end(),name)!=assertions_.end())throw std::invalid_argument("assertion already exists");
                result.plan="CREATE ASSERTION "+name;if(explain)return result;
                assertions_.reserve(assertions_.size()+1);
                auto next_assertions=assertions_;next_assertions.push_back(name);
                std::size_t next_size=encoded_state_size_;
                model_->add_required_empty(relation,[&](const auto&required){
                    if(store_){auto catalog=catalog_image(tables_,next_assertions,model_->definitions(),required);auto payload=sqlpersistence::encode_ddl(catalog,{});next_size=encoded_size_for(catalog);append_record(payload);}
                });
                assertions_.swap(next_assertions);encoded_state_size_=next_size;return result;
            }
            if(p.match("materialized")) {p.need("view");auto name=p.name();p.need("as");p.need("select");return select(p,explain,name);}
            p.need("table");Table added;added.name=p.name();
            if(added.name.rfind("refpot_internal_",0)==0)throw std::invalid_argument("reserved internal relation prefix");p.need("(");
            do {
                auto col=p.name();p.need("integer");
                if(added.columns.empty()){p.need("primary");p.need("key");}
                else {p.need("not");p.need("null");}
                if(std::find(added.columns.begin(),added.columns.end(),col)!=added.columns.end())throw std::invalid_argument("duplicate column");
                added.columns.push_back(col);if(added.columns.size()>64)throw std::invalid_argument("column limit exceeded");
            }while(p.match(","));
            p.need(")");p.end();
            if(in_tx_)throw std::invalid_argument("DDL inside a transaction is unsupported");
            if(tables_.size()>=128)throw std::invalid_argument("table limit exceeded");
            for(const auto& t:tables_)if(t.name==added.name)throw std::invalid_argument("table already exists");
            result.plan="CREATE source catalog append";if(explain)return result;
            foundation::Definition d;d.name=added.name;d.op="source";d.width=added.columns.size();
            tables_.reserve(tables_.size()+1);
            auto next_tables=tables_;next_tables.push_back(added);
            std::size_t next_size=encoded_state_size_;
            model_->add_source(d,[&](const auto&definition){
                if(store_){auto definitions=model_->definitions();definitions.push_back(definition);std::map<std::string,Bag> new_bags;new_bags.emplace(definition.name,Bag{});
                    auto catalog=catalog_image(next_tables,assertions_,definitions,model_->required_empty());auto payload=sqlpersistence::encode_ddl(catalog,new_bags);next_size=encoded_size_for(catalog,new_bags);append_record(payload);}
            });
            tables_.push_back(std::move(added));encoded_state_size_=next_size;return result;
        }
        if(op=="insert") {
            p.need("into");auto n=table(p.name());if(tables_[n].derived)throw std::invalid_argument("derived relation is read-only");p.need("values");p.need("(");Row row;
            do {row.push_back(p.value());}while(p.match(","));p.need(")");p.end();
            if(row.size()!=tables_[n].columns.size())throw std::invalid_argument("INSERT row width mismatch");
            result.plan="INSERT source";if(explain)return result;
            result.affected=1;apply({{"insert",tables_[n].name,std::move(row),0}});return result;
        }
        if(op=="update"||op=="delete") {
            bool del=op=="delete";if(del)p.need("from");auto name=p.name();auto n=table(name);
            if(tables_[n].derived)throw std::invalid_argument("derived relation is read-only");
            std::vector<Source> sources{{n,name,0}};std::vector<std::pair<std::size_t,I>> assignments;
            if(!del){p.need("set");do {auto c=bind(p.ref(),sources);if(c==0)throw std::invalid_argument("primary key is immutable");p.need("=");I value=p.value();for(const auto& a:assignments)if(a.first==c)throw std::invalid_argument("duplicate assignment");assignments.emplace_back(c,value);}while(p.match(","));}
            auto where=predicates(p,sources);p.end();result.plan=del?"DELETE source scan":"UPDATE source scan";
            if(explain)return result;
            std::vector<foundation::Mutation> mutations;Budget budget;
            scan(n,[&](const Row& row,I){budget.step();if(matches(row,where)) {
                if(mutations.size()>=10000)throw std::runtime_error("mutation limit exceeded");
                foundation::Mutation m;m.op=del?"delete":"update";m.table=name;m.key=row[0];
                if(!del){m.row=row;for(const auto& [c,v]:assignments)m.row[c]=v;}
                mutations.push_back(std::move(m));
            }return true;});
            result.affected=mutations.size();apply(std::move(mutations));return result;
        }
        throw std::invalid_argument("unsupported SQL statement: "+op);
    }
public:
    explicit Database(foundation::Mode mode=foundation::Mode::Overlay,std::size_t row_limit=100000):row_limit_(row_limit),mode_(mode),model_(std::make_unique<relational::SharedModel>(std::vector<foundation::Definition>{},std::vector<std::string>{},mode)){
        if(!row_limit_||row_limit_>100000)throw std::invalid_argument("catalog row budget must be 1..100000");
    }
    explicit Database(const std::string& path,foundation::Mode mode=foundation::Mode::Overlay,std::size_t row_limit=100000)
      : row_limit_(row_limit),mode_(mode),model_(std::make_unique<relational::SharedModel>(std::vector<foundation::Definition>{},std::vector<std::string>{},mode)),store_(std::make_unique<sqlstorage::Store>(path)) {
        if(!row_limit_||row_limit_>100000)throw std::invalid_argument("catalog row budget must be 1..100000");
        recover_store();
    }
    void checkpoint() {
        if(in_tx_)throw std::logic_error("checkpoint is forbidden inside a transaction");
        if(!store_)return;
        if(store_->poisoned())throw std::runtime_error("database is poisoned");
        sqlpersistence::Image image=catalog_image(tables_,assertions_,model_->definitions(),model_->required_empty());
        sqlpersistence::Bytes payload;
        model_->with_committed([&](const auto& bags){payload=sqlpersistence::encode_image_range(image,bags);});
        if(payload.size()!=encoded_state_size_)throw std::logic_error("tracked encoded state size mismatch "+std::to_string(encoded_state_size_)+"/"+std::to_string(payload.size()));
        store_->checkpoint(payload);
    }
    bool poisoned()const noexcept{return store_&&store_->poisoned();}
    bool in_transaction()const noexcept{return in_tx_;}
    std::map<std::string,std::uint64_t> stats() const {
        return {{"statement_mutations",statement_mutations_},
                {"source_mutation_applications",model_->source_mutation_applications()},
                {"full_bag_copied_entries",model_->materialized_entries()},
                {"predicate_bindings",predicate_bindings_},{"predicate_tests",predicate_tests_},
                {"maintenance_steps",model_->maintenance_steps()},
                {"prior_mutation_replays",0},{"catalog_copied_rows",0},{"candidate_copied_entries",0}};
    }
    void rollback()noexcept{model_->rollback();pending_mutations_=0;visible_rows_=committed_rows_;in_tx_=false;}
    Result execute(const std::string& query,const std::vector<I>& params={},bool explain=false) {
        try {
            bool ddl=false;
            auto result=execute_impl(query,params,explain,ddl);
            if(!explain&&ddl)++catalog_revision_;
            return result;
        } catch(...) {if(in_tx_&&!explain)rollback();throw;}
    }
    QueryContext query_context(const std::vector<std::string>& requested) const {
        if(store_&&store_->poisoned())throw std::runtime_error("database is poisoned");
        if(in_tx_)throw std::logic_error("catalog context is forbidden inside a transaction");
        QueryContext context;context.revision=catalog_revision_;
        if(requested.size()>128)throw std::length_error("too many authorized relations");
        std::set<std::string> seen;
        for(const auto& name:requested) {
            if(name.size()>64)throw std::length_error("relation name exceeds 64 bytes");
            if(!seen.insert(name).second)throw std::invalid_argument("duplicate authorized relation");
            auto found=std::find_if(tables_.begin(),tables_.end(),[&](const auto& t){return t.name==name;});
            if(found==tables_.end())throw std::invalid_argument("unknown authorized relation");
            context.relations.push_back({found->name,found->columns,found->derived});
        }
        return context;
    }
    Result execute_readonly(const std::string& query,const std::vector<I>& params,
                            const std::vector<std::string>& requested,std::uint64_t revision,bool explain=false) {
        if(in_tx_)throw std::logic_error("read-only query is forbidden inside a transaction");
        if(revision!=catalog_revision_)throw std::invalid_argument("stale catalog context");
        if(requested.size()>128)throw std::length_error("too many authorized relations");
        std::set<std::string> allowed;
        for(const auto& name:requested) {
            if(name.size()>64)throw std::length_error("relation name exceeds 64 bytes");
            if(!allowed.insert(name).second)throw std::invalid_argument("duplicate authorized relation");
        }
        struct Authorization { const std::set<std::string>*& slot; const std::set<std::string>* prior; ~Authorization(){slot=prior;} };
        Authorization guard{authorized_relations_,authorized_relations_};authorized_relations_=&allowed;
        return execute(query,params,explain);
    }
};
}
