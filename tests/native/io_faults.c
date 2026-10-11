/* Test-only syscall interposition. Never linked into the package. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <dlfcn.h>

#ifndef __APPLE__
static void *original(const char *name) {
    void *fn = dlsym(RTLD_NEXT, name);
    if (!fn) _exit(88);
    return fn;
}
#endif
static ssize_t base_write(int fd, const void *bytes, size_t length) {
#ifdef __APPLE__
    return write(fd, bytes, length); /* own-image references are not interposed */
#else
    ssize_t (*fn)(int, const void *, size_t) = original("write");
    return fn(fd, bytes, length);
#endif
}
static int fd_path(int fd, char *out) {
#ifdef __APPLE__
    return fcntl(fd, F_GETPATH, out) == 0;
#else
    char link[64];
    snprintf(link, sizeof link, "/proc/self/fd/%d", fd);
    ssize_t n = readlink(link, out, 4095);
    if (n < 0) return 0;
    out[n] = 0;
    return 1;
#endif
}
static int active(const char *path, const char *call) {
    const char *target = getenv("REFPOT_FAULT_PATH");
    const char *want = getenv("REFPOT_FAULT_CALL");
    if (!target || !want || strcmp(want, call) || strcmp(path, target)) return 0;
    const char *sentinel = getenv("REFPOT_FAULT_SENTINEL");
    if (sentinel) {
        int fd = open(sentinel, O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (fd >= 0) {
            base_write(fd, call, strlen(call));
            base_write(fd, "\n", 1);
            close(fd);
        }
    }
    return 1;
}
static int fault_fsync(int fd) {
    char path[4096];
    if (fd_path(fd, path) && active(path, "fsync")) { errno = EIO; return -1; }
    #ifdef __APPLE__
    return fsync(fd);
#else
    int (*fn)(int) = original("fsync");
    return fn(fd);
#endif
}
static int fault_ftruncate(int fd, off_t length) {
    char path[4096];
    if (fd_path(fd, path) && active(path, "ftruncate")) { errno = EIO; return -1; }
    #ifdef __APPLE__
    return ftruncate(fd, length);
#else
    int (*fn)(int, off_t) = original("ftruncate");
    return fn(fd, length);
#endif
}
static ssize_t fault_write(int fd, const void *bytes, size_t length) {
    char path[4096];
    if (fd_path(fd, path) && active(path, "write")) { errno = EIO; return -1; }
    return base_write(fd, bytes, length);
}
static int fault_rename(const char *from, const char *to) {
    if (active(from, "rename")) { errno = EIO; return -1; }
    #ifdef __APPLE__
    return rename(from, to);
#else
    int (*fn)(const char *, const char *) = original("rename");
    return fn(from, to);
#endif
}
#ifdef __APPLE__
#define INTERPOSE(replacement_fn, original_fn) \
    __attribute__((used)) static struct { const void *replacement; const void *replacee; } \
    interpose_##original_fn __attribute__((section("__DATA,__interpose"))) = \
    { (const void *)(uintptr_t)&replacement_fn, (const void *)(uintptr_t)&original_fn }
INTERPOSE(fault_fsync, fsync);
INTERPOSE(fault_ftruncate, ftruncate);
INTERPOSE(fault_write, write);
INTERPOSE(fault_rename, rename);
#else
int fsync(int fd) { return fault_fsync(fd); }
int ftruncate(int fd, off_t length) { return fault_ftruncate(fd, length); }
/* The build backend enables large-file symbols on Linux. */
int ftruncate64(int fd, off64_t length) {
    char path[4096];
    if (fd_path(fd, path) && active(path, "ftruncate")) { errno = EIO; return -1; }
    int (*fn)(int, off64_t) = original("ftruncate64");
    return fn(fd, length);
}
ssize_t write(int fd, const void *bytes, size_t length) { return fault_write(fd, bytes, length); }
int rename(const char *from, const char *to) { return fault_rename(from, to); }
#endif
