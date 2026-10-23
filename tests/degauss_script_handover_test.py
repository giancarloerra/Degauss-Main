#!/usr/bin/env python3
"""Exercise the actual terminal-mode function with ordered video-call stubs."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / "menu.cpp").read_text()
start = source.index("bool menu_degauss_terminal_mode(bool frontend)")
end = source.index("\n}", start) + 2
function = source[start:end]
fixture = r"""
#include <cassert>
#include <vector>
static bool degauss_running = true;
static bool menu_core = true;
static int vt = 2;
constexpr int MENU_SCRIPTS_FB2 = 1;
static int menustate = MENU_SCRIPTS_FB2;
static std::vector<int> calls;
static bool is_menu() { return menu_core; }
static int video_chvt(int n) { if (n) { vt = n; calls.push_back(2); } return vt; }
static void video_set_degauss_native_fb(bool enabled) { calls.push_back(enabled ? 1 : 0); }
static void video_fb_enable(int n) { assert(n == 1); calls.push_back(3); }
static void vga_nag(bool warning) { calls.push_back(warning ? 4 : 5); }
""" + function + r"""
int main() {
    assert(menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{0, 2, 3, 4}));
    calls.clear();
    assert(menu_degauss_terminal_mode(true));
    assert((calls == std::vector<int>{1, 2, 3, 5}));
    calls.clear();
    degauss_running = false;
    assert(!menu_degauss_terminal_mode(true));
    degauss_running = true; menu_core = false;
    assert(!menu_degauss_terminal_mode(false));
    menu_core = true; menustate = 0;
    assert(!menu_degauss_terminal_mode(true));
    menustate = MENU_SCRIPTS_FB2; vt = 1;
    assert(!menu_degauss_terminal_mode(false));
    assert(calls.empty());
}
"""
with tempfile.TemporaryDirectory(prefix="degauss-terminal-test-") as directory:
    source_path = Path(directory) / "test.cpp"
    binary = Path(directory) / "test"
    source_path.write_text(fixture)
    subprocess.run([os.environ.get("CXX", "c++"), "-std=c++14", "-Wall", "-Wextra",
                    "-Werror", str(source_path), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
