#!/usr/bin/env python3
"""Exercise the actual terminal-mode function with ordered video-call stubs."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
source = (root / "menu.cpp").read_text()
start = source.index("bool menu_degauss_terminal_mode(")
end = source.index("\n}", start) + 2
function = source[start:end]
fixture = r"""
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
static char last_error[256] = {};
bool menu_degauss_terminal_mode(bool frontend, char *error = last_error, size_t error_size = sizeof(last_error));
static bool degauss_running = true;
static bool menu_core = true;
static int vt = 2;
constexpr int MENU_SCRIPTS_FB2 = 1;
static int menustate = MENU_SCRIPTS_FB2;
static std::vector<int> calls;
static bool activate_ok = true, framebuffer_ok = true;
static bool native_selection = false;
static bool preset_ok = true, mask_ok = true;
static bool is_menu() { return menu_core; }
static int video_chvt(int n) { if (n) { calls.push_back(2); if (!activate_ok) return -1; vt = n; } return vt; }
static bool video_get_degauss_native_fb() { return native_selection; }
static void video_set_degauss_native_fb(bool enabled) { native_selection = enabled; calls.push_back(enabled ? 1 : 0); }
static bool video_set_degauss_preset(const char *name, char *error, size_t size) { assert(!name); calls.push_back(6); if (!preset_ok) snprintf(error, size, "preset reset failed"); return preset_ok; }
static bool video_set_degauss_display_mask(const char *name) { assert(!name); calls.push_back(7); return mask_ok; }
static bool video_fb_enable(int n) { assert(n == 1); calls.push_back(3); return framebuffer_ok; }
static void vga_nag(bool warning) { calls.push_back(warning ? 4 : 5); }
""" + function + r"""
int main() {
    assert(menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{6, 7, 0, 2, 3, 4}));
    calls.clear();
    assert(menu_degauss_terminal_mode(true));
    assert((calls == std::vector<int>{1, 2, 3, 5}));
    calls.clear();
    activate_ok = false;
    assert(!menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{6, 7, 0, 2, 1}));
    assert(native_selection);
    assert(strstr(last_error, "Terminal activation"));
    calls.clear(); activate_ok = true; framebuffer_ok = false;
    assert(!menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{6, 7, 0, 2, 3, 1}));
    assert(native_selection);
    assert(strstr(last_error, "Framebuffer configuration"));
    calls.clear(); framebuffer_ok = true;
    preset_ok = false;
    assert(!menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{6}));
    assert(strstr(last_error, "preset reset failed"));
    calls.clear(); preset_ok = true; mask_ok = false;
    assert(!menu_degauss_terminal_mode(false));
    assert((calls == std::vector<int>{6, 7}));
    assert(strstr(last_error, "mask could not be cleared"));
    calls.clear(); mask_ok = true;
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

# Compile the actual command/reply branch. Its acknowledgement must wait on
# the existing ordered worker and verify the kernel geometry, not queued intent.
input_source = (root / "input.cpp").read_text()
branch = input_source.split('else if (!strncmp(cmd, "fb_degauss ", 11))', 1)[1]
branch = branch.split('else if (!strncmp(cmd, "fb_preset ", 10))', 1)[0]
ack_fixture = r"""
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <functional>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include <fcntl.h>
#include <unistd.h>
#define FBIOGET_VSCREENINFO 0x4600
struct fb_var_screeninfo { unsigned xres, yres, bits_per_pixel; };
static fb_var_screeninfo live_geometry = {352, 240, 32};
static std::vector<std::function<void()>> jobs;
static bool apply_ok = true, prepare_geometry = true, fail_open = false, fail_ioctl = false;
static int framebuffer_reads = 0;
static void offload_add_work(std::function<void()> work) { jobs.push_back(work); }
static bool menu_degauss_terminal_mode(bool, char *error, size_t size) {
    if (!apply_ok) { snprintf(error, size, "terminal ownership refused"); return false; }
    if (prepare_geometry) offload_add_work([] { live_geometry = {800, 600, 32}; });
    return true;
}
static void video_get_degauss_terminal_size(int &width, int &height) { width = 800; height = 600; }
static int test_open(const char *path, int flags, mode_t mode = 0) {
    if (!strcmp(path, "/dev/fb0")) {
        ++framebuffer_reads;
        if (fail_open) { errno = EACCES; return -1; }
        return 9876;
    }
    return ::open(path, flags, mode);
}
static int test_close(int fd) { return fd == 9876 ? 0 : ::close(fd); }
static int test_ioctl(int fd, unsigned long command, fb_var_screeninfo *info) {
    assert(fd == 9876 && command == FBIOGET_VSCREENINFO);
    if (fail_ioctl) { errno = EIO; return -1; }
    *info = live_geometry;
    return 0;
}
#define open test_open
#define close test_close
#define ioctl test_ioctl
static void receive(char *cmd) {
    if (!strncmp(cmd, "fb_degauss ", 11))
""" + branch + r"""
}
#undef open
#undef close
#undef ioctl
static std::string reply_path;
static void run_one() { auto job = jobs.front(); jobs.erase(jobs.begin()); job(); }
static std::string read_reply() {
    std::ifstream stream(reply_path);
    assert(stream.good());
    std::string text((std::istreambuf_iterator<char>(stream)), std::istreambuf_iterator<char>());
    assert(!unlink(reply_path.c_str()));
    assert(access((reply_path + ".part").c_str(), F_OK));
    return text;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    reply_path = std::string(argv[1]) + "/degauss-terminal-123456789.status";
    char script[] = "fb_degauss 123456789 script";
    char frontend[] = "fb_degauss 123456789 frontend";
    receive(script);
    assert(jobs.size() == 2 && access(reply_path.c_str(), F_OK));
    run_one();
    assert(jobs.size() == 1 && access(reply_path.c_str(), F_OK));
    run_one();
    assert(read_reply() == "ok\n");
    receive(frontend);
    while (!jobs.empty()) run_one();
    assert(read_reply() == "ok\n");
    prepare_geometry = false;
    live_geometry = {100, 100, 32};
    receive(script); run_one();
    assert(read_reply().find("error Framebuffer is 100x100x32, expected 800x600x32") == 0);
    live_geometry = {800, 600, 16};
    receive(frontend); run_one();
    assert(read_reply().find("error Framebuffer is 800x600x16") == 0);
    fail_open = true;
    receive(script); run_one();
    assert(read_reply().find("error Reading framebuffer geometry failed:") == 0);
    fail_open = false; fail_ioctl = true;
    receive(script); run_one();
    assert(read_reply().find("error Reading framebuffer geometry failed:") == 0);
    fail_ioctl = false; apply_ok = false;
    const int reads = framebuffer_reads;
    receive(script); run_one();
    assert(read_reply() == "error terminal ownership refused\n");
    assert(framebuffer_reads == reads);
    char bad[] = "fb_degauss 3 script";
    receive(bad);
    char joined[] = "fb_mask off\nfb_degauss 123456789 script";
    receive(joined);
    assert(jobs.empty() && access(reply_path.c_str(), F_OK));
}
"""
with tempfile.TemporaryDirectory(prefix="dt-ack-") as directory:
    source_path = Path(directory) / "test.cpp"
    binary = Path(directory) / "test"
    fixture = ack_fixture.replace('"/tmp/degauss-terminal-', '"' + directory + '/degauss-terminal-')
    source_path.write_text(fixture)
    subprocess.run([os.environ.get("CXX", "c++"), "-std=c++14", "-Wall", "-Wextra",
                    "-Werror", str(source_path), "-o", str(binary)], check=True)
    subprocess.run([str(binary), directory], check=True)
