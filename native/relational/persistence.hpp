#pragma once

#include "storage.hpp"
#include "foundation.hpp"
#include <cstring>
#include <map>
#include <set>
#include <string>
#include <utility>
#include <vector>

namespace refpot::sqlpersistence {
using Bytes = sqlstorage::Bytes;
using Definition = foundation::Definition;
using Bag = foundation::Bag;
using Row = foundation::Row;
using I = foundation::I;

struct Table {
    std::string name;
    std::vector<std::string> columns;
    bool derived=false;
};
struct Image {
    std::vector<Table> tables;
    std::vector<std::string> assertions;
    std::vector<Definition> definitions;
    std::vector<std::string> required;
    std::map<std::string,Bag> bags;
};
struct Ddl {
    Image catalog;
    std::map<std::string,Bag> added;
};

class Writer {
    Bytes bytes_;
    void room(std::size_t n) {
        if(n>sqlstorage::Store::max_payload-bytes_.size())throw std::length_error("encoded relational state exceeds 64 MiB");
    }
public:
    void u8(std::uint8_t n){room(1);bytes_.push_back(n);}
    void u32(std::uint32_t n){room(4);for(unsigned i=0;i<4;++i)bytes_.push_back(static_cast<unsigned char>(n>>(8U*i)));}
    void u64(std::uint64_t n){room(8);for(unsigned i=0;i<8;++i)bytes_.push_back(static_cast<unsigned char>(n>>(8U*i)));}
    void i64(I n){u64(static_cast<std::uint64_t>(n));}
    void str(const std::string& s){if(s.size()>65536)throw std::length_error("encoded string exceeds limit");u32(static_cast<std::uint32_t>(s.size()));room(s.size());bytes_.insert(bytes_.end(),s.begin(),s.end());}
    void magic(const char* s){room(8);bytes_.insert(bytes_.end(),s,s+8);}
    Bytes finish(){return std::move(bytes_);}
};
class Reader {
    const Bytes& b_;std::size_t at_=0;
    void need(std::size_t n)const{if(n>b_.size()-at_)throw std::invalid_argument("truncated relational persistence record");}
public:
    explicit Reader(const Bytes& b):b_(b){if(b.size()>sqlstorage::Store::max_payload)throw std::length_error("relational persistence payload exceeds limit");}
    std::uint8_t u8(){need(1);return b_[at_++];}
    std::uint32_t u32(){need(4);std::uint32_t x=0;for(unsigned i=0;i<4;++i)x|=std::uint32_t(b_[at_++])<<(8U*i);return x;}
    std::uint64_t u64(){need(8);std::uint64_t x=0;for(unsigned i=0;i<8;++i)x|=std::uint64_t(b_[at_++])<<(8U*i);return x;}
    I i64(){return static_cast<I>(u64());}
    std::string str(){auto n=u32();if(n>65536)throw std::length_error("relational string exceeds limit");need(n);std::string s(reinterpret_cast<const char*>(b_.data()+at_),n);at_+=n;return s;}
    void magic(const char* s){need(8);if(std::memcmp(b_.data()+at_,s,8))throw std::invalid_argument("unknown relational persistence format");at_+=8;}
    void end()const{if(at_!=b_.size())throw std::invalid_argument("trailing relational persistence bytes");}
};

inline void put_strings(Writer& w,const std::vector<std::string>& v){if(v.size()>1024)throw std::length_error("catalog string count exceeds limit");w.u32(static_cast<std::uint32_t>(v.size()));for(const auto&s:v)w.str(s);}
inline std::vector<std::string> get_strings(Reader&r,std::size_t max=1024){auto n=r.u32();if(n>max)throw std::length_error("catalog string count exceeds limit");std::vector<std::string> v;v.reserve(n);for(std::uint32_t i=0;i<n;++i)v.push_back(r.str());return v;}
inline void put_definition(Writer&w,const Definition&d){
    w.str(d.name);w.str(d.op);w.str(d.input);w.str(d.left);w.str(d.right);w.u64(d.width);
    if(d.exprs.size()>64)throw std::length_error("definition expression count exceeds limit");w.u32(static_cast<std::uint32_t>(d.exprs.size()));
    for(const auto&e:d.exprs)put_strings(w,e);
    w.u64(d.column);w.str(d.cmp);w.i64(d.value);w.u64(d.left_key);w.u64(d.right_key);w.u64(d.key);w.u64(d.value_column);w.u8(d.right_column?1:0);if(d.right_column)w.u64(*d.right_column);
}
inline std::size_t get_size(Reader&r){auto n=r.u64();if(n>1000000)throw std::length_error("catalog index exceeds limit");return static_cast<std::size_t>(n);}
inline Definition get_definition(Reader&r){
    Definition d;d.name=r.str();d.op=r.str();d.input=r.str();d.left=r.str();d.right=r.str();d.width=get_size(r);
    auto n=r.u32();if(n>64)throw std::length_error("definition expression count exceeds limit");d.exprs.reserve(n);for(std::uint32_t i=0;i<n;++i)d.exprs.push_back(get_strings(r,1024));
    d.column=get_size(r);d.cmp=r.str();d.value=r.i64();d.left_key=get_size(r);d.right_key=get_size(r);d.key=get_size(r);d.value_column=get_size(r);auto right=r.u8();if(right>1)throw std::invalid_argument("invalid filter operand kind");if(right)d.right_column=get_size(r);return d;
}
inline void put_tables(Writer&w,const std::vector<Table>&tables){if(tables.size()>128)throw std::length_error("table count exceeds limit");w.u32(static_cast<std::uint32_t>(tables.size()));for(const auto&t:tables){w.str(t.name);w.u8(t.derived?1:0);if(t.columns.empty()||t.columns.size()>64)throw std::length_error("table column count exceeds limit");w.u32(static_cast<std::uint32_t>(t.columns.size()));for(const auto&c:t.columns)w.str(c);}}
inline std::vector<Table> get_tables(Reader&r){auto n=r.u32();if(n>128)throw std::length_error("table count exceeds limit");std::vector<Table> out;out.reserve(n);for(std::uint32_t i=0;i<n;++i){Table t;t.name=r.str();auto d=r.u8();if(d>1)throw std::invalid_argument("invalid derived table flag");t.derived=d!=0;auto c=r.u32();if(!c||c>64)throw std::length_error("table column count exceeds limit");t.columns.reserve(c);for(std::uint32_t j=0;j<c;++j)t.columns.push_back(r.str());out.push_back(std::move(t));}return out;}
inline void put_bag(Writer&w,const std::string&name,const Bag&bag){w.str(name);if(bag.size()>200000)throw std::length_error("relation tuple count exceeds limit");w.u32(static_cast<std::uint32_t>(bag.size()));for(const auto&x:bag){w.u32(static_cast<std::uint32_t>(x.first.size()));for(I v:x.first)w.i64(v);w.i64(x.second);}}
inline Bag get_bag(Reader&r){Bag out;auto n=r.u32();if(n>200000)throw std::length_error("relation tuple count exceeds limit");for(std::uint32_t i=0;i<n;++i){auto width=r.u32();if(!width||width>128)throw std::length_error("tuple width exceeds limit");Row row;row.reserve(width);for(std::uint32_t j=0;j<width;++j)row.push_back(r.i64());I mult=r.i64();if(mult<=0)throw std::invalid_argument("invalid persisted multiplicity");if(!out.emplace(std::move(row),mult).second)throw std::invalid_argument("duplicate persisted tuple");}return out;}

inline Bytes encode_image(const Image&im){Writer w;w.magic("RPSQLC01");w.u32(1);put_tables(w,im.tables);put_strings(w,im.assertions);if(im.definitions.size()>1024)throw std::length_error("definition count exceeds limit");w.u32(static_cast<std::uint32_t>(im.definitions.size()));for(const auto&d:im.definitions)put_definition(w,d);put_strings(w,im.required);if(im.bags.size()>1024)throw std::length_error("relation count exceeds limit");w.u32(static_cast<std::uint32_t>(im.bags.size()));for(const auto&x:im.bags)put_bag(w,x.first,x.second);return w.finish();}
inline Image decode_image(const Bytes&b){Reader r(b);r.magic("RPSQLC01");if(r.u32()!=1)throw std::invalid_argument("unsupported relational codec version");Image im;im.tables=get_tables(r);im.assertions=get_strings(r,128);auto n=r.u32();if(n>1024)throw std::length_error("definition count exceeds limit");im.definitions.reserve(n);for(std::uint32_t i=0;i<n;++i)im.definitions.push_back(get_definition(r));im.required=get_strings(r,1024);n=r.u32();if(n>1024)throw std::length_error("relation count exceeds limit");for(std::uint32_t i=0;i<n;++i){auto name=r.str();if(!im.bags.emplace(name,get_bag(r)).second)throw std::invalid_argument("duplicate relation bag");}r.end();return im;}
inline Bytes encode_delta(const std::map<std::string,Bag>&changes){Writer w;w.magic("RPSQLR01");w.u32(1);w.u8(1);std::size_t count=0;for(const auto&x:changes)if(!x.second.empty())++count;if(count>1024)throw std::length_error("changed relation count exceeds limit");w.u32(static_cast<std::uint32_t>(count));for(const auto&x:changes)if(!x.second.empty()){w.str(x.first);if(x.second.size()>200000)throw std::length_error("relation delta tuple count exceeds limit");w.u32(static_cast<std::uint32_t>(x.second.size()));for(const auto&y:x.second){w.u32(static_cast<std::uint32_t>(y.first.size()));for(I v:y.first)w.i64(v);w.i64(y.second);}}return w.finish();}
inline std::map<std::string,Bag> decode_delta(const Bytes&b){Reader r(b);r.magic("RPSQLR01");if(r.u32()!=1||r.u8()!=1)throw std::invalid_argument("unsupported relational change record");auto n=r.u32();if(n>1024)throw std::length_error("changed relation count exceeds limit");std::map<std::string,Bag> out;for(std::uint32_t i=0;i<n;++i){auto name=r.str();auto count=r.u32();if(count>200000)throw std::length_error("relation delta tuple count exceeds limit");Bag bag;for(std::uint32_t j=0;j<count;++j){auto width=r.u32();if(!width||width>128)throw std::length_error("delta tuple width exceeds limit");Row row;row.reserve(width);for(std::uint32_t k=0;k<width;++k)row.push_back(r.i64());auto amount=r.i64();if(!amount||!bag.emplace(std::move(row),amount).second)throw std::invalid_argument("invalid duplicate or zero relation delta");}if(!out.emplace(name,std::move(bag)).second)throw std::invalid_argument("duplicate changed relation");}r.end();return out;}
inline Bytes encode_ddl(const Image&catalog,const std::map<std::string,Bag>&added){Writer w;w.magic("RPSQLR01");w.u32(1);w.u8(2);put_tables(w,catalog.tables);put_strings(w,catalog.assertions);if(catalog.definitions.size()>1024)throw std::length_error("definition count exceeds limit");w.u32(static_cast<std::uint32_t>(catalog.definitions.size()));for(const auto&d:catalog.definitions)put_definition(w,d);put_strings(w,catalog.required);if(added.size()>1024)throw std::length_error("added relation count exceeds limit");w.u32(static_cast<std::uint32_t>(added.size()));for(const auto&x:added)put_bag(w,x.first,x.second);return w.finish();}
inline Ddl decode_ddl(const Bytes&b){Reader r(b);r.magic("RPSQLR01");if(r.u32()!=1||r.u8()!=2)throw std::invalid_argument("unsupported relational DDL record");Ddl d;d.catalog.tables=get_tables(r);d.catalog.assertions=get_strings(r,128);auto n=r.u32();if(n>1024)throw std::length_error("definition count exceeds limit");d.catalog.definitions.reserve(n);for(std::uint32_t i=0;i<n;++i)d.catalog.definitions.push_back(get_definition(r));d.catalog.required=get_strings(r,1024);n=r.u32();if(n>1024)throw std::length_error("added relation count exceeds limit");for(std::uint32_t i=0;i<n;++i){auto name=r.str();if(!d.added.emplace(name,get_bag(r)).second)throw std::invalid_argument("duplicate DDL relation");}r.end();return d;}
inline std::size_t encoded_image_size(const Image&im){
    Image catalog;catalog.tables=im.tables;catalog.assertions=im.assertions;catalog.definitions=im.definitions;catalog.required=im.required;
    const auto base=encode_image(catalog).size();
    std::size_t total=base;
    for(const auto&entry:im.bags){
        const auto& name=entry.first;const auto&bag=entry.second;
        if(name.size()>sqlstorage::Store::max_payload-total)throw std::length_error("encoded relational state exceeds 64 MiB");
        total+=4+name.size()+4;
        for(const auto&row:bag){
            const std::size_t part=4+row.first.size()*8+8;
            if(part>sqlstorage::Store::max_payload-total)throw std::length_error("encoded relational state exceeds 64 MiB");
            total+=part;
        }
    }
    return total;
}
inline std::size_t bag_size(const std::string&name,const Bag&bag){std::size_t n=4+name.size()+4;for(const auto&row:bag)n+=4+row.first.size()*8+8;return n;}
inline bool equal_definition(const Definition&a,const Definition&b){return a.name==b.name&&a.op==b.op&&a.input==b.input&&a.left==b.left&&a.right==b.right&&a.width==b.width&&a.exprs==b.exprs&&a.column==b.column&&a.cmp==b.cmp&&a.value==b.value&&a.left_key==b.left_key&&a.right_key==b.right_key&&a.key==b.key&&a.value_column==b.value_column&&a.right_column==b.right_column;}
} // namespace refpot::sqlpersistence
