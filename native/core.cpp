#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <map>
#include <set>
#include <mutex>
#include <type_traits>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/file.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

namespace py = pybind11;
using Bytes = std::vector<unsigned char>;
struct Row { int64_t key, value; std::string text; };
struct KeyLess { bool operator()(int64_t left, int64_t right) const noexcept { return left < right; } };
using Rows = std::map<int64_t, Row, KeyLess>;
constexpr size_t MAX_BYTES = 64 * 1024 * 1024;

static uint32_t crc(const unsigned char* p, size_t n) {
    uint32_t c = ~0u;
    for (size_t i = 0; i < n; ++i) {
        c ^= p[i];
        for (int j = 0; j < 8; ++j) c = (c >> 1) ^ (0xedb88320u & -(c & 1));
    }
    return ~c;
}
static void put(Bytes& b, uint64_t v, size_t n) {
    for (size_t i = 0; i < n; ++i) b.push_back((v >> (8 * i)) & 255);
}
static uint64_t number(const unsigned char* p, size_t n) {
    uint64_t v = 0;
    for (size_t i = 0; i < n; ++i) v |= uint64_t(p[i]) << (8 * i);
    return v;
}
static void need(bool valid, const char* message) {
    if (!valid) throw std::runtime_error(message);
}
static void full_write(int fd, const Bytes& b) {
    size_t offset = 0;
    while (offset < b.size()) {
        ssize_t n = ::write(fd, b.data() + offset, b.size() - offset);
        if (n < 0 && errno == EINTR) continue;
        need(n > 0, "write failed; reopen before further operations");
        offset += size_t(n);
    }
}
static Bytes read_file(const std::string& path) {
    struct stat st{};
    if (::stat(path.c_str(), &st)) {
        if (errno == ENOENT) return {};
        throw std::runtime_error("stat failed");
    }
    need(S_ISREG(st.st_mode) && st.st_size >= 0 && uint64_t(st.st_size) <= MAX_BYTES,
         "file size/type exceeds format bounds");
    std::ifstream file(path, std::ios::binary);
    need(bool(file), "read failed");
    Bytes bytes(size_t(st.st_size));
    file.read(reinterpret_cast<char*>(bytes.data()), bytes.size());
    need(file.good() || (file.eof() && file.gcount() == std::streamsize(bytes.size())), "short read");
    return bytes;
}
static void row_bytes(Bytes& b, const Row& r) {
    put(b, uint64_t(r.key), 8); put(b, uint64_t(r.value), 8);
    put(b, r.text.size(), 1); b.insert(b.end(), r.text.begin(), r.text.end());
}
static Row parse_row(const Bytes& b, size_t& at, size_t limit) {
    need(at <= limit && limit - at >= 17, "truncated record");
    Row r{int64_t(number(b.data() + at, 8)), int64_t(number(b.data() + at + 8, 8)), ""};
    size_t len = b[at + 16]; at += 17;
    need(len <= 31 && len <= limit - at, "record text bounds");
    r.text.assign(reinterpret_cast<const char*>(b.data() + at), len); at += len;
    PyObject* decoded = PyUnicode_DecodeUTF8(r.text.data(), r.text.size(), "strict");
    if (!decoded) { PyErr_Clear(); throw std::runtime_error("invalid stored UTF-8"); }
    Py_DECREF(decoded);
    return r;
}

class Database {
    std::string path;
    int lockfd = -1, wal = -1;
    pid_t owner = ::getpid();
    bool closed = false, poisoned = false, tx = false;
    uint64_t sequence = 0;
    Rows rows, changes;
    std::set<int64_t, KeyLess> deletions;
    size_t encoded_size = 32;
    size_t staged_size = 32;
    size_t staged_count = 0;
    std::recursive_mutex mutex;

    const Row* visible(int64_t key) const {
        auto changed = changes.find(key);
        if (tx && changed != changes.end()) return &changed->second;
        if (tx && deletions.count(key)) return nullptr;
        auto found = rows.find(key);
        return found == rows.end() ? nullptr : &found->second;
    }
    static size_t row_size(const Row& row) { return 17 + row.text.size(); }
    void stage_row(const Row& row) {
        auto old = visible(row.key);
        const bool existed = old != nullptr;
        if (old && old->value == row.value && old->text == row.text) return;
        size_t next_size = staged_size;
        if (existed) next_size -= row_size(*old);
        size_t addition = row_size(row);
        if (addition > MAX_BYTES - next_size)
            throw std::invalid_argument("database snapshot capacity exceeded");
        next_size += addition;
        // Construct before changing the effects so allocation failure is operation-atomic.
        Row prepared = row;
        auto found = changes.find(row.key);
        if (found == changes.end()) changes.emplace(row.key, std::move(prepared));
        else found->second = std::move(prepared);
        deletions.erase(row.key);
        staged_size = next_size;
        if (!existed) ++staged_count;
    }
    void stage_delete(int64_t key) {
        const Row* old = visible(key);
        need(old != nullptr, "missing row");
        size_t next_size = staged_size - row_size(*old);
        auto removed = changes.find(key);
        if (rows.find(key) != rows.end()) deletions.insert(key);
        else deletions.erase(key);
        if (removed != changes.end()) changes.erase(removed);
        staged_size = next_size;
        --staged_count;
    }
    void apply_changes() noexcept {
        static_assert(std::is_nothrow_move_assignable_v<Row>);
        static_assert(noexcept(KeyLess{}(int64_t{}, int64_t{})));
        for (int64_t key : deletions) rows.erase(key);
        while (!changes.empty()) {
            auto node = changes.extract(changes.begin());
            auto found = rows.find(node.key());
            if (found == rows.end()) rows.insert(std::move(node));
            else found->second = std::move(node.mapped());
        }
        deletions.clear();
        encoded_size = staged_size;
    }

    void check() const {
        need(::getpid() == owner, "database is not usable after fork");
        need(!closed, "database is closed"); need(!poisoned, "database writer is poisoned; reopen required");
    }
    void sync_dir() {
        int fd = ::open(std::filesystem::path(path).parent_path().c_str(), O_RDONLY);
        need(fd >= 0, "directory open failed");
        int result = ::fsync(fd); ::close(fd); need(result == 0, "directory sync failed");
    }
    void release() noexcept {
        if (wal >= 0) { ::close(wal); wal = -1; }
        if (lockfd >= 0) { if (::getpid() == owner) ::flock(lockfd, LOCK_UN); ::close(lockfd); lockfd = -1; }
    }
    void load_snapshot() {
        if (!std::filesystem::exists(path)) return;
        Bytes b = read_file(path);
        need(b.size() >= 32 && !std::memcmp(b.data(), "RPSNAP2\0", 8), "snapshot magic");
        need(number(b.data() + 8, 4) == 2, "unsupported storage version");
        need(crc(b.data(), b.size() - 4) == number(b.data() + b.size() - 4, 4), "snapshot checksum");
        sequence = number(b.data() + 12, 8);
        uint64_t count = number(b.data() + 20, 8);
        need(count <= (b.size() - 32) / 17, "snapshot record count");
        size_t at = 28;
        for (uint64_t i = 0; i < count; ++i) {
            Row r = parse_row(b, at, b.size() - 4);
            need(rows.emplace(r.key, r).second, "duplicate stored key");
            encoded_size += row_size(r);
        }
        need(at == b.size() - 4, "snapshot trailing bytes");
    }
    bool valid_frame(const Bytes& frame) {
        return frame.size() >= 28 && !std::memcmp(frame.data(), "RPREDO2\0", 8) &&
            crc(frame.data(), frame.size() - 4) == number(frame.data() + frame.size() - 4, 4);
    }
    void replay(const Bytes& frame, uint64_t& previous) {
        uint64_t seq = number(frame.data() + 8, 8), count = number(frame.data() + 16, 8);
        need(seq > 0 && (previous == 0 || seq == previous + 1), "redo sequence gap");
        previous = seq;
        need(count <= (frame.size() - 28) / 9, "redo operation count");
        size_t at = 24; Rows upserts; std::set<int64_t, KeyLess> removals;
        for (uint64_t i = 0; i < count; ++i) {
            need(at < frame.size() - 4, "truncated redo operation");
            unsigned char kind = frame[at++];
            if (kind == 0) {
                need(frame.size() - 4 - at >= 8, "truncated delete");
                int64_t key = int64_t(number(frame.data() + at, 8)); at += 8;
                upserts.erase(key); removals.insert(key);
            } else {
                need(kind == 1, "redo operation kind");
                Row row = parse_row(frame, at, frame.size() - 4);
                removals.erase(row.key); upserts.insert_or_assign(row.key, std::move(row));
            }
        }
        need(at == frame.size() - 4, "redo trailing bytes");
        if (seq > sequence) {
            need(seq == sequence + 1, "redo frontier gap");
            size_t next_size = encoded_size;
            for (int64_t key : removals) {
                auto found = rows.find(key);
                if (found != rows.end()) next_size -= row_size(found->second);
            }
            for (const auto& [key, row] : upserts) {
                auto found = rows.find(key);
                if (found != rows.end()) next_size -= row_size(found->second);
                size_t addition = row_size(row);
                need(addition <= MAX_BYTES - next_size, "database snapshot capacity exceeded");
                next_size += addition;
            }
            for (int64_t key : removals) {
                auto found = rows.find(key);
                if (found != rows.end()) { encoded_size -= row_size(found->second); rows.erase(found); }
            }
            while (!upserts.empty()) {
                auto node = upserts.extract(upserts.begin());
                auto found = rows.find(node.key());
                if (found == rows.end()) { encoded_size += row_size(node.mapped()); rows.insert(std::move(node)); }
                else { encoded_size -= row_size(found->second); encoded_size += row_size(node.mapped()); found->second = std::move(node.mapped()); }
            }
            sequence = seq;
        }
    }
    void recover() {
        Bytes b = read_file(path + ".wal");
        size_t at = 0; uint64_t previous = 0;
        while (at < b.size()) {
            if (b.size() - at < 8) break;
            size_t size = number(b.data() + at, 4);
            need((uint32_t(size) ^ uint32_t(number(b.data() + at + 4, 4))) == UINT32_MAX, "redo length checksum");
            need(size >= 28 && size <= MAX_BYTES / 2, "redo frame bounds");
            if (b.size() - at - 8 < size * 2) break; // incomplete, unacknowledged trailing record
            Bytes first(b.begin() + at + 8, b.begin() + at + 8 + size);
            Bytes second(b.begin() + at + 8 + size, b.begin() + at + 8 + size * 2);
            bool a = valid_frame(first), c = valid_frame(second);
            need(a || c, "both redo copies invalid");
            need(!(a && c) || first == second, "redo copies disagree");
            replay(a ? first : second, previous);
            at += 8 + size * 2;
        }
        // Only an incomplete trailing physical record is truncated; complete corrupt frames fail closed.
        if (at != b.size()) {
            need(::ftruncate(wal, at) == 0 && ::fsync(wal) == 0, "truncate incomplete redo failed");
        }
        need(::lseek(wal, 0, SEEK_END) >= 0, "redo seek failed");
    }
    void persist() {
        need(sequence != UINT64_MAX, "transaction identity exhausted");
        if (changes.empty() && deletions.empty()) return;
        need(staged_size <= MAX_BYTES, "database snapshot capacity exceeded");
        Bytes body; const char magic[8] = {'R','P','R','E','D','O','2','\0'};
        body.insert(body.end(), magic, magic + 8); put(body, sequence + 1, 8);
        uint64_t count = deletions.size() + changes.size();
        Bytes ops; ops.reserve(size_t(count) * 9);
        for (int64_t key : deletions) { ops.push_back(0); put(ops, uint64_t(key), 8); }
        for (const auto& [key, row] : changes) { ops.push_back(1); row_bytes(ops, row); }
        put(body, count, 8); body.insert(body.end(), ops.begin(), ops.end());
        put(body, crc(body.data(), body.size()), 4);
        if (body.size() > (MAX_BYTES - 8) / 2)
            throw std::invalid_argument("transaction redo capacity exceeded");
        struct stat st{}; need(::fstat(wal, &st) == 0, "redo stat failed");
        if (uint64_t(st.st_size) + 8 + body.size() * 2 > MAX_BYTES) checkpoint();
        Bytes frame; put(frame, body.size(), 4); put(frame, ~uint32_t(body.size()), 4); frame.insert(frame.end(), body.begin(), body.end());
        frame.insert(frame.end(), body.begin(), body.end());
        try { full_write(wal, frame); need(::fsync(wal) == 0, "redo sync failed"); }
        catch (...) { poisoned = true; throw; }
        ++sequence;
    }
public:
    explicit Database(std::string p) : path(std::filesystem::absolute(p).lexically_normal().string()) {
        try {
            need(std::filesystem::is_directory(std::filesystem::path(path).parent_path()), "database parent must exist");
            need(!std::filesystem::is_symlink(path), "database symlinks are unsupported");
            struct stat identity{};
            if (::stat(path.c_str(), &identity) == 0) need(identity.st_nlink == 1, "database hard links are unsupported");
            lockfd = ::open((path + ".lock").c_str(), O_CREAT | O_RDWR, 0600);
            need(lockfd >= 0, "lock open failed");
            need(::flock(lockfd, LOCK_EX | LOCK_NB) == 0, "database already locked");
            wal = ::open((path + ".wal").c_str(), O_CREAT | O_RDWR | O_APPEND, 0600);
            need(wal >= 0, "redo open failed");
            need(::fsync(wal) == 0, "initial redo sync failed"); sync_dir();
            load_snapshot(); recover();
        } catch (...) { release(); throw; }
    }
    ~Database() { release(); }
    void begin() {
        std::lock_guard<std::recursive_mutex> g(mutex); check(); need(!tx, "nested transaction");
        changes.clear(); deletions.clear(); staged_size = encoded_size; staged_count = rows.size(); tx = true;
    }
    void commit() {
        std::lock_guard<std::recursive_mutex> g(mutex); check(); need(tx, "no transaction");
        try { persist(); apply_changes(); tx = false; }
        catch (...) { changes.clear(); deletions.clear(); staged_size = encoded_size; staged_count = rows.size(); tx = false; throw; }
    }
    void rollback() {
        std::lock_guard<std::recursive_mutex> g(mutex); check(); changes.clear(); deletions.clear();
        staged_size = encoded_size; staged_count = rows.size(); tx = false;
    }
    void insert(int64_t key, int64_t value, std::string text) {
        std::lock_guard<std::recursive_mutex> g(mutex); check();
        if (text.size() > 31) throw std::invalid_argument("text exceeds 31 UTF-8 bytes");
        if (visible(key)) throw std::invalid_argument("duplicate key");
        if (!tx) { changes.clear(); deletions.clear(); staged_size = encoded_size; staged_count = rows.size(); }
        stage_row(Row{key, value, std::move(text)});
        if (!tx) { try { persist(); apply_changes(); } catch (...) { changes.clear(); deletions.clear(); staged_size = encoded_size; throw; } }
    }
    Row fetch(int64_t key) {
        std::lock_guard<std::recursive_mutex> g(mutex); check();
        const Row* row = visible(key); if (!row) throw py::key_error("key not found"); return *row;
    }
    void update(int64_t key, py::object value, py::object text) {
        std::lock_guard<std::recursive_mutex> g(mutex); check();
        const Row* found = visible(key); if (!found) throw py::key_error("key not found");
        Row row = *found;
        if (!value.is_none()) row.value = value.cast<int64_t>();
        if (!text.is_none()) row.text = text.cast<std::string>();
        if (row.text.size() > 31) throw std::invalid_argument("text exceeds 31 UTF-8 bytes");
        if (!tx) { changes.clear(); deletions.clear(); staged_size = encoded_size; staged_count = rows.size(); }
        stage_row(row);
        if (!tx) { try { persist(); apply_changes(); } catch (...) { changes.clear(); deletions.clear(); staged_size = encoded_size; throw; } }
    }
    void erase(int64_t key) {
        std::lock_guard<std::recursive_mutex> g(mutex); check();
        if (!visible(key)) throw py::key_error("key not found");
        if (!tx) { changes.clear(); deletions.clear(); staged_size = encoded_size; staged_count = rows.size(); }
        stage_delete(key);
        if (!tx) { try { persist(); apply_changes(); } catch (...) { changes.clear(); deletions.clear(); staged_size = encoded_size; throw; } }
    }
    size_t size() { std::lock_guard<std::recursive_mutex> g(mutex); check(); return tx ? staged_count : rows.size(); }
    void checkpoint() {
        std::lock_guard<std::recursive_mutex> g(mutex); check();
        // Automatic checkpoint may happen while a prepared transaction is pending; only committed rows are published.
        Bytes b; const char magic[8] = {'R','P','S','N','A','P','2','\0'};
        b.insert(b.end(), magic, magic + 8); put(b, 2, 4); put(b, sequence, 8); put(b, rows.size(), 8);
        for (auto& [key, r] : rows) row_bytes(b, r);
        put(b, crc(b.data(), b.size()), 4); need(b.size() <= MAX_BYTES, "checkpoint exceeds format bounds");
        int fd = -1;
        try {
            fd = ::open((path + ".tmp").c_str(), O_CREAT | O_TRUNC | O_WRONLY, 0600); need(fd >= 0, "checkpoint open failed");
            full_write(fd, b); need(::fsync(fd) == 0, "checkpoint sync failed"); ::close(fd); fd = -1;
            need(::rename((path + ".tmp").c_str(), path.c_str()) == 0, "checkpoint rename failed"); sync_dir();
            need(::ftruncate(wal, 0) == 0 && ::fsync(wal) == 0, "redo reclamation failed");
            need(::lseek(wal, 0, SEEK_END) >= 0, "redo reset failed");
        } catch (...) { if (fd >= 0) ::close(fd); poisoned = true; throw; }
    }
    void close() { std::lock_guard<std::recursive_mutex> g(mutex); need(::getpid() == owner, "database is not usable after fork"); changes.clear(); deletions.clear(); tx = false; closed = true; release(); }
};

PYBIND11_MODULE(_core, m) {
    py::class_<Row>(m, "Row").def_readonly("key", &Row::key).def_readonly("value", &Row::value).def_readonly("text", &Row::text);
    py::class_<Database>(m, "_Database").def(py::init<std::string>())
        .def("insert", &Database::insert, py::arg("key"), py::arg("value"), py::arg("text") = "")
        .def("get", &Database::fetch).def("update", &Database::update).def("delete", &Database::erase)
        .def("size", &Database::size).def("checkpoint", &Database::checkpoint).def("close", &Database::close)
        .def("begin", &Database::begin).def("commit", &Database::commit).def("rollback", &Database::rollback);
}
