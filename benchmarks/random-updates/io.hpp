#include <cstdio>
#include <cstdint>
#include <unistd.h>
#include <chrono>
struct IOStats {uint64_t sync_calls=0,write_calls=0,bytes=0,errors=0;double sync_s=0,write_s=0;};
IOStats io, captured;int io_dsync_fd=-1;uint64_t dsync_write_calls=0;
using IClock=std::chrono::steady_clock;
double isecs(IClock::time_point t){return std::chrono::duration<double>(IClock::now()-t).count();}
extern "C" int __real_fdatasync(int);extern "C" int __real_fsync(int);
extern "C" ssize_t __real_pwrite(int,const void*,size_t,off_t);
extern "C" ssize_t __real_pwrite64(int,const void*,size_t,off64_t);
extern "C" ssize_t __real_write(int,const void*,size_t);
extern "C" int __wrap_fdatasync(int f){auto t=IClock::now();int r=__real_fdatasync(f);io.sync_calls++;io.sync_s+=isecs(t);io.errors+=(r!=0);return r;}
extern "C" int __wrap_fsync(int f){auto t=IClock::now();int r=__real_fsync(f);io.sync_calls++;io.sync_s+=isecs(t);io.errors+=(r!=0);return r;}
extern "C" ssize_t __wrap_pwrite(int f,const void*b,size_t n,off_t o){auto t=IClock::now();auto r=__real_pwrite(f,b,n,o);if(f==io_dsync_fd){io.sync_calls++;io.sync_s+=isecs(t);dsync_write_calls++;}io.write_calls++;io.bytes+=r>0?r:0;io.write_s+=isecs(t);io.errors+=(r<0);return r;}
extern "C" ssize_t __wrap_pwrite64(int f,const void*b,size_t n,off64_t o){auto t=IClock::now();auto r=__real_pwrite64(f,b,n,o);io.write_calls++;io.bytes+=r>0?r:0;io.write_s+=isecs(t);io.errors+=(r<0);return r;}
extern "C" ssize_t __wrap_write(int f,const void*b,size_t n){auto t=IClock::now();auto r=__real_write(f,b,n);io.write_calls++;io.bytes+=r>0?r:0;io.write_s+=isecs(t);io.errors+=(r<0);return r;}
