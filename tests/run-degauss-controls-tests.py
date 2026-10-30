#!/usr/bin/env python3
"""Validate controller profile compatibility and Main's frontend-only hooks."""

from pathlib import Path
import subprocess
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
assert "video_get_degauss_native_fb() && video_fb_state()" in predicate

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
print("Controller profile, inheritance, conflict, malformed-input and frontend-only hook tests passed")
