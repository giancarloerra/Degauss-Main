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
static bool activate_ok = true, framebuffer_ok = true;
static bool is_menu() { return menu_core; }
static int video_chvt(int n) { if (n) { calls.push_back(2); if (!activate_ok) return -1; vt = n; } return vt; }
static void video_set_degauss_native_fb(bool enabled) { calls.push_back(enabled ? 1 : 0); }
static bool video_fb_enable(int n) { assert(n == 1); calls.push_back(3); return framebuffer_ok; }
static void vga_nag(bool warning) { calls.push_back(warning ? 4 : 5); }
""" + function + r"""
int main() {
    assert(menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{0, 2, 3, 4}));
    calls.clear();
    assert(menu_degauss_terminal_mode(true));
    assert((calls == std::vector<int>{1, 2, 3, 5}));
    calls.clear();
    activate_ok = false;
    assert(!menu_degauss_terminal_mode(true));
    assert((calls == std::vector<int>{1, 2}));
    calls.clear(); activate_ok = true; framebuffer_ok = false;
    assert(!menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{0, 2, 3}));
    calls.clear(); framebuffer_ok = true;
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

# Exercise the production VT activation separately: failed opens/ioctls must
# neither claim success nor advance the remembered terminal.
video = (root / "video.cpp").read_text()
start = video.index("int video_chvt(int num)")
end = video.index("\n}", start) + 2
vt_fixture = r"""
#include <cassert>
#include <cstdio>
#define O_RDONLY 0
#define O_CLOEXEC 0
#define VT_ACTIVATE 1
#define VT_WAITACTIVE 2
static bool fail_open = false;
static int fail_request = 0, closed = 0;
static int mock_open(const char*, int) { return fail_open ? -1 : 8; }
static int mock_ioctl(int fd, int request, int) { assert(fd == 8); return request == fail_request ? -1 : 0; }
static int mock_close(int fd) { assert(fd == 8); ++closed; return 0; }
#define open mock_open
#define ioctl mock_ioctl
#define close mock_close
""" + video[start:end] + r"""
int main() {
    assert(video_chvt(0) == 1);
    fail_open = true;
    assert(video_chvt(2) == -1 && video_chvt(0) == 1 && closed == 0);
    fail_open = false; fail_request = VT_ACTIVATE;
    assert(video_chvt(2) == -1 && video_chvt(0) == 1 && closed == 1);
    fail_request = VT_WAITACTIVE;
    assert(video_chvt(2) == -1 && video_chvt(0) == 1 && closed == 2);
    fail_request = 0;
    assert(video_chvt(2) == 2 && video_chvt(0) == 2 && closed == 3);
    assert(video_chvt(1) == 1 && video_chvt(0) == 1 && closed == 4);
}
"""
with tempfile.TemporaryDirectory(prefix="degauss-vt-activation-test-") as directory:
    source_path = Path(directory) / "test.cpp"
    binary = Path(directory) / "test"
    source_path.write_text(vt_fixture)
    subprocess.run([os.environ.get("CXX", "c++"), "-std=c++14", "-Wall", "-Wextra",
                    "-Werror", str(source_path), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
