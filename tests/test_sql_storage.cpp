#include "../native/relational/storage.hpp"

#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

using refpot::sqlstorage::Bytes;
using refpot::sqlstorage::Store;

namespace {
std::string temp_dir() {
  char pattern[] = "/Users/tugrulguner/.hermes/cache/scratch/sql-store-test-XXXXXX";
  char* result = ::mkdtemp(pattern);
  assert(result != nullptr);
  return result;
}
Bytes bytes(std::string s) { return Bytes(s.begin(), s.end()); }
std::string text(const Bytes& b) { return std::string(b.begin(), b.end()); }
void write_file(const std::string& path, const Bytes& data) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  out.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
}
Bytes read_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  return Bytes(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}
void clean(const std::string& path) {
  ::unlink((path + ".wal").c_str()); ::unlink((path + ".lock").c_str());
  ::unlink((path + ".tmp").c_str()); ::unlink(path.c_str()); ::rmdir(path.substr(0, path.find_last_of('/')).c_str());
}
void reopen_test() {
  const auto dir = temp_dir(); const auto path = dir + "/db";
  {
    Store store(path); assert(store.snapshot().empty()); assert(store.sequence() == 0);
    store.append(bytes("one")); store.append(bytes("two"));
    assert(store.sequence() == 2); assert(store.records().size() == 2);
    store.checkpoint(bytes("checkpoint")); assert(store.sequence() == 2);
    assert(store.records().empty()); store.append(bytes("after-checkpoint")); assert(store.sequence() == 3);
  }
  {
    Store store(path); assert(text(store.snapshot()) == "checkpoint");
    assert(store.sequence() == 3); assert(store.records().size() == 1);
    assert(text(store.records()[0]) == "after-checkpoint");
    store.append(bytes("three")); assert(store.sequence() == 4);
  }
  { Store s(path); assert(s.sequence() == 4); assert(s.records().size() == 2); assert(text(s.records()[1]) == "three"); }
  const auto stale = read_file(path + ".wal");
  { Store s(path); s.checkpoint(bytes("new-snapshot")); }
  write_file(path + ".wal", stale);
  { Store s(path); assert(s.sequence() == 4); assert(text(s.snapshot()) == "new-snapshot"); assert(s.records().empty()); s.append(bytes("after-stale")); }
  { Store s(path); assert(s.sequence() == 5); assert(s.records().size() == 1); assert(text(s.records()[0]) == "after-stale"); }
  clean(path);
}
void recovery_prefix_test() {
  const auto dir = temp_dir(); const auto base = dir + "/base";
  { Store s(base); s.checkpoint(bytes("acked")); s.append(bytes("tail")); }
  const Bytes wal = read_file(base + ".wal");
  const Bytes snap = read_file(base);
  assert(wal.size() > 8);
  for (std::size_t prefix = 0; prefix < wal.size(); ++prefix) {
    const auto path = dir + "/p" + std::to_string(prefix);
    { Store s(path); }
    write_file(path, snap);
    write_file(path + ".wal", Bytes(wal.begin(), wal.begin() + static_cast<std::ptrdiff_t>(prefix)));
    { Store s(path); assert(text(s.snapshot()) == "acked");
      assert(s.records().empty()); s.append(bytes("next")); }
    { Store s(path); assert(s.sequence() == 1U); assert(text(s.records().back()) == "next"); }
    clean(path);
  }
  clean(base);
}
void corruption_and_lock_test() {
  const auto dir = temp_dir(); const auto path = dir + "/db";
  { Store s(path); s.append(bytes("payload")); s.checkpoint(bytes("snapshot")); }
  auto snap = read_file(path); assert(!snap.empty()); const auto good_snap = snap;
  snap[0] ^= 0x40; write_file(path, snap);
  bool rejected = false; try { Store s(path); } catch (...) { rejected = true; }
  assert(rejected); snap = good_snap; snap.back() ^= 0x40; write_file(path, snap);
  rejected = false; try { Store s(path); } catch (...) { rejected = true; }
  assert(rejected); write_file(path, good_snap);
  { Store s(path); s.append(bytes("payload")); }
  auto wal = read_file(path + ".wal"); assert(!wal.empty());
  auto corrupt_header = wal; corrupt_header[0] ^= 0x40; write_file(path + ".wal", corrupt_header);
  rejected = false; try { Store s(path); } catch (...) { rejected = true; }
  assert(rejected); wal.back() ^= 0x40; write_file(path + ".wal", wal);
  rejected = false; try { Store s(path); } catch (...) { rejected = true; }
  assert(rejected);
  write_file(path + ".wal", {});
  Store owner(path); rejected = false; try { Store contender(path); } catch (...) { rejected = true; }
  assert(rejected);
  const auto dir_alias = dir + "/dir-alias"; assert(::symlink(dir.c_str(), dir_alias.c_str()) == 0);
  rejected = false; try { Store contender(dir_alias + "/db"); } catch (...) { rejected = true; }
  assert(rejected); ::unlink(dir_alias.c_str());
  // The prior refusal was only because `owner` held the lock. Directory aliases
  // must also be rejected when no canonical opener happens to be active.
  owner.~Store();
  assert(::symlink(dir.c_str(), dir_alias.c_str()) == 0);
  rejected = false; try { Store aliased(dir_alias + "/db"); } catch (...) { rejected = true; }
  assert(rejected); ::unlink(dir_alias.c_str());
  new (&owner) Store(path);
  const auto alias = dir + "/alias"; assert(::link(path.c_str(), alias.c_str()) == 0);
  rejected = false; try { Store bad(alias); } catch (...) { rejected = true; }
  assert(rejected); ::unlink(alias.c_str());
  const auto sym = dir + "/sym"; assert(::symlink(path.c_str(), sym.c_str()) == 0);
  rejected = false; try { Store bad(sym); } catch (...) { rejected = true; }
  assert(rejected); ::unlink(sym.c_str());
  const auto foreign = dir + "/foreign";
  { Store s(foreign); s.append(bytes("foreign")); }
  const auto target = dir + "/target";
  { Store s(target); s.checkpoint(bytes("target")); }
  write_file(target + ".wal", read_file(foreign + ".wal"));
  rejected = false; try { Store bad(target); } catch (...) { rejected = true; }
  assert(rejected);
  ::unlink((foreign + ".wal").c_str()); ::unlink((foreign + ".lock").c_str()); ::unlink(foreign.c_str());
  ::unlink((target + ".wal").c_str()); ::unlink((target + ".lock").c_str()); ::unlink(target.c_str());
  clean(path);
}
void fork_test() {
  const auto dir = temp_dir(); const auto path = dir + "/db";
  Store parent(path);
  const pid_t child = ::fork(); assert(child >= 0);
  if (child == 0) {
    bool refused = false;
    try { parent.append(bytes("child")); } catch (...) { refused = true; }
    parent.~Store();
    bool lock_retained = false;
    try { Store contender(path); } catch (...) { lock_retained = true; }
    _exit(refused && lock_retained ? 0 : 1);
  }
  int status = 0; assert(::waitpid(child, &status, 0) == child);
  assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
  parent.append(bytes("parent")); assert(parent.sequence() == 1);
  clean(path);
}
}
int main() {
  reopen_test(); recovery_prefix_test(); corruption_and_lock_test(); fork_test();
  std::cout << "SQL storage tests passed\n";
}
