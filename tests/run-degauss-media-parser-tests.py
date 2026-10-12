#!/usr/bin/env python3
"""Exercise the production Sun CUE and Marty D88 paths against real files."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]


files = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <strings.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <string>
#include <vector>
using __off64_t = int64_t;
static int open_files;
struct fileTYPE {
    FILE *filp;
    int64_t size;
    bool opened() const { return filp != nullptr; }
};
static int FileOpenEx(fileTYPE *f, const char *path, int flags) {
    f->filp = fopen(path, (flags & O_RDWR) ? "r+b" : "rb");
    if (!f->filp) return 0;
    ++open_files;
    struct stat st; assert(!fstat(fileno(f->filp), &st)); f->size = st.st_size;
    return 1;
}
static int FileOpen(fileTYPE *f, const char *path) { return FileOpenEx(f, path, O_RDONLY); }
static int FileCanWrite(const char *path) { return !access(path, W_OK); }
static void FileClose(fileTYPE *f) {
    if (f->filp) { fclose(f->filp); f->filp = nullptr; --open_files; }
}
static int FileSeek(fileTYPE *f, int64_t offset, int origin) {
    return !fseeko(f->filp, offset, origin);
}
static int FileReadAdv(fileTYPE *f, void *data, int size) { return fread(data, 1, size, f->filp); }
static int FileLoad(const char *path, void *data, int size) {
    FILE *f = fopen(path, "rb"); if (!f) return 0;
    int read = fread(data, 1, size, f); fclose(f); return read;
}
static int FileWriteAdv(fileTYPE *f, const void *data, int size) {
    int written = fwrite(data, 1, size, f->filp); fflush(f->filp); return written;
}
static void write_file(const std::string &path, const std::vector<uint8_t> &data) {
    FILE *f = fopen(path.c_str(), "wb"); assert(f);
    assert(fwrite(data.data(), 1, data.size(), f) == data.size()); fclose(f);
}
'''

sun = (ROOT / "support/sun/sun_cdrom.cpp").read_text()
toc = (ROOT / "cd.h").read_text()
toc = toc[toc.index("typedef enum"):toc.index("} toc_t;") + len("} toc_t;")]
# Only the production TOC fields are used by this parser, not its unrelated lookup methods.
toc = toc[:toc.index("\n\tint GetTrackByLBA")] + "\n} toc_t;\n"
sun_state = sun[sun.index("struct sun_cdrom_state"):sun.index("static uint32_t layout_data_off")]
sun_code = files + '#include "support/sun/sun_cdrom.h"\nstruct chd_file {};\n' + toc + sun_state
sun_code += "\n".join(function(sun, signature) for signature in (
    "static uint32_t layout_data_off(", "static void log_toc(",
    "static int finish_mount(", "static uint32_t msf_field(", "static int mount_cue(",
))
sun_code += r'''
static void clear_disc() {
    for (int i = 0; i < cd.toc.last; ++i) FileClose(&cd.toc.tracks[i].f);
    memset(&cd, 0, sizeof(cd)); assert(open_files == 0);
}
static void cue(const std::string &path, int count, bool repeat_index) {
    FILE *f = fopen(path.c_str(), "wb"); assert(f);
    fputs("FILE \"disc.bin\" BINARY\n", f);
    for (int i = 0; i < count; ++i) {
        if (!repeat_index || i == 0) fprintf(f, "TRACK %02d MODE1/2048\n", i + 1);
        fprintf(f, "INDEX 01 00:00:%02d\n", i % 75);
    }
    fclose(f);
}
int main(int argc, char **argv) {
    assert(argc == 2); std::string dir = argv[1], path = dir + "/disc.cue";
    write_file(dir + "/disc.bin", std::vector<uint8_t>(2048 * 150, 0x5a));
    // Healthy single- and maximum-track discs still mount and close every file.
    for (int count : {1, 99}) {
        cue(path, count, false);
        assert(mount_cue(path.c_str()) == SUN_CDROM_HANDLED);
        assert(cd.toc.last == count && cd.toc.end > 0); clear_disc();
    }
    // Repeated INDEX 01 entries must not advance beyond the fixed track table.
    cue(path, 101, true);
    assert(mount_cue(path.c_str()) == SUN_CDROM_REJECT);
    assert(cd.toc.last == 0 && open_files == 0);
}
'''

marty = (ROOT / "support/marty/marty.cpp").read_text()
marty_code = files + '#include "support/marty/marty.h"\n'
marty_code += marty[marty.index("#define D88_HDR"):marty.index("static void fd_write_track(")]
marty_code += r'''
int main(int argc, char **argv) {
    assert(argc == 2); std::string path = std::string(argv[1]) + "/floppy.d88";
    // Normal N=0..3 stays unchanged; larger preserved IDs use the reader's 1024-byte clamp.
    for (int n : {0, 1, 2, 3, 4, 5, 127, 255}) {
        uint32_t size = 128u << (n > 3 ? 3 : n), first = D88_HDR, second = first + 16 + size;
        std::vector<uint8_t> image(second + 16 + 512, 0);
        wr32(image.data() + 0x1C, image.size());
        wr32(image.data() + 0x20, first); wr32(image.data() + 0x24, second);
        for (int track = 0; track < 2; ++track) {
            uint32_t off = track ? second : first, len = track ? 512 : size;
            uint8_t *h = image.data() + off;
            h[0] = track; h[2] = 1; h[3] = track ? 2 : n;
            wr16(h + 4, 1); wr16(h + 14, len);
            for (uint32_t i = 0; i < len; ++i) h[16 + i] = (i * 17 + track) & 255;
        }
        write_file(path, image);
        assert(fd_load(&fds[0], path.c_str()));
        uint8_t rec[MARTY_TRACK_REC]; fd_read_track(MARTY_SLOT_FDD, rec, 0);
        assert(rec[0] == 1 && rec[REC_TABLE + 3] == n);
        // A write at the end of the served sector must not truncate it or change the ID.
        rec[REC_DATA + size - 1] ^= 0xff; image[first + 16 + size - 1] ^= 0xff;
        d88_write_track(&fds[0], rec, 0); fd_unload(&fds[0]);
        FILE *saved = fopen(path.c_str(), "rb"); assert(saved);
        std::vector<uint8_t> actual(image.size());
        size_t got = fread(actual.data(), 1, actual.size(), saved);
        if (got != image.size() || fgetc(saved) != EOF || actual != image) {
            fprintf(stderr, "D88 write changed the sector ID, length or adjacent data (N=%d)\n", n);
            abort();
        }
        fclose(saved);
        // The changed image must survive a real reopen and the adjacent track must remain intact.
        assert(fd_load(&fds[0], path.c_str())); fd_read_track(MARTY_SLOT_FDD, rec, 0);
        assert(rec[REC_TABLE + 3] == n && rec[REC_DATA + size - 1] == image[first + 16 + size - 1]);
        fd_read_track(MARTY_SLOT_FDD, rec, 1);
        assert(rec[0] == 1 && rec[REC_TABLE + 3] == 2);
        assert(!memcmp(rec + REC_DATA, image.data() + second + 16, 512));
        fd_unload(&fds[0]); assert(open_files == 0);
    }
}
'''

marty_cue = files
marty_cue += marty[marty.index("enum { TRK_AUDIO"):marty.index("static toc_t     chd_toc;")]
marty_cue += "\n".join(function(marty, signature) for signature in (
    "static int msf_frames(", "static int cd_file_sectors(",
    "static void cd_close_track(", "static int cd_load_cue(",
))
marty_cue += r'''
static void clear() {
    for (int i = 0; i < cd_nfiles; ++i) FileClose(&cd_files[i].f);
    memset(cd_tracks, 0, sizeof(cd_tracks)); memset(cd_files, 0, sizeof(cd_files));
    cd_nfiles = cd_ntracks = 0; assert(open_files == 0);
}
int main(int argc, char **argv) {
    assert(argc == 2); std::string dir = argv[1], path = dir + "/marty.cue";
    write_file(dir + "/disc.bin", std::vector<uint8_t>(2048 * 150, 0x5a));
    for (bool malformed : {false, true}) {
        FILE *f = fopen(path.c_str(), "wb"); assert(f);
        fputs("FILE \"disc.bin\" BINARY\nTRACK 01 MODE1/2048\n", f);
        if (malformed) fputs("INDEX 01 invalid\n", f);
        fputs("INDEX 01 00:00:00\nTRACK 02 MODE1/2048\nINDEX 01 00:01:00\n", f);
        fclose(f);
        assert(cd_load_cue(path.c_str()));
        assert(cd_ntracks == 2 && cd_nfiles == 1);
        assert(cd_tracks[0].start == 150 && cd_tracks[0].end == 225);
        assert(cd_tracks[1].start == 225 && cd_tracks[1].end == 300);
        clear();
    }
}
'''

marty_chd = files + '#include <algorithm>\n#include "support/marty/marty.h"\nstruct chd_file {};\n' + toc
marty_chd += marty[marty.index("enum { TRK_AUDIO"):marty.index("#define CD_CACHE_N")]
marty_chd += r'''
static bool stored;
static chd_file image;
enum { CHDERR_NONE = 0 };
static int mister_load_chd(const char *, toc_t *table) {
    memset(table, 0, sizeof(*table));
    table->chd_f = &image; table->chd_hunksize = 4096; table->last = 2;
    table->tracks[0].start = stored ? 75 : 0;
    table->tracks[0].end = 200; table->tracks[0].indexes[1] = 75;
    table->tracks[1].start = 200 + (stored ? 75 : 0);
    table->tracks[1].end = 400; table->tracks[1].indexes[1] = 75;
    for (int i = 0; i < 2; ++i) { table->tracks[i].type = TT_MODE1; table->tracks[i].sector_size = 2048; }
    return CHDERR_NONE;
}
'''
marty_chd += function(marty, "static int cd_load_chd(")
marty_chd += r'''
int main() {
    for (bool included : {false, true}) {
        stored = included; assert(cd_load_chd("synthetic.chd"));
        // Index zero is an absolute LBA for every track, including the first.
        for (int i = 0; i < 2; ++i) {
            assert(cd_tracks[i].idx0 == cd_tracks[i].start - 75);
            assert(cd_tracks[i].gap == (stored ? 0 : 75));
        }
        assert(cd_tracks[0].idx0 == (stored ? 150 : 75));
        // Routing begins at a stored sector or an explicitly unstored pregap.
        assert(!stored || cd_tracks[0].idx0 - 150 >= 0);
        free(chd_hunkbuf); chd_hunkbuf = nullptr;
    }
}
'''

failures = []
for name, production in (("sun-cue", sun_code), ("marty-d88", marty_code), ("marty-cue", marty_cue), ("marty-chd-index", marty_chd)):
    with tempfile.TemporaryDirectory(prefix="degauss-media-") as temporary:
        task_dir = Path(temporary)
        unit, binary = task_dir / "test.cpp", task_dir / "test"
        unit.write_text(production)
        subprocess.run([
            "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
            "-Wno-unused-variable", "-fsanitize=address,undefined", "-I", str(ROOT),
            str(unit), "-o", str(binary),
        ], check=True)
        try:
            arguments = [] if name == "marty-chd-index" else [str(task_dir)]
            result = subprocess.run([str(binary), *arguments], capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            failures.append(name)
            print(f"{name}: parser did not finish within 10 seconds")
            continue
        if result.returncode:
            failures.append(name)
            print(f"{name}: failed ({result.returncode})\n{result.stderr[-6000:]}")
        else:
            print(f"{name}: real-file parser and compatibility checks passed")
if failures:
    raise SystemExit("Media parser checks failed: " + ", ".join(failures))
