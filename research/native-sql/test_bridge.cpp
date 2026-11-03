#include <cstdlib>
#include <cstring>
#include <new>
#include <cassert>
#include <iostream>
static long fail_at=-1, allocations=0;
void* operator new(std::size_t n){if(fail_at>=0&&allocations++==fail_at)throw std::bad_alloc();if(auto p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void operator delete(void* p)noexcept{std::free(p);}
void operator delete(void* p,std::size_t)noexcept{std::free(p);}
#include "bridge.cpp"
static char* call(void* h,const char* q){return rp_sql_execute(h,q,std::strlen(q),nullptr,0,0);}
int main(){
    long rejected=0,fatal=0;bool completed=false;
    for(long cut=0;cut<1000&&!completed;++cut){
        void* h=rp_sql_open(0);assert(h);
        char* setup=call(h,"CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)");assert(setup&&std::strstr(setup,"\"ok\":true"));rp_sql_free(setup);
        allocations=0;fail_at=cut;
        char* response=call(h,"INSERT INTO stock VALUES (1, 10)");
        const long observed=allocations;
        fail_at=-1;
        if(!response||std::strstr(response,"\"fatal\":true")){++fatal;}
        else if(std::strstr(response,"\"ok\":false")){
            ++rejected;
            char* state=call(h,"SELECT * FROM stock");
            assert(state&&std::strstr(state,"\"rows\":[]")&&"nonfatal failure must not hide published writes");rp_sql_free(state);
        }else {assert(std::strstr(response,"\"ok\":true"));assert(std::strstr(response,"\"affected\":1")&&std::strstr(response,"\"in_transaction\":false}"));completed=cut>=observed;}
        rp_sql_free(response);assert(rp_sql_close(h)==0);
    }
    assert(completed&&rejected>0);
    std::cout<<"bridge fault cuts: rejected="<<rejected<<" fatal="<<fatal<<"\n";
}
