#!/usr/bin/env python3
"""Exercise SharpMZ tape admission and failed transfer cleanup."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "support/sharpmz/sharpmz.cpp").read_text()
header = (ROOT / "support/sharpmz/sharpmz.h").read_text()
file_io = (ROOT / "file_io.cpp").read_text()
assert "fileTYPE::~fileTYPE(){FileClose(this);}" in "".join(file_io.split())


def function(signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


struct_start = header.index("typedef struct", header.index("// MZ Series Tape header"))
tape_header = header[struct_start:header.index("} sharpmz_tape_header_t;", struct_start) + len("} sharpmz_tape_header_t;")]

dependencies = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#define MAX_TAPE_QUEUE 5
#define SHARPMZ_CMT_MC 1
#define SHARPMZ_MEMBANK_SYSRAM 1
#define SHARPMZ_MEMBANK_CMT_HDR 4
#define SHARPMZ_MEMBANK_CMT_DATA 5
#define SHARPMZ_FILE_ADDR_TX 0x58
#define SHARPMZ_FILE_TX 0x53
#define SHARPMZ_EOF 0
#define MZ_TAPE_HEADER_STACK_ADDR 0x10f0
#define MZ_TAPE_HEADER_SIZE 128
#define DISKLED_ON
#define DISKLED_OFF
#define sharpmz_debugf(...) ((void)0)
struct { char *queue[MAX_TAPE_QUEUE]; unsigned short elements; } tapeQueue = {};
static bool allocation_fails, selected, closed;
static int reset_count;
static unsigned char sector_buffer[512], MZBANKADDR[8] = {};
static std::vector<unsigned char> commands;
static void *test_malloc(size_t size) { return allocation_fails ? nullptr : std::malloc(size); }
#define malloc test_malloc
struct fileTYPE;
static void FileClose(fileTYPE *);
struct fileTYPE { FILE *file = nullptr; ~fileTYPE() { FileClose(this); } };
static bool FileOpen(fileTYPE *file, const char *path) {
    closed = false; file->file = std::fopen(path, "rb"); return file->file;
}
static void FileClose(fileTYPE *file) {
    if (file->file) { std::fclose(file->file); file->file = nullptr; closed = true; }
}
static unsigned int sharpmz_file_read(fileTYPE *file, void *data, size_t size) {
    return std::fread(data, 1, size, file->file);
}
static unsigned long GetTimer(unsigned long) { return 0; }
static void sharpmz_reset(int, int) { ++reset_count; }
static void EnableFpga() { selected = true; }
static void DisableFpga() { selected = false; }
static void spi8(unsigned char command) { assert(selected); commands.push_back(command); }
static void spi_write(unsigned char *, size_t, int) { assert(selected); }
'''

checks = r'''
static void tape(const char *path, int declared, int actual) {
    sharpmz_tape_header_t header = {}; header.dataType = SHARPMZ_CMT_MC; header.fileSize = declared;
    auto file = std::fopen(path, "wb"); assert(file);
    assert(std::fwrite(&header, 1, 128, file) == 128);
    for (int i = 0; i < actual; ++i) std::fputc(0x55, file);
    std::fclose(file);
}
int main(int argc, char **argv) {
    assert(argc == 2 && sizeof(sharpmz_tape_header_t) == 128);
    char name[] = "Tape.mzf";
    allocation_fails = true;
    assert(!sharpmz_push_filename(name) && tapeQueue.elements == 0);
    allocation_fails = false;
    for (int i = 0; i < MAX_TAPE_QUEUE; ++i) {
        assert(sharpmz_push_filename(name));
        assert(tapeQueue.elements == i + 1 && !std::strcmp(tapeQueue.queue[i], name));
    }
    assert(!sharpmz_push_filename(name) && tapeQueue.elements == MAX_TAPE_QUEUE);
    for (auto item : tapeQueue.queue) std::free(item);
    // A missing body must fail, end the transfer and release the FPGA bus.
    tape(argv[1], 512, 0);
    assert(sharpmz_load_tape_to_ram(argv[1], 0) == 4);
    assert(!selected && closed && reset_count == 1);
    assert(commands[commands.size() - 2] == SHARPMZ_FILE_TX);
    assert(commands.back() == SHARPMZ_EOF);
    // Early header failure also closes the file through fileTYPE's destructor.
    auto short_file = std::fopen(argv[1], "wb"); assert(short_file);
    std::fputc(1, short_file); std::fclose(short_file);
    assert(sharpmz_load_tape_to_ram(argv[1], 0) == 2 && closed && !selected);
    // Partial data followed by EOF has the same cleanup, never apparent success.
    commands.clear(); tape(argv[1], 512, 256);
    assert(sharpmz_load_tape_to_ram(argv[1], 0) == 4 && !selected && closed);
    // The existing healthy transfer still completes and writes the header.
    commands.clear(); tape(argv[1], 512, 512);
    assert(sharpmz_load_tape_to_ram(argv[1], 0) == 0 && !selected && closed);
}
'''

with tempfile.TemporaryDirectory() as task_dir:
    unit = Path(task_dir) / "sharpmz.cpp"
    binary = Path(task_dir) / "sharpmz"
    unit.write_text(dependencies + tape_header + "\nstatic sharpmz_tape_header_t tapeHeader;\n"
                    + function("bool sharpmz_push_filename(char *fileName)")
                    + function("short sharpmz_load_tape_to_ram(const char *tapeFile, unsigned char dstCMT)")
                    + checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-but-set-variable", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary), str(Path(task_dir) / "Tape.mzf")], check=True)
print("SharpMZ queue and failed transfer checks passed")
