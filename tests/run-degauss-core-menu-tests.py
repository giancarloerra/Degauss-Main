#!/usr/bin/env python3
"""Execute Main's core-chooser initialization with isolated host dependencies."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


menu = (ROOT / "menu.cpp").read_text()
user_io = (ROOT / "user_io.cpp").read_text()
production = "\n".join([
    function(user_io, "const char* get_rbf_dir()"),
    function(user_io, "const char* get_rbf_name()"),
    function(user_io, "const char* get_rbf_path()"),
    function(menu, "static void ResolveExistingCorePath(char *path)"),
    function(menu, "void SelectFile(const char* path,"),
])
# Standard Main has a recent-index argument; the pinned RA Main does not.
recent_argument = ", 0" if "int recent_idx)" in production else ""

dependencies = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>

static char core_path[1024] = {};
static char selPath[1024] = {};
static char filter[256] = {};
static unsigned long filter_typing_timer = 0;
static const char *home_dir = nullptr;
static char fs_pFileExt[64] = {};
int fs_ExtLen, fs_Options, fs_MenuSelect, fs_MenuCancel, fs_RecentIdx, menustate;
static bool menu_active = false;
static std::string scanned_path;
static const int SCANO_CORES = 1, SCANO_TXT = 2, SCANO_SAVES = 4,
    SCANO_NOENTER = 8, SCANO_DIR = 16, SCANF_INIT = 0, MENU_FILE_SELECT1 = 1;
static const char *PCECD_DIR = "PCECD", *NEOCD_DIR = "NEOGEOCD", *SAVE_DIR = "saves";
static const char *CoreName2 = "Test";
static const std::set<std::string> files = {
    "degauss/menu.rbf", "menu.rbf", "other/menu.rbf",
    "_Console/NES/NES_20000101.rbf", "_Arcade/_Organized/Test.mra",
    "Scripts/test.sh"
};
static const std::set<std::string> directories = {"", "Scripts", "_Console/NES"};

static const char *getRootDir() { return "/media/fat"; }
static bool is_menu() { return menu_active; }
static bool is_pce() { return false; }
static bool is_neogeo() { return false; }
static bool FileExists(const char *path) { return files.count(path) != 0; }
static bool PathIsDir(const char *path) { return directories.count(path) != 0; }
static const char *user_io_get_core_path(const char *, int) { return "games/Test"; }
static void ScanDirectory(char *path, int, const char *, int) { scanned_path = path; }
static void AdjustDirectory(char *) {}
'''

checks = r'''
static void choose(const char *core, bool menu, const char *expected,
    int options = SCANO_CORES, const char *path = "", const char *ext = "RBF")
{
    std::strcpy(core_path, core);
    menu_active = menu;
    SelectFile(path, ext, options, 2, 3/* RECENT_ARGUMENT */);
    if (scanned_path != expected) {
        std::fprintf(stderr, "Chooser for %s: expected '%s', got '%s'\n",
            core, expected, scanned_path.c_str());
        std::exit(1);
    }
}

int main()
{
    // The private Menu is infrastructure, not the user's core-browsing location.
    choose("/media/fat/degauss/menu.rbf", true, "");
    choose("/media/fat/_Console/NES/NES_20000101.rbf", false,
        "_Console/NES/NES_20000101.rbf");
    // A game return followed by another exit must also begin at the root.
    choose("/media/fat/degauss/menu.rbf", true, "");
    choose("/media/fat/degauss/menu.rbf", true, "");
    // MRA initialization uses its XML path, not its supporting Arcade RBF.
    choose("/media/fat/_Arcade/_Organized/Test.mra", false,
        "_Arcade/_Organized/Test.mra");
    // Ordinary Menu, other Menu locations and non-Menu cores retain their paths.
    choose("/media/fat/menu.rbf", true, "menu.rbf");
    choose("/media/fat/other/menu.rbf", true, "other/menu.rbf");
    choose("/media/fat/degauss/menu.rbf", false, "degauss/menu.rbf");
    choose("", true, "");
    // Missing core files still resolve to the existing parent directory.
    choose("/media/fat/_Console/NES/missing.rbf", false, "_Console/NES");
    // The correction applies only to core selection, never the Scripts picker.
    choose("/media/fat/degauss/menu.rbf", true, "Scripts/test.sh",
        SCANO_DIR, "Scripts/test.sh", "SH");
    std::puts("Core chooser regression checks passed");
}
'''
checks = checks.replace("/* RECENT_ARGUMENT */", recent_argument)

with tempfile.TemporaryDirectory(prefix="degauss-core-menu-") as temporary:
    root = Path(temporary)
    source = root / "chooser.cpp"
    binary = root / "chooser"
    source.write_text(dependencies + production + checks)
    subprocess.run([
        "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
        str(source), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
