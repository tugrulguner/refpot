#pragma once

#include <algorithm>
#include <cstdint>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace refpot::model {
using I = std::int64_t;
using Row = std::vector<I>;
using Bag = std::map<Row,I>;
struct Definition {
    std::string name,op,input,left,right;
    std::size_t width=0;
    std::vector<std::vector<std::string>> exprs;
    std::size_t column=0;
    std::string cmp;
    I value=0;
    std::size_t left_key=0,right_key=0,key=0,value_column=0;
};
struct Mutation { std::string op,table; Row row; I key=0; };
struct Stats { std::uint64_t source_delta_rows=0,derived_nodes=0,rows_visited=0,copied_rows=0; };

namespace detail {
inline I checked(__int128 v) {
    if (v < std::numeric_limits<I>::min() || v > std::numeric_limits<I>::max())
        throw std::overflow_error("signed 64-bit arithmetic overflow");
    return static_cast<I>(v);
}
inline void change(Bag& b, const Row& r, I d) {
    if (!d) return;
    auto it=b.find(r); I old=it==b.end()?0:it->second;
    I now=checked(static_cast<__int128>(old)+d);
    if (!now) { if(it!=b.end()) b.erase(it); }
    else if(it==b.end()) b.emplace(r,now); else it->second=now;
}
inline void add(Bag& b, const Row& r, I d) {
    if (!d) return;
    auto it=b.find(r); I old=it==b.end()?0:it->second;
    I now=checked(static_cast<__int128>(old)+d);
    if (now<0) throw std::logic_error("negative bag multiplicity");
    if (!now) { if(it!=b.end()) b.erase(it); }
    else if(it==b.end()) b.emplace(r,now); else it->second=now;
}
inline I count_product(I a,I b) { return checked(static_cast<__int128>(a)*b); }
inline bool digits(const std::string& s,std::size_t start) {
    if(start>=s.size()) return false;
    for(std::size_t i=start;i<s.size();++i) if(s[i]<'0'||s[i]>'9') return false;
    return true;
}
inline bool integer_token(const std::string& s) {
    std::size_t start=(!s.empty()&&s[0]=='-')?1:0;
    return digits(s,start);
}
inline std::size_t expr_width(const std::vector<std::string>& e, std::size_t input_width) {
    if(e.empty()) throw std::invalid_argument("empty expression");
    std::size_t depth=0;
    for(const auto& t:e) {
        if(t=="+"||t=="-"||t=="*") { if(depth<2) throw std::invalid_argument("malformed postfix expression"); --depth; }
        else if(t.size()>1 && t[0]=='c' && digits(t,1)) {
            std::size_t n=0; try { n=std::stoull(t.substr(1)); }
            catch(...) { throw std::invalid_argument("bad column reference"); }
            if(n>=input_width) throw std::invalid_argument("column outside input width"); ++depth;
        } else {
            if(!integer_token(t)) throw std::invalid_argument("invalid expression token");
            try { (void)std::stoll(t); }
            catch(...) { throw std::invalid_argument("integer literal outside signed 64-bit range"); }
            ++depth;
        }
    }
    if(depth!=1) throw std::invalid_argument("expression must leave one value");
    return 1;
}
inline I eval(const std::vector<std::string>& e,const Row& row) {
    std::vector<I> stack; stack.reserve(e.size());
    for(const auto& t:e) {
        if(t=="+"||t=="-"||t=="*") {
            I b=stack.back(); stack.pop_back(); I a=stack.back(); stack.pop_back();
            stack.push_back(checked(t=="+"?static_cast<__int128>(a)+b:t=="-"?static_cast<__int128>(a)-b:static_cast<__int128>(a)*b));
        } else if(t.size()>1 && t[0]=='c') stack.push_back(row.at(static_cast<std::size_t>(std::stoull(t.substr(1)))));
        else stack.push_back(static_cast<I>(std::stoll(t)));
    }
    return stack[0];
}
inline bool cmp(I a,const std::string& c,I b) {
    if(c=="lt") return a<b; if(c=="le") return a<=b; if(c=="eq") return a==b;
    if(c=="ne") return a!=b; if(c=="ge") return a>=b; if(c=="gt") return a>b;
    throw std::invalid_argument("unknown comparison");
}
}

class Model {
    std::vector<Definition> defs_;
    std::map<std::string,std::size_t> index_;
    std::map<std::string,std::size_t> widths_;
    std::vector<std::string> required_;
    std::map<std::string,Bag> bags_;
    std::uint64_t epoch_=0;
    Stats stats_{};

    static void valid_name(const std::string& n) {
        if(n.empty()||n[0]<'a'||n[0]>'z') throw std::invalid_argument("invalid relation name");
        for(char c:n) if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_')) throw std::invalid_argument("invalid relation name");
    }
    std::size_t parent(const std::string& n) const {
        auto i=widths_.find(n); if(i==widths_.end()) throw std::invalid_argument("parent must precede definition"); return i->second;
    }
    static void column(std::size_t c,std::size_t w) { if(c>=w) throw std::invalid_argument("column outside relation width"); }
    static Bag combine(const Bag& a,const Bag& b) {
        Bag out=a; for(const auto& x:b) detail::add(out,x.first,x.second); return out;
    }
    void derive(std::size_t di, const std::map<std::string,Bag>& old,
                std::map<std::string,Bag>& now, std::map<std::string,Bag>& deltas,
                Stats& st) const {
        const auto& d=defs_[di]; Bag delta;
        auto get=[&](const std::string& n)->const Bag& { return now.at(n); };
        auto oldbag=[&](const std::string& n)->const Bag& { return old.at(n); };
        auto dd=[&](const std::string& n)->const Bag& { return deltas.at(n); };
        bool touched=false;
        if(d.op=="join"||d.op=="anti") touched=!dd(d.left).empty()||!dd(d.right).empty();
        else if(d.op=="union") touched=!dd(d.left).empty()||!dd(d.right).empty();
        else touched=!dd(d.input).empty();
        if(!touched) return;
        if(d.op=="map") {
            for(const auto& x:dd(d.input)) { ++st.rows_visited; Row r; r.reserve(d.exprs.size()); for(const auto& e:d.exprs) r.push_back(detail::eval(e,x.first)); detail::change(delta,r,x.second); }
        } else if(d.op=="filter") {
            for(const auto& x:dd(d.input)) { ++st.rows_visited; if(detail::cmp(x.first[d.column],d.cmp,d.value)) detail::change(delta,x.first,x.second); }
        } else if(d.op=="union") {
            delta=dd(d.left); st.copied_rows+=delta.size();
            for(const auto& x:dd(d.right)) { ++st.rows_visited; detail::change(delta,x.first,x.second); }
        } else if(d.op=="join") {
            const Bag& dl=dd(d.left); const Bag& dr=dd(d.right);
            std::map<Row,__int128> wide;
            auto join_into=[&](const Bag& l,const Bag& r) {
                for(const auto& a:l) for(const auto& b:r) {
                    ++st.rows_visited;
                    if(a.first[d.left_key]==b.first[d.right_key]) {
                        Row row=a.first; row.insert(row.end(),b.first.begin(),b.first.end());
                        wide[row]+=static_cast<__int128>(a.second)*b.second;
                    }
                }
            };
            // Include the cross term once. Wide intermediate deltas may cancel even
            // when each complete old/new materialization fits signed 64-bit counts.
            join_into(dl,oldbag(d.right)); join_into(get(d.left),dr);
            for(const auto& x:wide) detail::change(delta,x.first,detail::checked(x.second));
        } else if(d.op=="group") {
            std::map<I,bool> touched;
            for(const auto& x:dd(d.input)) { ++st.rows_visited; touched[x.first[d.key]]=true; }
            for(const auto& key:touched) {
                for(const auto& x:oldbag(d.name)) { ++st.rows_visited; if(x.first[0]==key.first) detail::change(delta,x.first,-x.second); }
                __int128 sum=0; __int128 count=0;
                for(const auto& x:get(d.input)) {
                    ++st.rows_visited;
                    if(x.first[d.key]==key.first) {
                        count+=x.second; (void)detail::checked(count);
                        sum+=static_cast<__int128>(x.first[d.value_column])*x.second;
                    }
                }
                if(count) { Row r{key.first,detail::checked(sum),detail::checked(count)}; detail::change(delta,r,1); }
            }
        } else if(d.op=="anti") {
            std::map<I,bool> affected;
            for(const auto& x:dd(d.left)) { ++st.rows_visited; affected[x.first[d.left_key]]=true; }
            for(const auto& x:dd(d.right)) { ++st.rows_visited; affected[x.first[d.right_key]]=true; }
            for(const auto& key:affected) {
                for(const auto& x:oldbag(d.name)) { ++st.rows_visited; if(x.first[d.left_key]==key.first) detail::change(delta,x.first,-x.second); }
                bool present=false; for(const auto& x:get(d.right)) { ++st.rows_visited; if(x.first[d.right_key]==key.first) { present=true; break; } }
                if(!present) for(const auto& x:get(d.left)) { ++st.rows_visited; if(x.first[d.left_key]==key.first) detail::change(delta,x.first,x.second); }
            }
        }
        st.copied_rows+=oldbag(d.name).size();
        now[d.name]=combine(oldbag(d.name),delta);
        deltas[d.name]=std::move(delta);
        ++st.derived_nodes;
    }
public:
    explicit Model(std::vector<Definition> defs,std::vector<std::string> required_empty)
      : defs_(std::move(defs)),required_(std::move(required_empty)) {
        for(std::size_t i=0;i<defs_.size();++i) {
            const auto& d=defs_[i]; valid_name(d.name);
            if(index_.count(d.name)) throw std::invalid_argument("duplicate relation");
            std::size_t w=0;
            if(d.op=="source") { if(!d.width) throw std::invalid_argument("source width must be positive"); w=d.width; }
            else if(d.op=="map") { auto in=parent(d.input); if(d.exprs.empty()) throw std::invalid_argument("map requires expressions"); for(const auto& e:d.exprs) detail::expr_width(e,in); w=d.exprs.size(); }
            else if(d.op=="filter") { auto in=parent(d.input); column(d.column,in); detail::cmp(0,d.cmp,0); w=in; }
            else if(d.op=="join"||d.op=="anti") { auto l=parent(d.left),r=parent(d.right); column(d.left_key,l); column(d.right_key,r); w=d.op=="join"?l+r:l; }
            else if(d.op=="union") { auto l=parent(d.left),r=parent(d.right); if(l!=r) throw std::invalid_argument("union widths differ"); w=l; }
            else if(d.op=="group") { auto in=parent(d.input); column(d.key,in); column(d.value_column,in); w=3; }
            else throw std::invalid_argument("unknown relation operator");
            index_[d.name]=i; widths_[d.name]=w; bags_[d.name]=Bag{};
        }
        for(const auto& n:required_) { valid_name(n); if(!index_.count(n)) throw std::invalid_argument("unknown required-empty relation"); }
    }
    void apply(const std::vector<Mutation>& mutations) {
        if(epoch_==std::numeric_limits<std::uint64_t>::max()) throw std::overflow_error("epoch exhausted");
        auto candidate=bags_; Stats next{}; std::map<std::string,Bag> deltas;
        for(const auto& x:bags_) next.copied_rows+=x.second.size();
        for(const auto& d:defs_) deltas[d.name]=Bag{};
        for(const auto& m:mutations) {
            auto it=index_.find(m.table); if(it==index_.end()) throw std::invalid_argument("unknown mutation table");
            const auto& d=defs_[it->second]; if(d.op!="source") throw std::invalid_argument("derived relation is read-only");
            Bag& b=candidate.at(m.table);
            if(m.op=="insert"||m.op=="update") {
                if(m.row.size()!=d.width) throw std::invalid_argument("source row width mismatch");
                I key=m.row[0]; auto rowit=b.lower_bound(Row{key});
                // A one-cell key sorts before all complete rows with that primary key.
                if(rowit!=b.end() && rowit->first[0]!=key) rowit=b.end();
                if(m.op=="insert" && rowit!=b.end()) throw std::invalid_argument("duplicate source primary key");
                if(m.op=="update" && rowit==b.end()) throw std::invalid_argument("missing source primary key");
                if(rowit!=b.end()) { detail::change(deltas[m.table],rowit->first,-1); b.erase(rowit); }
                b.emplace(m.row,1); detail::change(deltas[m.table],m.row,1);
            } else if(m.op=="delete") {
                auto rowit=b.lower_bound(Row{m.key});
                if(rowit!=b.end() && rowit->first[0]!=m.key) rowit=b.end();
                if(rowit==b.end()) throw std::invalid_argument("missing source primary key");
                detail::change(deltas[m.table],rowit->first,-1); b.erase(rowit);
            } else throw std::invalid_argument("unknown mutation operation");
        }
        std::uint64_t source_rows=0;
        for(const auto& d:defs_) if(d.op=="source") {
            auto n=static_cast<std::uint64_t>(deltas.at(d.name).size());
            if(n>std::numeric_limits<std::uint64_t>::max()-source_rows) throw std::overflow_error("source delta count overflow");
            source_rows+=n;
        }
        if(source_rows>std::numeric_limits<std::uint64_t>::max()-next.source_delta_rows) throw std::overflow_error("source delta stats overflow");
        next.source_delta_rows+=source_rows;
        for(std::size_t i=0;i<defs_.size();++i) if(defs_[i].op!="source") derive(i,bags_,candidate,deltas,next);
        for(const auto& n:required_) if(!candidate.at(n).empty()) throw std::logic_error("required-empty relation is nonempty");
        bags_.swap(candidate); stats_=next; ++epoch_;
    }
    const Bag& bag(const std::string& name) const { auto i=bags_.find(name); if(i==bags_.end()) throw std::out_of_range("unknown relation"); return i->second; }
    std::map<std::string,Bag> snapshot() const { return bags_; }
    std::uint64_t epoch() const { return epoch_; }
    Stats stats() const { return stats_; }
};
}
