#!/usr/bin/env python3
"""Check actual-direct framebuffer warnings and optional Sun ID PROM reads."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def function(source, signature):
    start = source.index(signature)
    return source[start:source.index("\n}\n", start) + 3]

common = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
'''
menu = common + r'''
struct { int fb_terminal, vga_scaler, direct_video; } cfg;
static bool framebuffer, direct;
static int warnings;
enum { OSD_VGA, OSD_HDMI, OSD_ALL, OSD_MSG };
static bool video_fb_state() { return framebuffer; }
static bool video_is_direct() { return direct; }
static void EnableOsd_on(int) {}
static void OsdSetSize(int) {}
static void OsdSetTitle(const char *) {}
static void OsdWrite(int, const char * = nullptr) {}
static int OsdGetSize() { return 16; }
static void OsdUpdate() {}
static void OsdEnable(int) { ++warnings; }
static void OsdDisable() {}
'''
menu += function((ROOT / "menu.cpp").read_text(), "static void vga_nag(")
menu += r'''
int main() {
    for (bool show : {false, true}) for (bool fb : {false, true})
    for (int terminal = 0; terminal < 3; ++terminal) for (int scaler = 0; scaler < 2; ++scaler)
    for (int requested = 0; requested < 3; ++requested) for (bool active : {false, true}) {
        framebuffer = fb; direct = active; cfg = {terminal, scaler, requested}; warnings = 0;
        vga_nag(show);
        assert(warnings == (show && fb && !(terminal == 2 && !scaler && !active)));
    }
}
'''
idprom = common + r'''
#include <string>
static std::string root, path;
static unsigned reads, downloads;
static bool ethernet;
static uint8_t sent[32];
static int FileLoad(const char *name, void *buffer, int size) {
    ++reads; assert(buffer && size == 32); // One real read, not an unchecked metadata/read pair.
    FILE *f = fopen(name, "rb"); if (!f) return 0;
    int n = fread(buffer, 1, size, f); fclose(f); return n;
}
static int ethernet_read_iface_mac(const char *, uint8_t *out) {
    if (!ethernet) return 0;
    const uint8_t address[] = {2, 3, 4, 5, 6, 7}; memcpy(out, address, sizeof(address)); return 1;
}
static uint8_t sun_idprom_machine() { return 0x17; }
static const char *HomeDir() { return root.c_str(); }
static char *user_io_make_filepath(const char *, const char *) { return const_cast<char *>(path.c_str()); }
static void user_io_set_index(int index) { assert(index == 64); }
static void user_io_set_download(int) {}
static void user_io_file_tx_data(const uint8_t *data, int size) { assert(size == 32); memcpy(sent, data, size); ++downloads; }
'''
source = (ROOT / "support/sun/sun_idprom.cpp").read_text()
idprom += "#define IDPROM_INDEX 64\n" + function(source, "static int make_idprom(") + function(source, "void sun_idprom_send(")
idprom += r'''
int main(int argc, char **argv) {
    assert(argc == 2); root = argv[1]; path = root + "/boot1.rom";
    for (int size : {0, 8, 16, 20, 32, 64}) for (bool host : {false, true}) {
        uint8_t contents[64]; for (unsigned i = 0; i < sizeof(contents); ++i) contents[i] = i + 1;
        FILE *f = fopen(path.c_str(), "wb"); assert(f); assert(fwrite(contents, 1, size, f) == (unsigned)size); fclose(f);
        reads = downloads = 0; ethernet = host; memset(sent, 0, sizeof(sent)); sun_idprom_send();
        assert(reads == 1 && downloads == (size >= 16 || host));
        if (size >= 16) for (int i = 0; i < 32; ++i) assert(sent[i] == (i < size ? contents[i] : 0xff));
        else if (host) {
            uint8_t checksum = 0; for (int i = 0; i < 16; ++i) checksum ^= sent[i];
            assert(!checksum && sent[0] == 1 && sent[1] == 0x17);
            for (int i = 16; i < 32; ++i) assert(sent[i] == 0xff);
        }
    }
    assert(!remove(path.c_str())); reads = downloads = 0; ethernet = true;
    sun_idprom_send(); assert(reads == 1 && downloads == 1);
    reads = downloads = 0; ethernet = false; sun_idprom_send(); assert(reads == 1 && downloads == 0);
}
'''
for name, production in (("vga-warning", menu), ("sun-idprom", idprom)):
    with tempfile.TemporaryDirectory(prefix="degauss-" + name + "-") as temporary:
        folder = Path(temporary); unit, binary = folder / "test.cpp", folder / "test"
        unit.write_text(production)
        subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", "-include", "initializer_list", str(unit), "-o", str(binary)], check=True)
        subprocess.run([str(binary), *([str(folder)] if name == "sun-idprom" else [])], check=True)
        print(name + ": production behaviour and compatibility passed")
