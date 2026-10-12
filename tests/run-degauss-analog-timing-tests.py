#!/usr/bin/env python3
"""Exercise the production analog modeline conversion independently of HDMI."""

from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
video = (root / "video.cpp").read_text()

# The released upstream recovery is limited to integer requests, not every
# fractional request whose failed search would later round in setPLL.
pll_start = video.index("static int findPLLpar(")
pll_end = video.index("static void setPLL(", pll_start)
pll_production = video[pll_start:pll_end]
pll_checks = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
''' + pll_production + r'''
int main() {
    uint32_t c, m; double ko;
    assert(findPLLpar(100.0, &c, &m, &ko, true) && ko == 0);
    assert(pll_request_on_integer(100.0));
    assert(findPLLpar(148.5, &c, &m, &ko, true) && ko != 0);
    assert(!pll_request_on_integer(148.5));
    assert(!findPLLpar(100.01, &c, &m, &ko, true));
    assert(!pll_request_on_integer(100.01));
    assert(!findPLLpar(100.0001, &c, &m, &ko, true));
    assert(pll_request_on_integer(100.0001));
    puts("Upstream integer-request PLL recovery contract passed");
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-pll-guard-") as temporary:
    unit = Path(temporary) / "pll.cpp"
    binary = Path(temporary) / "pll"
    unit.write_text(pll_checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

start = video.index("static bool degauss_native_timing(")
end = video.index("\n}\n", start) + 3
production = video[start:end]
parser_start = video.index("static int parse_custom_video_mode(")
parser_end = video.index("\n}\n", parser_start) + 3
production = video[parser_start:parser_end] + production
prepare_start = video.index("static bool prepare_degauss_native_timing(")
prepare_end = video.index("\n}\n", prepare_start) + 3
enable_start = video.index("void video_fb_enable(")
enable_end = video.index("\n}\n", enable_start) + 3
config_start = video.index("static void video_fb_config()\n{")
config_end = video.index("\n}\n", config_start) + 3
direct_start = video.index("bool video_is_direct()\n{")
direct_end = video.index("\n}\n", direct_start) + 3
harness = r'''
#include <cassert>
#include <cmath>
using std::isfinite;
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <cstdlib>
#include <strings.h>
#include <vector>
#define FB_SIZE (1920*1080)
struct vmode_custom_t {
    uint32_t item[32];
    struct { unsigned pr, rb, hpol, vpol; } param;
    double Fpix;
};
static unsigned pll_calls = 0;
static unsigned cfg_errors = 0;
static unsigned cvt_calls = 0;
static void setPLL(double, vmode_custom_t *) { ++pll_calls; }
static void cfg_error(const char *, ...) { ++cfg_errors; }
static void video_calculate_cvt(int, int, float, int, vmode_custom_t *) { ++cvt_calls; }
static char *strcpyz(char *out, const char *in) { return strcpy(out,in); }
static int str_tokenize(char *text, const char *separator, char **tokens, int max) {
    int count = 0;
    for (char *token = strtok(text,separator); token && count < max;
         token = strtok(nullptr,separator)) tokens[count++] = token;
    return count;
}
'''
framebuffer = r'''
#define PROFILE_FUNCTION()
#define UIO_SET_FBUF 0x2f
#define FB_ADDR 0x22000000
#define FB_EN 0x8000
#define FB_FILTER 0x4000
#define FB_NATIVE 0x2000
#define FB_FMT_RxB 0x10
#define FB_FMT_8888 6
#define FB_DV_LBRD 3
#define FB_DV_UBRD 2
static uint32_t framebuffer_storage;
static uint32_t *fb_base = &framebuffer_storage;
static bool native_active = true, menu_active = true;
static int menu_bg = 0, menu_bgn = 1, fb_num = 0, fb_enabled = 0;
static int fb_width = 320, fb_height = 240;
static int con_width = 320, con_height = 240, con_crt = 0;
static bool minimig_active = false, minimig_rtg_hdmi = false;
static int brd_x = 0, brd_y = 0;
static bool degauss_preset_filter = false, degauss_preset_active = false;
static char degauss_display_mask[1024] = {};
static vmode_custom_t v_cur = {};
static struct {
    char degauss_analog_video_mode[1024];
    int direct_video, fb_size, fb_hscale, menu_pal, vscale_border;
    int fb_terminal, vga_scaler, forced_scandoubler;
} cfg = {};
static int capability = 0xD161;
static unsigned disable_calls = 0;
static int vga_enable = -1;
static unsigned menu_status;
static std::vector<uint16_t> words;
static bool is_menu() { return menu_active; }
static bool is_minimig() { return minimig_active; }
static bool video_degauss_native_fb_active() { return native_active; }
static int spi_uio_cmd_cont(int) { return capability; }
static void spi_w(uint16_t value) { words.push_back(value); }
static void DisableIO() { ++disable_calls; }
static void fb_write_module_params() {}
static void input_switch(int) {}
static int video_fb_state() { return fb_enabled && !fb_num; }
static void degauss_restore_preset_baseline(bool) {}
static void setShadowMask() {}
static void set_vga_fb(int enable) { vga_enable = enable; }
static void set_yc_mode() {}
static void user_io_status_set(const char *bits, unsigned value) {
    assert(!strcmp(bits, "[8:5]")); menu_status = value;
}
'''
production += framebuffer + video[direct_start:direct_end] + video[prepare_start:prepare_end] + video[enable_start:enable_end] + video[config_start:config_end]
checks = r'''
int main() {
    vmode_custom_t mode = {};
    char modeline[] = "320,16,32,32,240,3,3,16,8000";
    assert(parse_custom_video_mode(modeline, &mode, false) == -2);
    assert(pll_calls == 0);
    assert(mode.Fpix == 8.0);
    assert(parse_custom_video_mode(modeline, &mode) == -2);
    assert(pll_calls == 1);
    char cvt_nan[] = "320,240,nan";
    assert(parse_custom_video_mode(cvt_nan, &mode, false) == -1);
    assert(cvt_calls == 0 && pll_calls == 1);
    char zero_clock[] = "320,16,32,32,240,3,3,16,0";
    assert(parse_custom_video_mode(zero_clock, &mode, false) == -2);
    uint16_t timing[8];
    assert(!degauss_native_timing(mode, timing));
    assert(pll_calls == 1);
    uint32_t source[] = {1,320,16,32,32,240,3,3,16};
    memcpy(mode.item, source, sizeof(source));
    mode.Fpix = 8.0;
    assert(degauss_native_timing(mode, timing));
    const uint16_t expected[] = {1000,840,920,800,262,243,246,240};
    assert(!memcmp(timing, expected, sizeof(expected)));
    mode.item[1] = 4096;
    mode.Fpix = 32.0;
    assert(!degauss_native_timing(mode, timing));
    memcpy(mode.item, source, sizeof(source));
    mode.Fpix = 8.0;
    // Equivalent modelines must retain the same real picture width and sync.
    for (unsigned i = 1; i <= 4; ++i) mode.item[i] *= 2;
    mode.Fpix *= 2;
    assert(degauss_native_timing(mode, timing));
    assert(!memcmp(timing, expected, sizeof(expected)));
    mode.Fpix = 0;
    assert(!degauss_native_timing(mode, timing));
    mode.Fpix = std::numeric_limits<double>::infinity();
    assert(!degauss_native_timing(mode, timing));
    mode.Fpix = 16.0;
    mode.param.pr = 1;
    assert(!degauss_native_timing(mode, timing));
    mode.param.pr = 0;
    mode.item[3] = 0;
    assert(!degauss_native_timing(mode, timing));
    mode.item[3] = 64;
    mode.item[8] = 0;
    assert(!degauss_native_timing(mode, timing));
    mode.item[8] = 4095;
    assert(!degauss_native_timing(mode, timing));

    strcpy(cfg.degauss_analog_video_mode, modeline);
    // A background framebuffer request is effectively enabled and needs the
    // same configured native timing and capability check as the frontend.
    menu_bg = 1;
    video_fb_enable(0, 0);
    assert(fb_enabled == 1 && fb_num == menu_bgn);
    assert(words.size() == 18);
    assert(!memcmp(words.data() + 10, expected, sizeof(expected)));
    words.clear();
    capability = 1;
    const unsigned errors_before = cfg_errors;
    video_fb_enable(0, 0);
    assert(words.empty() && cfg_errors == errors_before + 1);
    assert(disable_calls == 2);

    // Old Menu cores retain the original command when no override is set.
    cfg.degauss_analog_video_mode[0] = 0;
    menu_bg = 0;
    video_fb_enable(1, 0);
    assert(words.size() == 10);
    words.clear();
    video_fb_enable(0, 0);
    assert(words.size() == 1 && words[0] == 0);
    assert(fb_enabled == 0);

    // A core rejecting the framebuffer command must not enable Direct Video
    // merely because a Menu background was requested.
    words.clear();
    menu_bg = 1;
    capability = 0;
    cfg.direct_video = 1;
    video_fb_enable(0, 0);
    assert(words.empty() && vga_enable == 0 && fb_enabled == 0);
    cfg.direct_video = 0;
    menu_bg = 0;
    capability = 1;

    // Rejected INI values must not change the stored framebuffer dimensions.
    strcpy(cfg.degauss_analog_video_mode, zero_clock);
    fb_width = 321; fb_height = 241;
    const unsigned config_errors_before = cfg_errors;
    video_fb_config();
    assert(cfg_errors == config_errors_before + 1);
    assert(fb_width == 321 && fb_height == 241);
    strcpy(cfg.degauss_analog_video_mode, modeline);
    video_fb_config();
    assert(fb_width == 320 && fb_height == 240 && brd_x == 0 && brd_y == 0);
    cfg.degauss_analog_video_mode[0] = 0;
    video_fb_config();
    assert(fb_width == 352 && fb_height == 240);
    cfg.menu_pal = 1;
    video_fb_config();
    assert(fb_width == 352 && fb_height == 288);
    assert(!con_crt && con_width == 352 && con_height == 288);

    // The upstream terminal gets its own dimensions, not the scaled UI's.
    native_active = false;
    cfg.fb_terminal = 2;
    cfg.fb_size = 1; cfg.fb_hscale = 1;
    v_cur.item[1] = 1920; v_cur.item[5] = 1080;
    video_fb_config();
    assert(fb_width == 1920 && fb_height == 1080);
    assert(con_crt && con_width == 640 && con_height == 288);
    cfg.forced_scandoubler = 1;
    video_fb_config();
    assert(con_height == 576);
    words.clear();
    video_fb_enable(1, 0);
    assert(words[3] == 640 && words[4] == 576 && words[9] == 2560);
    assert(menu_status == 0xB); // FB bit 5 and LED bits 8:6.
    video_fb_enable(0, 0);
    assert(menu_status == 0);
    cfg.vga_scaler = 1;
    video_fb_config();
    assert(!con_crt && con_width == 1920 && con_height == 1080);
    cfg.vga_scaler = 0;
    cfg.direct_video = 1;
    video_fb_config();
    assert(!con_crt);
    minimig_active = true; minimig_rtg_hdmi = true;
    assert(!video_is_direct());
    video_fb_config();
    assert(con_crt);
    puts("Analog timing conversion passed");
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-analog-timing-") as temporary:
    source = Path(temporary) / "timing.cpp"
    binary = Path(temporary) / "timing"
    source.write_text(harness + production + checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
