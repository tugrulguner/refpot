// Local in-process preview bridge. No SQLite, subprocess or model execution.
#include "sql.hpp"
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <thread>
#include <unistd.h>
namespace {
struct Handle {
    refpot::sqlpreview::Database db;
    bool poisoned=false;
    pid_t pid=getpid();
    std::thread::id owner=std::this_thread::get_id();
    explicit Handle(int mode):db(mode?refpot::foundation::Mode::Modular:refpot::foundation::Mode::Overlay) {}
    void check() const {
        if(pid!=getpid() || owner!=std::this_thread::get_id()) throw std::runtime_error("wrong native owner");
    }
};
std::string quote(const std::string& s) {
    std::string out="\"";
    for(unsigned char c:s) {
        if(c=='"'||c=='\\'){out+='\\';out+=static_cast<char>(c);}
        else if(c<32) { static const char* hex="0123456789abcdef";out+="\\u00";out+=hex[c>>4];out+=hex[c&15]; }
        else out+=static_cast<char>(c);
    }
    return out+'"';
}
char* copy(const std::string& s) {
    auto p=static_cast<char*>(std::malloc(s.size()+1));
    if(p) std::memcpy(p,s.c_str(),s.size()+1);
    return p;
}
}
extern "C" {
void* rp_sql_open(int mode) noexcept {
    try { return new Handle(mode); } catch(...) {return nullptr;}
}
int rp_sql_close(void* p) noexcept {
    if(!p)return 0;
    auto h=static_cast<Handle*>(p);
    try {h->check();delete h;return 0;} catch(...) {return -1;}
}
int rp_sql_rollback(void* p) noexcept {
    if(!p)return -1;
    auto h=static_cast<Handle*>(p);
    try {h->check();h->db.rollback();return 0;}catch(...){return -1;}
}
void rp_sql_free(void* p) noexcept {std::free(p);}
char* rp_sql_execute(void* p,const char* query,std::size_t length,const std::int64_t* parameters,std::size_t count,int explain) noexcept {
    Handle* owned=nullptr;
    bool executed=false;
    try {
        if(!p || !query || (count&&!parameters))throw std::invalid_argument("invalid bridge input");
        auto h=static_cast<Handle*>(p); h->check();owned=h;
        if(h->poisoned)throw std::runtime_error("native response failed; handle is poisoned");
        if(length>65536 || count>8192)throw std::invalid_argument("bridge input limit exceeded");
        std::vector<refpot::sqlpreview::I> params;
        if(count)params.assign(parameters,parameters+count);
        auto r=h->db.execute(std::string(query,length),params,explain!=0);
        executed=true;
        std::ostringstream out;
        out.exceptions(std::ios::badbit | std::ios::failbit);
        out<<"{\"ok\":true,\"columns\":[";
        for(std::size_t i=0;i<r.columns.size();++i){if(i)out<<',';out<<quote(r.columns[i]);}
        out<<"],\"rows\":[";
        for(std::size_t i=0;i<r.rows.size();++i){
            if(i)out<<',';out<<'[';
            for(std::size_t j=0;j<r.rows[i].size();++j){if(j)out<<',';if(r.rows[i][j])out<<*r.rows[i][j];else out<<"null";}
            out<<']';
        }
        out<<"],\"affected\":"<<r.affected<<",\"plan\":"<<quote(r.plan)
           <<",\"in_transaction\":"<<(h->db.in_transaction()?"true":"false")<<'}';
        return copy(out.str());
    } catch(const std::exception& e) {
        if(owned){if(executed)owned->poisoned=true;if(!explain)owned->db.rollback();}
        try {return copy("{\"ok\":false,\"fatal\":"+std::string(owned&&owned->poisoned?"true":"false")+",\"error\":"+quote(e.what())+"}");}catch(...){return nullptr;}
    } catch(...) {if(owned){owned->poisoned=true;owned->db.rollback();}return nullptr;}
}
}
