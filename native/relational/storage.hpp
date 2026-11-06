#pragma once

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <stdexcept>
#include <string>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <vector>

namespace refpot { namespace sqlstorage {
using Bytes = std::vector<unsigned char>;
class Store {
 public:
  static constexpr std::size_t max_payload = 64U * 1024U * 1024U;
  static constexpr std::size_t max_wal = 128U * 1024U * 1024U;
  explicit Store(const std::string& path) : path_(path), wal_path_(path+".wal"), lock_path_(path+".lock"), lock_fd_(-1), wal_fd_(-1), pid_(::getpid()), seq_(0), wal_size_(0), poisoned_(false), has_snapshot_(false) {
    if(path.empty())throw std::invalid_argument("empty store path");
    const auto slash=path_.find_last_of('/');
    parent_path_=slash==std::string::npos?".":(slash==0?"/":path_.substr(0,slash));
    validate_namespace();
    lock_fd_=::open(lock_path_.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600); if(lock_fd_<0)io_error("open lock");
    struct stat ls{}; if(::fstat(lock_fd_,&ls)<0||!S_ISREG(ls.st_mode)||ls.st_nlink!=1){close_fds();throw std::runtime_error("invalid lock file");}
    if(::flock(lock_fd_,LOCK_EX|LOCK_NB)<0){const int e=errno;close_fds();errno=e;io_error("lock store");}
    try{open_files();recover();}catch(...){close_fds();throw;}
  }
  Store(const Store&)=delete; Store& operator=(const Store&)=delete; Store(Store&&)=delete; Store& operator=(Store&&)=delete;
  ~Store(){close_fds();}
  const Bytes& snapshot()const noexcept{return snapshot_;}
  const std::vector<Bytes>& records()const noexcept{return records_;}
  void discard_recovery()noexcept{records_.clear();}
  bool needs_checkpoint(std::size_t n)const{return n>max_payload||wal_size_>max_wal||n>max_wal-wal_size_||frame_overhead()>max_wal-wal_size_-n;}
  void append(const Bytes& payload){
    check_owner(); if(poisoned_)throw std::runtime_error("store is poisoned");
    if(payload.size()>max_payload||needs_checkpoint(payload.size()))throw std::length_error("WAL capacity exceeded");
    if(seq_==std::numeric_limits<std::uint64_t>::max())throw std::length_error("sequence exhausted");
    const auto next=seq_+1; Bytes frame=make_frame(payload,next); Bytes prepared=payload; records_.reserve(records_.size()+1);
    try{write_all(wal_fd_,frame.data(),frame.size()); sync_fd(wal_fd_,"sync WAL");}
    catch(...){poisoned_=true;throw;}
    records_.push_back(std::move(prepared)); seq_=next; wal_size_+=frame.size();
  }
  void checkpoint(const Bytes& state){
    check_owner();if(poisoned_)throw std::runtime_error("store is poisoned");if(state.size()>max_payload)throw std::length_error("snapshot capacity exceeded");
    Bytes encoded=make_snapshot(state,seq_); Bytes prepared=state; const std::string tmp=path_+".tmp";
    int fd=::open(tmp.c_str(),O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW,0600);if(fd<0){poisoned_=true;io_error("open checkpoint temporary");}
    try{write_all(fd,encoded.data(),encoded.size());sync_fd(fd,"sync checkpoint");if(::close(fd)<0){fd=-1;io_error("close checkpoint");}fd=-1;
      if(::rename(tmp.c_str(),path_.c_str())<0)io_error("rename checkpoint");poisoned_=true;sync_directory();
      int trunc_result;do{trunc_result=::ftruncate(wal_fd_,0);}while(trunc_result<0&&errno==EINTR);if(trunc_result<0)io_error("truncate WAL");sync_fd(wal_fd_,"sync truncated WAL");if(::lseek(wal_fd_,0,SEEK_END)<0)io_error("seek truncated WAL");
      snapshot_.swap(prepared);records_.clear();wal_size_=0;has_snapshot_=true;poisoned_=false;
    }catch(...){if(fd>=0)::close(fd);poisoned_=true;throw;}
  }
  bool poisoned()const noexcept{return poisoned_;}
  std::uint64_t sequence()const noexcept{return seq_;}
 private:
  static constexpr std::size_t snap_header_size(){return 48;}
  static constexpr std::size_t frame_header_size(){return 48;}
  static constexpr std::size_t frame_overhead(){return frame_header_size()+4;}
  std::string path_,wal_path_,lock_path_,parent_path_;int lock_fd_,wal_fd_;pid_t pid_;std::uint64_t seq_;std::size_t wal_size_;bool poisoned_,has_snapshot_;std::array<unsigned char,16> id_{};Bytes snapshot_;std::vector<Bytes> records_;
  static void io_error(const char* s){throw std::runtime_error(std::string(s)+": "+std::strerror(errno));}
  static std::uint32_t crc32(const unsigned char*p,std::size_t n)noexcept{std::uint32_t c=0xffffffffU;for(std::size_t i=0;i<n;++i){c^=p[i];for(int k=0;k<8;++k)c=(c>>1U)^(0xedb88320U&(0U-(c&1U)));}return ~c;}
  static void put32(Bytes&b,std::size_t o,std::uint32_t v){for(unsigned i=0;i<4;++i)b[o+i]=static_cast<unsigned char>(v>>(8U*i));}
  static void put64(Bytes&b,std::size_t o,std::uint64_t v){for(unsigned i=0;i<8;++i)b[o+i]=static_cast<unsigned char>(v>>(8U*i));}
  static std::uint32_t get32(const unsigned char*p){std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(p[i])<<(8U*i);return v;}
  static std::uint64_t get64(const unsigned char*p){std::uint64_t v=0;for(unsigned i=0;i<8;++i)v|=std::uint64_t(p[i])<<(8U*i);return v;}
  static void sync_fd(int fd,const char*what){int r;do{r=::fsync(fd);}while(r<0&&errno==EINTR);if(r<0)io_error(what);}
  static void write_all(int fd,const unsigned char*p,std::size_t n){std::size_t d=0;while(d<n){ssize_t r=::write(fd,p+d,n-d);if(r<0&&errno==EINTR)continue;if(r<=0)io_error("write store");d+=static_cast<std::size_t>(r);}}
  static void read_exact(int fd,unsigned char*p,std::size_t n){std::size_t d=0;while(d<n){ssize_t r=::read(fd,p+d,n-d);if(r<0&&errno==EINTR)continue;if(r<=0)io_error("read store");d+=static_cast<std::size_t>(r);}}
  void check_owner()const{if(::getpid()!=pid_)throw std::runtime_error("store used after fork");}
  void close_fds()noexcept{if(wal_fd_>=0){::close(wal_fd_);wal_fd_=-1;}if(lock_fd_>=0){::close(lock_fd_);lock_fd_=-1;}}
  void validate_namespace(){struct stat st{};errno=0;if(::lstat(path_.c_str(),&st)==0&&(!S_ISREG(st.st_mode)||st.st_nlink!=1))throw std::runtime_error("invalid database path");if(errno&&errno!=ENOENT)io_error("inspect database path");
    for(const auto&p:{wal_path_,lock_path_,path_+".tmp"}){errno=0;if(::lstat(p.c_str(),&st)==0&&(!S_ISREG(st.st_mode)||st.st_nlink!=1))throw std::runtime_error("invalid sidecar path");if(errno&&errno!=ENOENT)io_error("inspect sidecar path");}
    if(::lstat(parent_path_.c_str(),&st)<0||!S_ISDIR(st.st_mode))throw std::runtime_error("store parent must be a real directory");}
  void open_files(){int fd=::open(path_.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW);if(fd>=0){struct stat s{};if(::fstat(fd,&s)<0||!S_ISREG(s.st_mode)||s.st_nlink!=1){::close(fd);throw std::runtime_error("invalid snapshot file");}try{read_snapshot(fd);}catch(...){::close(fd);throw;}::close(fd);has_snapshot_=true;}else if(errno!=ENOENT)io_error("open snapshot");
    struct stat before{}; errno=0; bool wal_existed=(::lstat(wal_path_.c_str(),&before)==0); if(!wal_existed&&errno!=ENOENT)io_error("inspect WAL path");
    wal_fd_=::open(wal_path_.c_str(),O_RDWR|O_CREAT|O_CLOEXEC|O_NOFOLLOW,0600);if(wal_fd_<0)io_error("open WAL");struct stat s{};if(::fstat(wal_fd_,&s)<0||!S_ISREG(s.st_mode)||s.st_nlink!=1){close_fds();throw std::runtime_error("invalid WAL file");}if(!wal_existed)sync_directory();}
  void random_identity(){int fd=::open("/dev/urandom",O_RDONLY|O_CLOEXEC);if(fd<0)io_error("open random source");std::size_t n=0;while(n<id_.size()){ssize_t r=::read(fd,id_.data()+n,id_.size()-n);if(r<0&&errno==EINTR)continue;if(r<=0){::close(fd);io_error("read random source");}n+=static_cast<std::size_t>(r);}::close(fd);}
  Bytes make_snapshot(const Bytes&p,std::uint64_t s)const{Bytes b(snap_header_size()+p.size(),0);std::memcpy(b.data(),"RPSQLS01",8);put32(b,8,1);std::memcpy(b.data()+12,id_.data(),16);put64(b,28,s);put32(b,36,static_cast<std::uint32_t>(p.size()));put32(b,40,crc32(p.data(),p.size()));put32(b,44,crc32(b.data(),44));std::copy(p.begin(),p.end(),b.begin()+48);return b;}
  Bytes make_frame(const Bytes&p,std::uint64_t s)const{Bytes b(frame_overhead()+p.size(),0);std::memcpy(b.data(),"RPSQLW01",8);put32(b,8,1);std::memcpy(b.data()+12,id_.data(),16);put64(b,28,s);put32(b,36,static_cast<std::uint32_t>(p.size()));put32(b,40,crc32(p.data(),p.size()));put32(b,44,crc32(b.data(),44));std::copy(p.begin(),p.end(),b.begin()+48);put32(b,48+p.size(),crc32(p.data(),p.size()));return b;}
  void read_snapshot(int fd){struct stat s{};if(::fstat(fd,&s)<0)io_error("stat snapshot");if(s.st_size<48||s.st_size>static_cast<off_t>(max_payload+48))throw std::runtime_error("invalid snapshot size");Bytes b(static_cast<std::size_t>(s.st_size));read_exact(fd,b.data(),b.size());if(std::memcmp(b.data(),"RPSQLS01",8)||get32(b.data()+8)!=1||get32(b.data()+44)!=crc32(b.data(),44))throw std::runtime_error("corrupt snapshot header");auto n=get32(b.data()+36);if(n>max_payload||b.size()!=48+n||get32(b.data()+40)!=crc32(b.data()+48,n))throw std::runtime_error("corrupt snapshot payload");std::copy(b.begin()+12,b.begin()+28,id_.begin());seq_=get64(b.data()+28);snapshot_.assign(b.begin()+48,b.end());}
  void recover(){struct stat s{};if(::fstat(wal_fd_,&s)<0)io_error("stat WAL");if(s.st_size<0||s.st_size>static_cast<off_t>(max_wal))throw std::runtime_error("WAL capacity exceeded");wal_size_=static_cast<std::size_t>(s.st_size);Bytes b(wal_size_);if(!b.empty()){if(::lseek(wal_fd_,0,SEEK_SET)<0)io_error("seek WAL");read_exact(wal_fd_,b.data(),b.size());}
    std::size_t off=0,valid=0;const std::uint64_t snapshot_sequence=seq_;std::uint64_t previous=0;bool have_id=has_snapshot_;while(off<b.size()){std::size_t remain=b.size()-off;if(remain<48)break;const auto*h=b.data()+off;if(std::memcmp(h,"RPSQLW01",8)||get32(h+8)!=1||get32(h+44)!=crc32(h,44))throw std::runtime_error("corrupt WAL frame header");auto n=get32(h+36);if(n>max_payload)throw std::runtime_error("WAL payload bound exceeded");std::size_t total=frame_overhead()+n;if(remain<total)break;if(get32(h+40)!=crc32(h+48,n)||get32(h+48+n)!=crc32(h+48,n))throw std::runtime_error("corrupt WAL payload");if(!have_id){std::copy(h+12,h+28,id_.begin());have_id=true;}else if(std::memcmp(h+12,id_.data(),16))throw std::runtime_error("wrong store identity in WAL");auto seq=get64(h+28);if(!seq||seq<=previous||(previous&&seq!=previous+1))throw std::runtime_error("invalid WAL sequence");if(!previous&&snapshot_sequence!=std::numeric_limits<std::uint64_t>::max()&&seq>snapshot_sequence+1)throw std::runtime_error("WAL sequence gap");previous=seq;if(seq>snapshot_sequence){if(seq!=seq_+1)throw std::runtime_error("WAL sequence gap");records_.emplace_back(h+48,h+48+n);seq_=seq;}valid=off+total;off=valid;}
    if(!have_id)random_identity();if(valid<b.size()){int tr;do{tr=::ftruncate(wal_fd_,static_cast<off_t>(valid));}while(tr<0&&errno==EINTR);if(tr<0)io_error("truncate interrupted WAL");sync_fd(wal_fd_,"sync repaired WAL");wal_size_=valid;}if(::lseek(wal_fd_,0,SEEK_END)<0)io_error("seek WAL end");}
  void sync_directory()const{int fd=::open(parent_path_.c_str(),O_RDONLY|O_CLOEXEC);if(fd<0)io_error("open parent directory");try{sync_fd(fd,"sync parent directory");}catch(...){::close(fd);throw;}if(::close(fd)<0)io_error("close parent directory");}
};
}} // namespace refpot::sqlstorage
