#!/usr/bin/env python3
"""Exercise native MGL dispatch without changing the existing OSD loaders."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
menu = (ROOT / "menu.cpp").read_text()
start = menu.index("static bool LoadLegacyMgl(mgl_struct *mgl)")
production = menu[start:menu.index("\n}\n", start) + 3]
assert "if (mgl->state == 1) LoadLegacyMgl(mgl);" in menu
user_io = (ROOT / "user_io.cpp").read_text()
assert "if (!mgl_get()->count || is_menu())" in user_io

dependencies = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
#include "support/arcade/mra_loader.h"

static int core, selected_index, tape_error;
static bool available = true;
static std::string operation, loaded_path, error;
static const int CORE_TYPE_SHARPMZ = 3;
static bool is_st() { return core == 1; }
static bool is_archie() { return core == 2; }
static int user_io_core_type() { return core; }
static const char *HomeDir() { return "/media/fat/games/Test"; }
static bool FileExists(const char *) { return available; }
static void record(const char *op, const char *path, int index) {
    operation = op; loaded_path = path; selected_index = index;
}
static void tos_insert_disk(int i, const char *p) { record("st-disk", p, i); }
static bool tos_disk_is_inserted(int) { return available; }
static void tos_load_cartridge(const char *p) {
    if (p) record("st-cartridge", p, 0);
    else operation += "-sent";
}
static int user_io_file_mount(const char *p, int i) {
    record("archie-floppy", p, i); return available;
}
static void archie_hdd_mount(char *p, int i) { record("archie-hdd", p, i); }
static const char *archie_get_hdd_name(int) { return available ? "Disk.hdf" : NULL; }
static short sharpmz_read_tape_header(const char *p) {
    record("sharp-header", p, 1); return tape_error;
}
static short sharpmz_load_tape_to_ram(const char *p, unsigned char i) {
    record("sharp-ram", p, i); return tape_error;
}
static void sharpmz_push_filename(char *p) { record("sharp-queue", p, 1); }
static void Info(const char *message, int) { error = message; }
'''

checks = r'''
static mgl_struct request(int family, char type, int index, const char *path) {
    core = family; operation.clear(); error.clear(); loaded_path.clear();
    mgl_struct mgl = {}; mgl.count = 1; mgl.state = 1;
    mgl.item[0].type = type; mgl.item[0].index = index;
    std::snprintf(mgl.item[0].path, sizeof(mgl.item[0].path), "%s", path);
    return mgl;
}
static void loaded(int family, char type, int index, const char *op, int slot) {
    auto mgl = request(family, type, index, "/media/usb0/games/Test/Game.img");
    assert(LoadLegacyMgl(&mgl));
    assert(mgl.state == 3 && !mgl.done && error.empty());
    assert(operation == op && selected_index == slot);
    assert(loaded_path == "/media/usb0/games/Test/Game.img");
}
int main() {
    // Reuse the OSD's floppy and hard-disk slots, including secondary slots.
    for (int i = 0; i < 4; i++) loaded(1, 'S', i, "st-disk", i);
    loaded(1, 'F', 0, "st-cartridge-sent", 0);
    for (int i = 0; i < 2; i++) loaded(2, 'S', i, "archie-floppy", i);
    for (int i = 2; i < 4; i++) loaded(2, 'S', i, "archie-hdd", i - 2);
    loaded(3, 'F', 2, "sharp-ram", 0);
    loaded(3, 'F', 1, "sharp-queue", 1);
    auto relative = request(1, 'S', 0, "Game.st");
    assert(LoadLegacyMgl(&relative));
    assert(loaded_path == "/media/fat/games/Test/Game.st");
    // Generic cores retain their existing CONF_STR dispatch and reset handling.
    auto generic = request(8, 'F', 0, "Game.rom");
    assert(!LoadLegacyMgl(&generic));
    assert(generic.state == 1 && !generic.done && operation.empty());
    // Native errors stop the sequence and display the failed layer.
    available = false;
    for (int family = 1; family <= 2; family++) {
        auto failed = request(family, 'S', 0, "missing.img");
        assert(LoadLegacyMgl(&failed));
        assert(failed.done && !error.empty());
    }
    available = true;
    for (int fail = 1; fail <= 4; fail++) {
        tape_error = fail;
        auto failed = request(3, 'F', 1, "bad.mzf");
        assert(LoadLegacyMgl(&failed));
        assert(failed.done && !error.empty() && operation == "sharp-header");
    }
    tape_error = 0;
    auto invalid = request(1, 'S', 4, "Disk.vhd");
    assert(LoadLegacyMgl(&invalid));
    assert(invalid.done && error == "Unsupported file type or slot");
    auto invalid_tape_slot = request(3, 'F', 0, "Tape.mzf");
    assert(LoadLegacyMgl(&invalid_tape_slot));
    assert(invalid_tape_slot.done && error == "Unsupported file type or slot");
}
'''

with tempfile.TemporaryDirectory() as task_dir:
    source = Path(task_dir) / "legacy-mgl.cpp"
    binary = Path(task_dir) / "legacy-mgl"
    source.write_text(dependencies + production + checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("Native MGL dispatch checks passed")
