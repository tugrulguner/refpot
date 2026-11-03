#pragma once
#include "../shared-change/native.hpp"
#include <charconv>
#include <optional>
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
    struct Table {std::string name;std::vector<std::string> columns;};
    struct Source {std::size_t table;std::string alias;std::size_t offset;};
    struct Item {std::string kind;syntax::Ref ref;std::string alias;std::size_t column=0;};
    struct Predicate {std::size_t column;std::string op;I value;};
    struct Budget {std::size_t visits=0;void step(){if(++visits>1000000)throw std::runtime_error("query work budget exceeded");}};
    foundation::Mode mode_;
    std::size_t row_limit_;
    std::vector<Table> tables_;
    std::unique_ptr<foundation::Model> model_;
    std::vector<foundation::Mutation> pending_;
    bool in_tx_=false;
    std::size_t table(const std::string& name)const {
        for(std::size_t i=0;i<tables_.size();++i)if(tables_[i].name==name)return i;
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
    static bool compare(I a,const std::string& op,I b) {
        if(op=="=")return a==b;if(op=="!="||op=="<>")return a!=b;
        if(op=="<")return a<b;if(op=="<=")return a<=b;if(op==">")return a>b;return a>=b;
    }
    std::vector<Predicate> predicates(syntax::Parser& p,const std::vector<Source>& sources)const {
        std::vector<Predicate> result;
        if(p.match("where"))do {
            auto column=bind(p.ref(),sources);auto op=p.take();
            if(op!="="&&op!="!="&&op!="<>"&&op!="<"&&op!="<="&&op!=">"&&op!=">=")throw std::invalid_argument("unsupported comparison");
            result.push_back({column,op,p.value()});
        }while(p.match("and"));
        return result;
    }
    static bool matches(const Row& row,const std::vector<Predicate>& where) {
        for(const auto& w:where)if(!compare(row[w.column],w.op,w.value))return false;return true;
    }
    void apply(std::vector<foundation::Mutation> mutations) {
        auto all=in_tx_?pending_:std::vector<foundation::Mutation>{};
        if(all.size()+mutations.size()>10000)throw std::runtime_error("transaction mutation limit exceeded");
        all.insert(all.end(),std::make_move_iterator(mutations.begin()),std::make_move_iterator(mutations.end()));
        if(in_tx_) {model_->rollback();model_->prepare(all);pending_.swap(all);}
        else model_->apply(all);
    }
    Result select(syntax::Parser& p,bool explain) {
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
        if(star)for(const auto& s:sources)for(const auto& c:tables_[s.table].columns)items.push_back({"column",{s.alias,c},"",0});
        bool aggregate=false;
        Result result;
        for(auto& item:items) {
            if(item.kind!="count")item.column=bind(item.ref,sources);
            aggregate|=item.kind!="column";
            result.columns.push_back(item.alias.empty()?(item.kind=="column"?item.ref.name:item.kind=="count"?"count(*)":"sum("+(item.ref.qualifier.empty()?"":item.ref.qualifier+".")+item.ref.name+")"):item.alias);
        }
        auto where=predicates(p,sources);
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
        result.plan="SCAN "+tables_[sources[0].table].name;
        if(joined)result.plan+=" NESTED_LOOP_JOIN "+tables_[sources[1].table].name;
        if(!where.empty())result.plan+=" FILTER";if(aggregate||group)result.plan+=" AGGREGATE";
        if(!order.empty())result.plan+=" SORT";if(limit)result.plan+=" LIMIT";
        if(explain)return result;
        Budget budget;
        struct Accumulator {I count=0;std::vector<__int128> sums;};
        std::map<I,Accumulator> groups;
        if(aggregate&&!group)groups.emplace(0,Accumulator{0,std::vector<__int128>(items.size())});
        auto emit=[&](const Row& row) {
            if(!matches(row,where))return;
            if(aggregate||group) {
                I key=group?row[*group]:0;
                auto it=groups.find(key);
                if(it==groups.end()){if(groups.size()>=100000)throw std::runtime_error("group limit exceeded");it=groups.emplace(key,Accumulator{0,std::vector<__int128>(items.size())}).first;}
                ++it->second.count;
                for(std::size_t j=0;j<items.size();++j)if(items[j].kind=="sum")it->second.sums[j]+=row[items[j].column];
            }else {
                if(result.rows.size()>=100000)throw std::runtime_error("result limit exceeded");
                std::vector<std::optional<I>> projected;for(const auto& item:items)projected.push_back(row[item.column]);result.rows.push_back(std::move(projected));
            }
        };
        scan(sources[0].table,[&](const Row& a,I ac) {
            budget.step();if(ac!=1)throw std::logic_error("invalid source multiplicity");
            if(joined)scan(sources[1].table,[&](const Row& b,I bc) {
                budget.step();if(bc!=1)throw std::logic_error("invalid source multiplicity");
                Row row=a;row.insert(row.end(),b.begin(),b.end());if(row[left]==row[right])emit(row);return true;
            });else emit(a);
            return true;
        });
        for(const auto& [key,acc]:groups) {
            std::vector<std::optional<I>> row;
            for(std::size_t j=0;j<items.size();++j) {
                if(items[j].kind=="column")row.push_back(key);
                else if(items[j].kind=="count")row.push_back(acc.count);
                else row.push_back(acc.count?std::optional<I>(foundation::detail::checked(acc.sums[j])):std::nullopt);
            }
            result.rows.push_back(std::move(row));
        }
        if(!order.empty())std::stable_sort(result.rows.begin(),result.rows.end(),[&](const auto& a,const auto& b){
            for(const auto& [column,desc]:order)if(a[column]!=b[column])return desc?a[column]>b[column]:a[column]<b[column];return false;
        });
        if(limit&&result.rows.size()>*limit)result.rows.resize(*limit);
        return result;
    }
    Result execute_impl(const std::string& query,const std::vector<I>& params,bool explain) {
        syntax::Parser p(query,params);auto op=p.take();Result result;
        if(op=="select")return select(p,explain);
        if(op=="begin"||op=="commit"||op=="rollback") {
            p.end();result.plan=op;
            if(op=="begin"&&in_tx_)throw std::invalid_argument("nested transaction");
            if(op=="commit"&&!in_tx_)throw std::invalid_argument("no transaction");
            if(explain)return result;
            if(op=="begin")in_tx_=true;
            else if(op=="rollback")rollback();
            else {if(model_->has_prepared())model_->commit();pending_.clear();in_tx_=false;}
            return result;
        }
        if(op=="create") {
            p.need("table");Table added;added.name=p.name();p.need("(");
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
            result.plan="CREATE source catalog (rebuild)";if(explain)return result;
            auto tables=tables_;tables.push_back(std::move(added));
            std::vector<foundation::Definition> definitions;
            for(const auto& t:tables){foundation::Definition d;d.name=t.name;d.op="source";d.width=t.columns.size();definitions.push_back(std::move(d));}
            auto model=std::make_unique<foundation::Model>(definitions,std::vector<std::string>{},mode_);
            std::vector<foundation::Mutation> restore;
            for(const auto& t:tables_)model_->scan(t.name,false,[&](const Row& row,I){if(restore.size()>=row_limit_)throw std::runtime_error("catalog rebuild row budget exceeded");restore.push_back({"insert",t.name,row,0});return true;});
            model->apply(restore);model_.swap(model);tables_.swap(tables);return result;
        }
        if(op=="insert") {
            p.need("into");auto n=table(p.name());p.need("values");p.need("(");Row row;
            do {row.push_back(p.value());}while(p.match(","));p.need(")");p.end();
            if(row.size()!=tables_[n].columns.size())throw std::invalid_argument("INSERT row width mismatch");
            result.plan="INSERT source";if(explain)return result;
            std::size_t count=0;
            for(std::size_t source=0;source<tables_.size();++source){
                scan(source,[&](const Row&,I){++count;return count<row_limit_;});
                if(count>=row_limit_)throw std::runtime_error("global catalog row limit exceeded");
            }
            result.affected=1;apply({{"insert",tables_[n].name,std::move(row),0}});return result;
        }
        if(op=="update"||op=="delete") {
            bool del=op=="delete";if(del)p.need("from");auto name=p.name();auto n=table(name);
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
    explicit Database(foundation::Mode mode=foundation::Mode::Overlay,std::size_t row_limit=100000):mode_(mode),row_limit_(row_limit),model_(std::make_unique<foundation::Model>(std::vector<foundation::Definition>{},std::vector<std::string>{},mode)){
        if(!row_limit_||row_limit_>100000)throw std::invalid_argument("catalog row budget must be 1..100000");
    }
    bool in_transaction()const noexcept{return in_tx_;}
    void rollback()noexcept{model_->rollback();pending_.clear();in_tx_=false;}
    Result execute(const std::string& query,const std::vector<I>& params={},bool explain=false) {
        try{return execute_impl(query,params,explain);}catch(...){if(in_tx_&&!explain)rollback();throw;}
    }
};
}
