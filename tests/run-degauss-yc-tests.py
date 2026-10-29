#!/usr/bin/env python3
"""Exercise production YC selection with the distributed clock-specific table."""

import os
import shlex
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
video = (root / 'video.cpp').read_text()
config = (root / 'cfg.cpp').read_text()


def function(source, signature):
    start = source.index(signature)
    start = source.rfind('\n', 0, start) + 1
    end = source.index('\n}', source.index('{', start)) + 2
    return source[start:end]


production = function(config, 'static int yc_parse_mode(')
production += '\n' + function(video, 'static bool video_degauss_native_fb_active()\n{')
# RA Main retains its own upstream calculation; never substitute normal Main's.
for signature in ('static uint64_t div_round_u64(', 'static uint64_t calc_frame_locked_phase('):
    if signature in video:
        production += '\n' + function(video, signature)
production += '\n' + function(video, 'static bool get_scaler_yc_timing(')
production += '\n' + function(video, 'static void set_yc_mode()\n{')
production += '\n' + function(video, 'void video_set_degauss_native_fb(bool enable)')

prefix = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <strings.h>
#include <vector>
using uint = unsigned int;
// ARMv7 uses long long for int64_t; some 64-bit hosts use long instead.
using main_int64_t = long long;
static_assert(sizeof(main_int64_t) == sizeof(int64_t), "64-bit target word required");
#define int64_t main_int64_t
// Match Main's configured policy for its unchanged diagnostic formatting.
#if defined(__GNUC__) && !defined(__clang__)
#pragma GCC diagnostic ignored "-Wformat-truncation"
#endif
struct yc_mode { char key[64]; int64_t phase_inc; };
static yc_mode yc_modes[20] = {};
static struct { int vga_mode_int, vga_scaler, ntsc_mode; bool degauss_native_analog, direct_video; } cfg = {};
static struct { uint32_t width, ptime, frame_clocks, vtime, ctime; bool interlaced; }
    current_video_info = {};
static struct {
    struct { uint32_t hact, hfp, hs, hbp, vact, vfp, vs, vbp; } param;
    double Fpix;
} v_cur = {};
static bool menu_core = true, degauss_native_fb = false;
static unsigned yc_updates = 0, fb_configurations = 0;
static int vga_fb = 0;
static const char *core_name = "MENU";
static std::vector<uint16_t> words;
static bool is_menu() { return menu_core; }
static int get_vga_fb() { return vga_fb; }
static bool video_is_direct() { return cfg.direct_video; }
static void video_fb_config() { ++fb_configurations; }
static const char *user_io_get_core_name(int) { return core_name; }
constexpr int UIO_SET_YC_PAR = 0x41;
static void spi_uio_cmd_cont(int command) { assert(command == UIO_SET_YC_PAR); ++yc_updates; words.clear(); }
static void spi_uio_cmd8(int command, int value) { assert(command == UIO_SET_YC_PAR); ++yc_updates; words = {uint16_t(value)}; }
static void spi_w(uint16_t value) { words.push_back(value); }
static void DisableIO() {}
#define CHAR_IS_LINEEND(c) ((c) == '\n' || (c) == '\r')
#define CHAR_IS_SPACE(c) ((c) == ' ' || (c) == '\t')
#define ini_parser_debugf(...)
'''

checks = r'''
static void load_table(const char *path) {
    memset(yc_modes, 0, sizeof(yc_modes));
    std::ifstream input(path); assert(input.good());
    std::string line; unsigned n = 0;
    while (std::getline(input, line)) {
        if (strncasecmp(line.c_str(), core_name, strlen(core_name))) continue;
        assert(n < 20);
        std::vector<char> text(line.begin(), line.end()); text.push_back(0);
        assert(yc_parse_mode(text.data(), &yc_modes[n])); ++n;
    }
    assert(n);
}
static uint64_t phase() {
    assert(words.size() == 7);
    return uint64_t(words[1]) | (uint64_t(words[2]) << 16) | (uint64_t(words[3]) << 32);
}
static uint64_t output() { set_yc_mode(); return phase(); }
static void native_case(const char *table, int mode, bool pal, bool custom) {
    menu_core = true; core_name = "MENU"; degauss_native_fb = true;
    cfg = {mode, 0, 0, true, false}; vga_fb = 0;
    assert(video_degauss_native_fb_active());
    current_video_info = {};
    current_video_info.width = 1058;
    // A 1323-clock active interval measured by the 100 MHz counter.
    current_video_info.ctime = 1323; current_video_info.ptime = 5292;
    const unsigned htotal = custom ? 1272 : 1276;
    current_video_info.frame_clocks = htotal * (pal ? 312 : 262) * 5 / 4;
    current_video_info.vtime = current_video_info.frame_clocks * 4;
    memset(yc_modes, 0, sizeof(yc_modes));
    const uint64_t calculated = output();
    const std::vector<uint16_t> calculated_packet = words;
    const double frequency = calculated * 25000000.0 / (1ULL << 40);
    const double reference = pal ? 4433618.75 : 315000000.0 / 88.0;
    assert(std::abs(frequency - reference) < 100.0);
    load_table(table);
    assert(output() == calculated);
    assert(words == calculated_packet); // Burst timing and enable bits also stay intact.
    assert((words[0] & 1) == (mode != 4));
    assert(words[6] == (mode == 4));
    // The same legacy keys remain honoured for ordinary Menu, not deleted globally.
    degauss_native_fb = false;
    const char *key = custom ? "MENU_60.0" : pal ? "MENU_50.2" : "MENU_59.8";
    uint64_t legacy = 0;
    for (const auto &entry : yc_modes) if (!strcmp(entry.key, key)) legacy = entry.phase_inc;
    assert(legacy && legacy != calculated);
    assert(output() == legacy);
    degauss_native_fb = true;
    assert(output() == calculated); // Re-entering native output never retains the old override.
}
int main(int argc, char **argv) {
    assert(argc == 2);
    for (int mode : {2, 3, 4}) for (bool pal : {false, true})
        native_case(argv[1], mode, pal, false);
    for (int mode : {2, 3, 4}) native_case(argv[1], mode, false, true);

    // Native/script/exit handovers must transmit the new selection even when
    // the video-info and framebuffer metadata have not changed.
    for (int mode : {2, 3, 4}) for (bool pal : {false, true}) {
        assert(!video_is_direct());
        native_case(argv[1], mode, pal, false);
        const uint64_t calculated = phase();
        unsigned updates = yc_updates, configurations = fb_configurations;
        video_set_degauss_native_fb(false);
        assert(!video_degauss_native_fb_active());
        assert(fb_configurations == configurations + 1);
        assert(yc_updates == updates + 1);
        assert(phase() != calculated);
        video_set_degauss_native_fb(true);
        assert(video_degauss_native_fb_active());
        assert(yc_updates == updates + 2 && phase() == calculated);
        video_set_degauss_native_fb(true);
        assert(yc_updates == updates + 2); // No redundant write for unchanged state.
    }
    for (int mode : {0, 1}) {
        cfg.vga_mode_int = mode;
        unsigned updates = yc_updates;
        video_set_degauss_native_fb(false);
        video_set_degauss_native_fb(true);
        assert(yc_updates == updates); // RGB/component handovers remain untouched.
    }
    cfg.vga_mode_int = 2; cfg.direct_video = true;
    unsigned updates = yc_updates;
    video_set_degauss_native_fb(false);
    assert(yc_updates == updates); // Direct Video retains its existing enable path.
    cfg.direct_video = false;
    cfg.degauss_native_analog = false;
    unsigned configurations = fb_configurations;
    video_set_degauss_native_fb(true);
    assert(!degauss_native_fb && fb_configurations == configurations);

    // Game-core calibration remains independent of the private Menu flag.
    core_name = "NES"; menu_core = false; degauss_native_fb = true;
    current_video_info = {256, 2048, 714733, 1663900, 880, false};
    load_table(argv[1]);
    uint64_t nes = 0;
    for (const auto &entry : yc_modes) if (!strcmp(entry.key, "NES_60.1")) nes = entry.phase_inc;
    assert(nes && output() == nes);

    // Existing shared-scaler and Direct Video selection still use the scaler clock.
    core_name = "MENU"; menu_core = true;
    v_cur.Fpix = 13.5;
    v_cur.param = {704, 24, 62, 68, 240, 4, 3, 15};
    for (bool direct : {false, true}) {
        cfg.vga_scaler = !direct; vga_fb = direct;
        memset(yc_modes, 0, sizeof(yc_modes));
        const uint64_t calculated = output();
        const std::vector<uint16_t> calculated_packet = words;
        // A user override matching this mode must remain ignored on scaler output.
        snprintf(yc_modes[0].key, sizeof(yc_modes[0].key), "MENU_60.1");
        yc_modes[0].phase_inc = 1;
        assert(output() == calculated && words == calculated_packet);
    }
    for (int mode : {0, 1}) {
        cfg.vga_mode_int = mode; set_yc_mode();
        assert(words == std::vector<uint16_t>{0});
    }
    puts("Native Y/C carrier and ordinary Menu/game/scaler override compatibility passed");
}
'''

with tempfile.TemporaryDirectory(prefix='degauss-yc-test-') as directory:
    build = Path(directory)
    unit = build / 'test.cpp'
    unit.write_text(prefix + production + checks)
    binary = build / 'test'
    command = [os.environ.get('CXX', 'c++'), '-std=c++14', '-Wall', '-Wextra', '-Werror']
    command += shlex.split(os.environ.get('CXXFLAGS', ''))
    # Keep the Linux production source unchanged on Apple's SDK.
    if os.uname().sysname == 'Darwin':
        command += ['-Wno-error=deprecated-declarations']
    subprocess.run(command + [str(unit), '-o', str(binary)], check=True)
    table = root / 'tests/fixtures/degauss-yc.txt'
    runner = shlex.split(os.environ.get('TEST_RUNNER', ''))
    result = subprocess.run(runner + [str(binary), str(table)], text=True, capture_output=True)
    if result.returncode:
        print(result.stdout + result.stderr)
        result.check_returncode()
    print(result.stdout.splitlines()[-1])
