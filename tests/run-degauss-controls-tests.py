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
assert "if (menu_degauss_controls_active() && !user_io_osd_is_visible())" in source[capture - 170:capture]
custom_start = source.index("static bool degauss_controller_custom_key(")
custom = source[custom_start:source.index("\n}\n", custom_start) + 3]
assert "!menu_degauss_controls_active() || user_io_osd_is_visible()" in custom
assert "uinp_send_key" in custom and ".mmap[" not in custom.replace("input[dev].mmap[SYS_AXIS_X + axis]", "native_axis")
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

# Execute the production routing function with isolated Main state. The
# device/library boundary is covered separately on MiSTer, not by this test.
harness = r'''
#include "support/degauss/degauss_controls.h"
#include <cassert>
#include <utility>
static degauss_controls::Store degauss_controller_profiles;
static bool frontend = true, osd = false;
static bool menu_degauss_controls_active() { return frontend; }
static bool user_io_osd_is_visible() { return osd; }
static std::string degauss_controller_identity(int dev) { return dev ? "other" : "pad"; }
static degauss_controls::Bindings native{{10,11,12,13,14,15,16,17,18,19}};
static degauss_controls::Bindings degauss_controller_native(int) { return native; }
static constexpr uint16_t KEY_EMU = 1000, KEY_UP = 1, KEY_DOWN = 2,
    KEY_LEFT = 3, KEY_RIGHT = 4, KEY_ENTER = 5, KEY_ESC = 6,
    KEY_TAB = 7, KEY_SPACE = 8, KEY_PAGEUP = 9, KEY_PAGEDOWN = 10;
static const uint16_t degauss_controller_keys[] = {KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT,
    KEY_ENTER, KEY_ESC, KEY_TAB, KEY_SPACE, KEY_PAGEUP, KEY_PAGEDOWN};
static constexpr unsigned SYS_AXIS_X = 0;
static struct { uint32_t mmap[2]; } input[2] = {};
static std::vector<std::pair<uint16_t, int>> events;
static void uinp_send_key(uint16_t key, int press) { events.push_back({key, press}); }
'''
checks = r'''
int main() {
    assert(!degauss_controller_custom_key(0, 10, 1));
    auto data = degauss_controls::reply("DGCP");
    degauss_controls::word(data, 1);
    degauss_controls::text(data, "pad");
    for (unsigned role = 0; role < 10; ++role) {
        const uint32_t code = role == degauss_controls::SELECT ? 300 : degauss_controls::INHERIT;
        degauss_controls::word(data, code & 65535);
        degauss_controls::word(data, code >> 16);
    }
    std::string error;
    assert(degauss_controller_profiles.read(data, error));
    assert(!degauss_controller_custom_key(1, 300, 1));
    frontend = false;
    assert(!degauss_controller_custom_key(0, 300, 1));
    frontend = true; osd = true;
    assert(!degauss_controller_custom_key(0, 300, 1));
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
    input[0].mmap[0] = 0x20000 | 3;
    assert(degauss_controller_custom_key(0, KEY_EMU + 6, 1));
    assert(events.back() == std::make_pair(KEY_LEFT, 1));
    assert(degauss_controller_custom_key(0, KEY_EMU + 7, 0));
    assert(events.back() == std::make_pair(KEY_RIGHT, 0));
    count = events.size();
    native[degauss_controls::BACK] = 300;
    assert(degauss_controller_custom_key(0, 300, 1));
    assert(events.size() == count); // changed native mappings cannot emit an ambiguous action
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-control-routing-") as temporary:
    unit = Path(temporary) / "routing.cpp"
    unit.write_text(harness + custom + checks)
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
print("Controller profile, inheritance, conflict, malformed-input and frontend-only hook tests passed")
