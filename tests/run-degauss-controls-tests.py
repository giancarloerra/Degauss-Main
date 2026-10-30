#!/usr/bin/env python3
"""Validate controller profile compatibility and Main's frontend-only hooks."""

from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="degauss-controls-") as temporary:
    binary = Path(temporary) / "controls"
    subprocess.run([
        "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
        "-fsanitize=address,undefined", str(ROOT / "tests/degauss_controls_test.cpp"),
        "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)

source = (ROOT / "input.cpp").read_text()
assert "degauss_ensure_menu_mapping" not in source
encode_start = source.index("static void degauss_controller_encode(")
encode = source[encode_start:source.index("\n}\n", encode_start)]
assert "load_map(" not in encode and "gcdb_" not in encode
callback = source.index("static void input_cb(struct input_event *ev, struct input_absinfo *absinfo, int dev, bool menu_event)\n{")
shortcut = source.index("degauss_shortcut_handle_controller_event(sub_dev", callback)
capture = source.index("degauss_controller_capture_key(dev, ev->code", callback)
overlay = source.index("degauss_controller_custom_key(dev, ev->code", callback)
native = source.index("if (ev->code == input[dev].mmap[SYS_BTN_X])", overlay)
assert shortcut < capture < overlay < native
dispatch_start = source.rfind("if (menu_degauss_controls_active()", callback, capture)
dispatch_end = source.index("\n\t\t\t\t\tif (ev->value <= 1)", capture)
dispatch = source[dispatch_start:dispatch_end]
custom_start = source.index("static bool degauss_controller_custom_key(")
custom = source[custom_start:source.index("\n}\n", custom_start) + 3]
assert "!menu_degauss_controls_active() || user_io_osd_is_visible()" in custom
assert "uinp_send_key" in custom and ".mmap[" not in custom
negative_start = source.index("static bool degauss_controller_negative_axis(")
negative = source[negative_start:source.index("\n}\n", negative_start) + 3]
assert "degauss_controller_negative_axis(dev, ev.code)" in source
assert "degauss_controller_prepare_capture_axes(instance, error)" in source
axes_start = source.index("static bool degauss_controller_prepare_capture_axes(")
capture_axes = source[axes_start:source.index("\n}\n", axes_start) + 3]
axes_harness = r'''
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <string>
#include <linux/input.h>
#define NUMDEV 3
static std::array<bool, ABS_CNT> degauss_controller_capture_negative_axes{};
static struct { int fd; } pool[NUMDEV] = {{0}, {1}, {2}};
static struct { bool mouse; int bind; } input[NUMDEV] = {{false,-1}, {false,0}, {false,-1}};
static bool moved_to_edge = false;
static bool failed_read = false;
static bool test_bit(unsigned axis, const unsigned char *bits) { return bits[axis / 8] & (1u << (axis % 8)); }
static int capture_ioctl(int fd, unsigned long request, void *output) {
    assert(fd != 2); // another controller's neutral positions cannot affect capture
    if (failed_read) { errno = ENODEV; return -1; }
    if (request == EVIOCGBIT(EV_ABS, (ABS_CNT + 7) / 8)) {
        auto *bits = static_cast<unsigned char *>(output);
        if (!fd) for (unsigned axis : {0u,1u,2u,3u,5u,16u}) bits[axis/8] |= 1u << (axis%8);
        else bits[4/8] |= 1u << (4%8);
        return 0;
    }
    auto *info = static_cast<input_absinfo *>(output);
    if (request == EVIOCGABS(0)) *info = {moved_to_edge ? 0 : 128,0,255,0,0,0};
    else if (request == EVIOCGABS(1)) *info = {0,-32768,32767,0,0,0};
    else if (request == EVIOCGABS(2)) *info = {0,0,255,0,0,0};
    else if (request == EVIOCGABS(3)) *info = {0,0,0,0,0,0};
    else if (request == EVIOCGABS(4)) *info = {0,-100,100,0,0,0};
    else if (request == EVIOCGABS(5)) *info = {255,0,255,0,0,0};
    else if (request == EVIOCGABS(16)) *info = {0,-1,1,0,0,0};
    else return -1;
    return 0;
}
#define ioctl capture_ioctl
'''
axes_cases = r'''
int main() {
    std::string error;
    assert(degauss_controller_prepare_capture_axes(0, error));
    assert(degauss_controller_capture_negative_axes[0]); // unsigned centered stick, no native axis mapping
    assert(degauss_controller_capture_negative_axes[1]); // signed centered stick
    assert(degauss_controller_capture_negative_axes[4]); // bound node belongs to the same controller
    assert(degauss_controller_capture_negative_axes[16]); // centered hat remains two-sided
    assert(!degauss_controller_capture_negative_axes[2]); // zero-rest trigger cannot become a negative press
    assert(!degauss_controller_capture_negative_axes[5]); // maximum-rest trigger also remains one-sided
    assert(!degauss_controller_capture_negative_axes[3]); // invalid range is not a centered axis
    moved_to_edge = true;
    assert(degauss_controller_prepare_capture_axes(0, error));
    assert(!degauss_controller_capture_negative_axes[0]); // every capture observes fresh resting state
    failed_read = true;
    assert(!degauss_controller_prepare_capture_axes(0, error));
    assert(error == std::string("Reading controller axis capabilities: ") + strerror(ENODEV));
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-axis-capture-") as temporary:
    unit = Path(temporary) / "axes.cpp"
    unit.write_text(axes_harness + capture_axes + axes_cases)
    binary = Path(temporary) / "axes"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
menu = (ROOT / "menu.cpp").read_text()
predicate_start = menu.index("bool menu_degauss_controls_active()")
predicate = menu[predicate_start:menu.index("\n}", predicate_start)]
assert "degauss_running && menustate == MENU_SCRIPTS_FB2 && is_menu()" in predicate
assert "video_fb_state()" in predicate
assert "video_get_degauss_native_fb" not in predicate
ownership_harness = r'''
#include <cassert>
static bool degauss_running = true, menu_core = true, framebuffer = true;
static constexpr int MENU_SCRIPTS_FB2 = 1;
static int menustate = MENU_SCRIPTS_FB2;
static bool is_menu() { return menu_core; }
static bool video_fb_state() { return framebuffer; }
'''
ownership_cases = r'''
int main() {
    assert(menu_degauss_controls_active()); // frontend ownership, independent of analog output selection
    degauss_running = false; assert(!menu_degauss_controls_active());
    degauss_running = true; menustate = 0; assert(!menu_degauss_controls_active());
    menustate = MENU_SCRIPTS_FB2; menu_core = false; assert(!menu_degauss_controls_active());
    menu_core = true; framebuffer = false; assert(!menu_degauss_controls_active());
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-ownership-") as temporary:
    unit = Path(temporary) / "ownership.cpp"
    unit.write_text(ownership_harness + predicate + '\n}\n' + ownership_cases)
    binary = Path(temporary) / "ownership"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# Non-controller multimedia buttons share the EV_KEY branch. They must not
# replace the active pad, clear its labels, or enter capture/custom routing.
dispatch_harness = r'''
#include <cassert>
static bool frontend = true, osd = false, eligible = true;
static int active = 1, captures = 0, customs = 0;
static bool menu_degauss_controls_active() { return frontend; }
static bool user_io_osd_is_visible() { return osd; }
static bool degauss_controller_is_pad(int) { return eligible; }
static void degauss_controller_active(int dev) { active = dev; }
static bool degauss_controller_capture_key(int, int, int) { ++captures; return false; }
static bool degauss_controller_custom_key(int, int, int) { ++customs; return false; }
static void dispatch_event(int dev) {
    struct { int code, value; } event = {352, 1}; // KEY_OK on an ordinary multimedia device
    auto *ev = &event;
'''
dispatch_cases = r'''
}
int main() {
    eligible = false;
    assert(!degauss_controller_is_pad(2));
    dispatch_event(2);
    assert(active == 1 && !captures && !customs);
    eligible = true;
    dispatch_event(2);
    assert(active == 2 && captures == 1 && customs == 1);
    frontend = false; dispatch_event(3);
    frontend = true; osd = true; dispatch_event(3);
    assert(active == 2 && captures == 1 && customs == 1);
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-dispatch-") as temporary:
    unit = Path(temporary) / "dispatch.cpp"
    unit.write_text(dispatch_harness + dispatch + dispatch_cases)
    binary = Path(temporary) / "dispatch"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# Execute the production routing function with isolated Main state. The
# device/library boundary is covered separately on MiSTer, not by this test.
harness = r'''
#include "support/degauss/degauss_controls.h"
#include <cassert>
#include <utility>
static degauss_controls::Store degauss_controller_profiles;
static bool frontend = true, osd = false;
static unsigned degauss_controller_capture = 0;
static int degauss_controller_capture_device = -1;
static std::array<bool, 64> degauss_controller_capture_negative_axes{};
static bool menu_degauss_controls_active() { return frontend; }
static bool user_io_osd_is_visible() { return osd; }
static std::string degauss_controller_identity(int dev) { return dev ? "other" : "pad"; }
static degauss_controls::Bindings native{{10,11,12,13,14,15,16,17,18,19}};
static constexpr uint16_t KEY_EMU = 1000, KEY_UP = 1, KEY_DOWN = 2,
    KEY_LEFT = 3, KEY_RIGHT = 4, KEY_ENTER = 5, KEY_ESC = 6,
    KEY_TAB = 7, KEY_SPACE = 8, KEY_PAGEUP = 9, KEY_PAGEDOWN = 10;
static const uint16_t degauss_controller_keys[] = {KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_ENTER, KEY_ESC, KEY_TAB, KEY_SPACE, KEY_PAGEUP, KEY_PAGEDOWN};
static struct { uint32_t mmap[2]; } input[2] = {};
static std::vector<std::pair<uint16_t, int>> events;
static void uinp_send_key(uint16_t key, int press) { events.push_back({key, press}); }
'''
checks = r'''
int main() {
    degauss_controller_capture = 123456789;
    degauss_controller_capture_device = 0;
    degauss_controller_capture_negative_axes[0] = true;
    assert(degauss_controller_negative_axis(0, 0)); // centered axis can first be captured leftward without a native mapping
    assert(!degauss_controller_negative_axis(1, 0)); // no policy change for another controller
    assert(!degauss_controller_negative_axis(0, 2)); // resting unipolar trigger stays one-sided
    frontend = false; assert(!degauss_controller_negative_axis(0, 0));
    frontend = true; osd = true; assert(!degauss_controller_negative_axis(0, 0));
    osd = false; degauss_controller_capture = 0;
    assert(!degauss_controller_negative_axis(0, 0)); // no lasting native-axis policy change after capture
    assert(!degauss_controller_custom_key(0, 10, 1));
    auto data = degauss_controls::reply("DGCP");
    degauss_controls::word(data, 1);
    degauss_controls::text(data, "pad");
    for (unsigned role = 0; role < 10; ++role) {
        const uint16_t code = role == degauss_controls::SELECT ? 300 : native[role];
        const bool direction = role == degauss_controls::LEFT || role == degauss_controls::RIGHT;
        degauss_controls::word(data, direction ? 2 : 1);
        degauss_controls::word(data, code);
        degauss_controls::text(data, "Saved");
        if (direction) {
            degauss_controls::word(data, KEY_EMU + (role == degauss_controls::LEFT ? 6 : 7));
            degauss_controls::text(data, "Stick");
        }
    }
    std::string error;
    assert(degauss_controller_profiles.read(data, error));
    assert(!degauss_controller_custom_key(1, 300, 1));
    frontend = false;
    assert(!degauss_controller_custom_key(0, 300, 1));
    assert(!degauss_controller_negative_axis(0, 3));
    frontend = true; osd = true;
    assert(!degauss_controller_custom_key(0, 300, 1));
    assert(!degauss_controller_negative_axis(0, 3));
    osd = false;
    assert(events.empty());
    for (unsigned role = 0; role < 10; ++role) {
        const uint16_t code = role == degauss_controls::SELECT ? 300 : 10 + role;
        assert(degauss_controller_custom_key(0, code, 1));
        assert(events.back() == std::make_pair(static_cast<uint16_t>(role + 1), 1));
        assert(degauss_controller_custom_key(0, code, 0));
        assert(events.back() == std::make_pair(static_cast<uint16_t>(role + 1), 0));
    }
    auto count = events.size();
    assert(degauss_controller_custom_key(0, 14, 1));
    assert(degauss_controller_custom_key(0, 300, 2));
    assert(events.size() == count);
    input[0].mmap[0] = 0x20000 | 4;
    assert(degauss_controller_negative_axis(0, 3)); // saved stick remains two-sided after native axes change
    assert(!degauss_controller_negative_axis(1, 3)); // never changes another controller's native axis policy
    assert(degauss_controller_custom_key(0, KEY_EMU + 6, 1));
    assert(events.back() == std::make_pair(KEY_LEFT, 1));
    assert(degauss_controller_custom_key(0, KEY_EMU + 7, 0));
    assert(events.back() == std::make_pair(KEY_RIGHT, 0));
    count = events.size();
    native[degauss_controls::BACK] = 300;
    assert(degauss_controller_custom_key(0, 15, 1));
    assert(events.size() == count + 1 && events.back() == std::make_pair(KEY_ESC, 1));
    assert(degauss_controller_custom_key(0, 300, 1));
    assert(events.back() == std::make_pair(KEY_ENTER, 1)); // custom map never merges later native changes
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-routing-") as temporary:
    unit = Path(temporary) / "routing.cpp"
    unit.write_text(harness + negative + custom + checks)
    binary = Path(temporary) / "routing"
    subprocess.run([
        "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
        "-fsanitize=address,undefined", str(unit), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)

capture_start = source.index("static bool degauss_controller_capture_key(")
capture_function = source[capture_start:source.index("\n}\n", capture_start) + 3]
capture_harness = r'''
#include "support/degauss/degauss_controls.h"
#include <cassert>
static unsigned degauss_controller_capture = 123;
static int degauss_controller_capture_device = 0;
static uint16_t degauss_controller_capture_code = 0;
static uint32_t degauss_controller_capture_since = 0;
static constexpr unsigned SYS_BTN_OSD_KTGL = 0;
static struct { uint32_t mmap[3]; } input[1] = {};
static bool user_io_osd_is_visible() { return false; }
static uint32_t GetTimer(unsigned) { return 100; }
static void degauss_controller_error(unsigned, const std::string &) {}
static void degauss_controller_cancel_capture() { degauss_controller_capture = 0; }
static void degauss_controller_reply(unsigned, const std::vector<uint8_t> &) {}
static std::string degauss_controller_label(int, uint16_t) { return "A"; }
'''
capture_cases = r'''
int main() {
    assert(!degauss_controller_capture_key(0, 300, 0)); // release of the Select that opened capture
    assert(degauss_controller_capture_key(0, 301, 1));
    assert(degauss_controller_capture_code == 301);
    assert(!degauss_controller_capture_key(0, 302, 0)); // other previously held controls also release
    assert(degauss_controller_capture_key(0, 301, 0));
    assert(!degauss_controller_capture && !degauss_controller_capture_code);
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-capture-") as temporary:
    unit = Path(temporary) / "capture.cpp"
    unit.write_text(capture_harness + capture_function + capture_cases)
    binary = Path(temporary) / "capture"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

poll_start = source.index("static void degauss_controller_poll()")
poll_function = source[poll_start:source.index("\n}\n", poll_start) + 3]
poll_harness = r'''
#include "support/degauss/degauss_controls.h"
#include <cassert>
#include <unistd.h>
static bool active = true;
static bool menu_degauss_controls_active() { return active; }
static bool user_io_osd_is_visible() { return false; }
static bool degauss_controller_session = false, degauss_controller_inventory_changed = false;
static unsigned degauss_controller_capture = 0;
static int degauss_controller_capture_device = -1, degauss_controller_active_device = -1;
static unsigned degauss_controller_capture_code = 0, degauss_controller_capture_since = 0,
    degauss_controller_capture_started = 0;
static std::string degauss_controller_capture_identity, degauss_controller_active_identity;
static degauss_controls::Store degauss_controller_profiles;
static struct { int fd; } pool[1];
static const uint16_t degauss_controller_keys[] = {1,2,3,4,5,6,7,8,9,10};
static unsigned releases = 0;
static void uinp_send_key(uint16_t, int value) { assert(!value); ++releases; }
static void degauss_controller_cancel_capture() { degauss_controller_capture = 0; }
static void degauss_controller_snapshot(unsigned) {}
static std::string degauss_controller_identity(int) { return "pad"; }
static void degauss_controller_active(int dev) { degauss_controller_active_device = dev; }
static uint32_t GetTimer(unsigned) { return 100; }
static void degauss_controller_error(unsigned, const std::string &) {}
'''
poll_cases = r'''
int main() {
    degauss_controller_poll();
    assert(degauss_controller_session && !releases);
    active = false;
    degauss_controller_poll();
    assert(!degauss_controller_session && releases == 10); // no held translated keys leak into native scripts/OSD
    degauss_controller_poll();
    assert(releases == 10); // idle native input is untouched
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-handover-") as temporary:
    unit = Path(temporary) / "handover.cpp"
    unit.write_text(poll_harness + poll_function + poll_cases)
    binary = Path(temporary) / "handover"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

snapshot_start = source.index("static void degauss_controller_snapshot(unsigned token)\n{")
snapshot_function = source[snapshot_start:source.index("\n}\n", snapshot_start) + 3]
snapshot_harness = r'''
#include "support/degauss/degauss_controls.h"
#include <cassert>
#define NUMDEV 1
static int degauss_controller_active_device = -1;
static uint16_t degauss_controller_generation = 1;
static bool degauss_controller_inventory_changed = true;
static bool degauss_controller_is_pad(int) { return false; }
static void degauss_controller_encode(std::vector<uint8_t> &, int) {}
static void degauss_controller_reply(unsigned, const std::vector<uint8_t> &) {}
'''
snapshot_cases = r'''
int main() {
    degauss_controller_snapshot(123456789);
    assert(degauss_controller_inventory_changed); // a list reply does not refresh the active report
    degauss_controller_snapshot(0);
    assert(!degauss_controller_inventory_changed);
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-snapshot-") as temporary:
    unit = Path(temporary) / "snapshot.cpp"
    unit.write_text(snapshot_harness + snapshot_function + snapshot_cases)
    binary = Path(temporary) / "snapshot"
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

alternate_start = source.index("static std::array<uint16_t, 4> degauss_controller_native_alternates(")
native_start = source.index("static degauss_controls::Bindings degauss_controller_native(")
native_function = source[alternate_start:source.index("\n}\n", native_start) + 3]
definitions = "\n".join(line for line in (ROOT / "input.h").read_text().splitlines()
                        if line.startswith("#define SYS_BTN_") or line.startswith("#define SYS_AXIS_")
                        or line.startswith("#define SYS_MS_")
                        or line.startswith("#define KEY_EMU "))
native_harness = r'''
#include <linux/input.h>
#include "support/degauss/degauss_controls.h"
#include <cassert>
static constexpr int QUIRK_WHEEL = 1;
static struct { uint32_t mmap[32]; int quirk; } input[1] = {};
'''
native_cases = r'''
int main() {
    input[0].mmap[SYS_BTN_UP] = 300;
    input[0].mmap[SYS_MS_UP] = 301;
    input[0].mmap[SYS_AXIS_X] = 0x20000;
    input[0].mmap[SYS_AXIS_Y] = 0x20001;
    auto primary = degauss_controller_native(0);
    auto alternate = degauss_controller_native_alternates(0);
    assert(primary[degauss_controls::UP] == 300);
    assert(primary[degauss_controls::LEFT] == KEY_EMU);
    assert(alternate[degauss_controls::LEFT] == KEY_EMU);
    assert(alternate[degauss_controls::UP] == KEY_EMU + 2);
    auto controls = degauss_controller_native_controls(0);
    assert((controls[degauss_controls::UP] == std::array<uint16_t, 3>{{300, 301, KEY_EMU + 2}}));
    input[0].mmap[SYS_BTN_L] = 310;
    input[0].mmap[SYS_BTN_MENU_FUNC] = 310;
    primary = degauss_controller_native(0);
    assert(primary[degauss_controls::SELECT] == 310);
    assert(!primary[degauss_controls::PAGE_PREVIOUS]); // native OK wins over the same shoulder's page action
    input[0].mmap[SYS_MS_LEFT] = 302;
    assert(degauss_controller_native(0)[degauss_controls::LEFT] == 302); // mouse navigation precedes stick fallback
    input[0].mmap[SYS_BTN_START] = 302;
    assert(degauss_controller_native(0)[degauss_controls::LEFT] == KEY_EMU); // Start consumes this key without a frontend action
    input[0].mmap[SYS_MS_LEFT] = 0;
    input[0].mmap[SYS_MS_UP] = KEY_EMU;
    controls = degauss_controller_native_controls(0);
    assert(!controls[degauss_controls::LEFT][0]); // earlier mouse Up owns the same physical code
    assert(controls[degauss_controls::UP][1] == KEY_EMU);
    input[0].mmap[SYS_MS_UP] = 0;
    input[0].mmap[SYS_AXIS_X] = UINT32_MAX;
    input[0].mmap[SYS_AXIS_Y] = UINT32_MAX;
    assert(!degauss_controller_native_alternates(0)[degauss_controls::LEFT]);
    assert(!degauss_controller_native(0)[degauss_controls::LEFT]); // unavailable axes never become fictitious buttons
}
'''
if sys.platform.startswith("linux"):
    with tempfile.TemporaryDirectory(prefix="degauss-control-native-copy-") as temporary:
        unit = Path(temporary) / "native.cpp"
        unit.write_text(native_harness + definitions + '\n' + native_function + native_cases)
        binary = Path(temporary) / "native"
        subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                        "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)

if sys.platform.startswith("linux"):
    start = source.index("static bool degauss_controller_is_pad(")
    inventory = source[start:source.index("\n}\n", start) + 3]
    dependencies = r'''
#include <linux/input.h>
#include <cstring>
#include <cassert>
#include "support/degauss/degauss_controls.h"
#define NUMDEV 4
#define KEY_EMU (KEY_MAX + 1)
#define JOYCON_COMBINED(dev) 0
#define test_bit(bit, array) (array[(bit) / 8] & (1 << ((bit) % 8)))
static constexpr int QUIRK_LIGHTGUN_MOUSE = 1;
static struct { int fd; } pool[NUMDEV];
static struct { bool mouse, force_joy, has_mmap; int bind, quirk; uint32_t mmap[10]; } input[NUMDEV] = {};
static degauss_controls::Bindings degauss_controller_native(int dev) {
    degauss_controls::Bindings result{}; result[0] = input[dev].mmap[0]; return result;
}
static int test_ioctl(int fd, unsigned long request, unsigned char *bits) {
    memset(bits, 0, _IOC_SIZE(request));
    const auto set = [&](unsigned code) { bits[code / 8] |= 1 << (code % 8); };
    if (_IOC_NR(request) == _IOC_NR(EVIOCGBIT(EV_KEY, 0))) set(fd == 11 ? BTN_SOUTH : KEY_OK);
    else if (fd == 13) set(ABS_HAT0X);
    else set(ABS_VOLUME);
    return 0;
}
#define ioctl test_ioctl
'''
    cases = r'''
int main() {
    for (int i = 0; i < NUMDEV; ++i) { pool[i].fd = 10 + i; input[i].bind = i; }
    input[1].bind = 0;
    assert(degauss_controller_is_pad(0)); // pad lives on a bound interface, not the primary keyboard node
    assert(!degauss_controller_is_pad(1)); // one logical controller, not duplicate interface entries
    assert(!input[0].has_mmap && !input[0].mmap[0]); // inventory never initialises or overwrites Main's mapping
    assert(!degauss_controller_is_pad(2)); // multimedia keyboard is not a gamepad
    assert(degauss_controller_is_pad(3)); // hat-only input
    input[2].force_joy = true;
    assert(degauss_controller_is_pad(2)); // explicit MiSTer keyboard-as-joystick setting
    input[2].force_joy = false; input[2].has_mmap = true;
    input[2].mmap[0] = BTN_SOUTH;
    assert(!degauss_controller_is_pad(2)); // an unrelated default map does not turn a keyboard into a pad
    input[2].mmap[0] = KEY_OK;
    assert(degauss_controller_is_pad(2)); // a nonstandard control explicitly mapped by MiSTer
    input[2].mmap[0] = KEY_EMU + ABS_VOLUME * 2;
    assert(degauss_controller_is_pad(2)); // an axis explicitly configured for native menu navigation
    pool[1].fd = -1;
    assert(!degauss_controller_is_pad(0));
}
'''
    with tempfile.TemporaryDirectory(prefix="degauss-control-inventory-") as temporary:
        unit = Path(temporary) / "inventory.cpp"
        unit.write_text(dependencies + inventory + cases)
        binary = Path(temporary) / "inventory"
        subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                        "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)
print("Controller profile, independent mapping, conflict, malformed-input and frontend-only hook tests passed")
