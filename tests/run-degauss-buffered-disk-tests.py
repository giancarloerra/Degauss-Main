#!/usr/bin/env python3
"""Check buffered image writes against real files and kernel write failures."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
dependencies = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <signal.h>
#define stat64 stat
#define fstat64 fstat
#define pwrite64 pwrite
#define SUN_DISK_SLOTS 2
#define UIO_BUFFER_SIZE 16384
#define UIO_SECTOR_WR 0x18
struct fileTYPE { FILE *filp; int type, mode; int64_t size; char path[1024]; };
static unsigned long now = 1;
static unsigned writes, transfers;
static unsigned notices, transitions;
static uint8_t incoming[UIO_BUFFER_SIZE];
static unsigned long GetTimer(unsigned long delay) { return now + delay; }
static bool CheckTimer(unsigned long deadline) { return now >= deadline; }
static void diskled_on() {}
static int FileSeek(fileTYPE *f, uint64_t off, int origin) { return !fseeko(f->filp, off, origin); }
static int FileWriteAdv(fileTYPE *f, void *bytes, int len) {
    ++writes; int n = fwrite(bytes, 1, len, f->filp);
    return n == len && !fflush(f->filp) ? n : 0;
}
static bool is_mac_scsi_family() { return true; }
static int sun_buffered_disks() { return 2; }
static void EnableIO() {}
static void DisableIO() {}
static void spi_w(unsigned) { ++transfers; }
static void spi_block_read(void *out, int, int size) { memcpy(out, incoming, size); }
static int user_io_get_width() { return 1; }
static void user_io_bufferinvalidate(int) {}
static void Info(const char *, int) { ++notices; }
static void create(const char *path, int value) {
    FILE *f = fopen(path, "wb"); assert(f);
    uint8_t data[32768]; memset(data, value, sizeof(data));
    assert(fwrite(data, 1, sizeof(data), f) == sizeof(data)); assert(!fclose(f));
}
static void mount(fileTYPE *f, const char *path) {
    int fd = open(path, O_RDWR | O_SYNC); assert(fd >= 0);
    f->filp = fdopen(fd, "r+b"); assert(f->filp);
    assert(!setvbuf(f->filp, nullptr, _IONBF, 0));
    f->mode = O_RDWR | O_SYNC; f->size = 32768;
    snprintf(f->path, sizeof(f->path), "%s", path);
}
static void expect(const char *path, int offset, int value) {
    FILE *f = fopen(path, "rb"); assert(f); assert(!fseek(f, offset, SEEK_SET));
    for (int i = 0; i < 512; ++i) assert(fgetc(f) == value);
    assert(!fclose(f));
}
'''
checks = r'''
int main(int argc, char **argv) {
    assert(argc == 3);
    const char *mode = argv[1], *path = argv[2];
    create(path, 0);
    fileTYPE image = {}; mount(&image, path);
    uint8_t payload[512]; memset(payload, 0x5a, sizeof(payload));
    rlimit original; assert(!getrlimit(RLIMIT_FSIZE, &original));
    signal(SIGXFSZ, SIG_IGN);
    if (!strcmp(mode, "healthy")) {
        for (int block = 0; block < 64; ++block) {
            assert(can_buffer(0, &image, block * 512, sizeof(payload)) == 1);
            stage(0, block * 512, payload, sizeof(payload));
        }
        assert(pending == 1 && writes == 0);
        FAMILY_disk_flush(0);
        assert(pending == 0 && writes == 1); // Healthy contiguous writes remain coalesced.
        for (int block = 0; block < 64; ++block) expect(path, block * 512, 0x5a);
    } else if (!strcmp(mode, "replaced")) {
        assert(can_buffer(0, &image, 512, sizeof(payload)) == 1);
        stage(0, 512, payload, sizeof(payload));
        assert(!fclose(image.filp)); image.filp = nullptr;
        char moved[1100], replacement[1100];
        snprintf(moved, sizeof(moved), "%s.moved", path);
        snprintf(replacement, sizeof(replacement), "%s.replacement", path);
        assert(!rename(path, moved)); create(path, 0xa7);
        FAMILY_disk_flush(0);
        expect(path, 512, 0xa7); // Never redirect old accepted bytes into a replaced pathname.
        assert(pending == 1 && slots[0].pending == 1 && slots[0].runs[0].len == 512);
        assert(!rename(path, replacement)); assert(!rename(moved, path));
        now += 2000; FAMILY_disk_flush(0);
        assert(!pending); expect(path, 512, 0x5a); expect(replacement, 512, 0xa7);
    } else if (!strcmp(mode, "lifecycle")) {
        assert(can_buffer(0, &image, 512, sizeof(payload)) == 1);
        stage(0, 512, payload, sizeof(payload));
        rlimit limited = original; limited.rlim_cur = 128;
        assert(!setrlimit(RLIMIT_FSIZE, &limited));
        assert(!guarded_mount(0)); assert(guarded_core_load() == -1);
        guarded_init(); guarded_restart();
        assert(pending == 1 && notices == 4 && transitions == 0 && image.filp);
        assert(!setrlimit(RLIMIT_FSIZE, &original)); now += 2000;
        assert(guarded_mount(0)); assert(guarded_core_load() == 1);
        guarded_init(); guarded_restart();
        assert(!pending && transitions == 4); expect(path, 512, 0x5a);
        // A pre-close flush still owns the original file after its name changes.
        memset(payload, 0x6b, sizeof(payload));
        assert(can_buffer(0, &image, 1024, sizeof(payload)) == 1);
        stage(0, 1024, payload, sizeof(payload));
        char moved[1100]; snprintf(moved, sizeof(moved), "%s.moved", path);
        assert(!rename(path, moved)); create(path, 0xa7);
        assert(guarded_mount(0)); assert(!fclose(image.filp)); image.filp = nullptr;
        expect(moved, 1024, 0x6b); expect(path, 1024, 0xa7);
    } else {
        const bool full = !strcmp(mode, "full");
        for (int run = 0; run < (full ? RUNS : 1); ++run) {
            assert(can_buffer(0, &image, run * 2048, sizeof(payload)) == 1);
            stage(0, run * 2048, payload, sizeof(payload));
        }
        rlimit limited = original; limited.rlim_cur = 128;
        assert(!setrlimit(RLIMIT_FSIZE, &limited));
        if (full) {
            memset(incoming, 0x6b, sizeof(incoming));
            FAMILY_disk_service(0, &image, 2, 32, 512, 0x100);
            assert(!transfers && pending == RUNS); // No ACK or overwrite while the queue cannot drain.
        } else if (!strcmp(mode, "read")) {
            assert(FAMILY_disk_service(0, &image, 1, 0, 512, 0x100) == 1);
            assert(!transfers && pending == 1); // Do not serve stale disk bytes after failed writeback.
        } else {
            FAMILY_disk_flush(0);
            assert(pending == 1 && slots[0].pending == 1 && slots[0].runs[0].len == 512);
        }
        unsigned attempted = writes;
        assert(!setrlimit(RLIMIT_FSIZE, &original));
        FAMILY_disk_poll();
        assert(writes == attempted && pending); // Retry delay does not spin on the error.
        now += 2000;
        if (full) {
            FAMILY_disk_service(0, &image, 2, 32, 512, 0x100);
            assert(transfers == 1 && pending == RUNS);
            FAMILY_disk_flush(0); expect(path, 16384, 0x6b);
        } else if (!strcmp(mode, "read")) {
            assert(FAMILY_disk_service(0, &image, 1, 0, 512, 0x100) == 0);
        } else FAMILY_disk_flush(0);
        assert(!pending); expect(path, 0, 0x5a);
    }
    if (image.filp) assert(!fclose(image.filp));
    for (int disk = 0; disk < SLOTS; ++disk) free(slots[disk].runs);
    assert(!setrlimit(RLIMIT_FSIZE, &original));
}
'''

failed = []
user_io = (ROOT / "user_io.cpp").read_text()
fpga_io = (ROOT / "fpga_io.cpp").read_text()

def body_prefix(source, signature, first_mutation):
    start = source.index(signature)
    return source[source.index("{", start) + 1:source.index(first_mutation, start)]

flush_start = user_io.index("int user_io_flush_images(")
flush_images = user_io[flush_start:user_io.index("\n}\n", flush_start) + 3]
for family in ("mac", "sun"):
    source = (ROOT / f"support/{family}/{family}_disk.cpp").read_text()
    production = source[source.index("#define BLKSZ"):]
    other = "sun" if family == "mac" else "mac"
    lifecycle = f"\nstatic int {other}_disk_flush(int) {{ return 1; }}\nfileTYPE sd_image[16] = {{}};\n" + flush_images
    lifecycle += "\nstatic int guarded_mount(unsigned char index) {" + body_prefix(user_io, "int user_io_file_mount(", "\n\tint writable") + "\n++transitions; return 1; }\n"
    lifecycle += "static int guarded_core_load() {" + body_prefix(fpga_io, "int fpga_load_rbf(", "\n\tOsdDisable") + "\n++transitions; return 1; }\n"
    lifecycle += "static void guarded_init() {" + body_prefix(user_io, "void user_io_init(", "\n\tchar *name") + "\n++transitions; }\n"
    lifecycle += "static void guarded_restart() {" + body_prefix(fpga_io, "void app_restart(", "\n\tsync()") + "\n++transitions; }\n"
    with tempfile.TemporaryDirectory(prefix=f"degauss-{family}-writeback-") as temporary:
        folder = Path(temporary)
        unit, binary = folder / "test.cpp", folder / "test"
        unit.write_text(dependencies + production + lifecycle + checks.replace("FAMILY", family))
        subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
        for mode in ("healthy", "failure", "replaced", "full", "read", "lifecycle"):
            result = subprocess.run([str(binary), mode, str(folder / f"{mode}.img")], capture_output=True, text=True, timeout=10)
            if result.returncode:
                failed.append(f"{family}:{mode}")
                print(f"{family}:{mode}: failed\n{result.stderr[-2000:]}")
            else:
                print(f"{family}:{mode}: real-file compatibility and recovery passed")
if failed:
    raise SystemExit("Buffered disk checks failed: " + ", ".join(failed))
