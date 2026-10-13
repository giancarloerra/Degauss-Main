#!/usr/bin/env python3
"""Check production saves with real linked targets and existing permissions."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "file_io.cpp").read_text()
start = source.index("int FileSave(")
production = source[start:source.index("\n}\n", start) + 3]
dependencies = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <string>
static char full_path[4096];
static void make_fullpath(const char *path) {
    assert(strlen(path) < sizeof(full_path)); strcpy(full_path, path);
}
static void contents(const char *path) {
    char data[4] = {}; int fd = open(path, O_RDONLY); assert(fd >= 0);
    assert(read(fd, data, sizeof(data)) == 3 && !memcmp(data, "new", 3)); close(fd);
}
'''
checks = r'''
int main(int argc, char **argv) {
    assert(argc == 3); std::string path = std::string(argv[1]) + "/state", other = path + "-link";
    int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600); assert(fd >= 0);
    assert(write(fd, "previous state", 14) == 14); close(fd); assert(!chmod(path.c_str(), 0600));
    struct stat before = {}; assert(!stat(path.c_str(), &before));
    const char *mode = argv[2], *save = path.c_str();
    if (!strcmp(mode, "symlink")) { assert(!symlink(path.c_str(), other.c_str())); save = other.c_str(); }
    if (!strcmp(mode, "hardlink")) { assert(!link(path.c_str(), other.c_str())); save = other.c_str(); }
    assert(FileSave(save, (void *)"new", 3) == 3);
    struct stat after = {}; assert(!stat(path.c_str(), &after));
    assert((after.st_mode & 07777) == (before.st_mode & 07777));
    assert(after.st_uid == before.st_uid && after.st_gid == before.st_gid);
    contents(path.c_str());
    if (!strcmp(mode, "symlink")) {
        assert(!lstat(other.c_str(), &after) && S_ISLNK(after.st_mode)); contents(other.c_str());
    }
    if (!strcmp(mode, "hardlink")) {
        assert(!stat(other.c_str(), &after) && after.st_ino == before.st_ino); contents(other.c_str());
    }
    assert(access((std::string(save) + ".tmp").c_str(), F_OK));
    std::string missing = path + "-new"; assert(FileSave(missing.c_str(), (void *)"new", 3) == 3); contents(missing.c_str());
    std::string directory = path + "-directory"; assert(!mkdir(directory.c_str(), 0700));
    assert(!FileSave(directory.c_str(), (void *)"new", 3));
    assert(!stat(directory.c_str(), &after) && S_ISDIR(after.st_mode));
    assert(access((directory + ".tmp").c_str(), F_OK));
}
'''
failures = []
with tempfile.TemporaryDirectory(prefix="degauss-filesave-") as temporary:
    root = Path(temporary)
    unit, binary = root / "save.cpp", root / "save"
    unit.write_text(dependencies + production + checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    for case in ("regular", "symlink", "hardlink"):
        folder = root / case
        folder.mkdir()
        result = subprocess.run([str(binary), str(folder), case], capture_output=True, text=True)
        if result.returncode:
            failures.append(case)
            print(f"{case}: failed\n{result.stderr[-3000:]}")
        else:
            print(f"{case}: target, permissions, complete replacement and failure cleanup passed")
if failures:
    raise SystemExit("FileSave checks failed: " + ", ".join(failures))
