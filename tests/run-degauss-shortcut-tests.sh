#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

test_binary="$(mktemp -t degauss-shortcut-test.XXXXXX)"
trap 'rm -f "$test_binary"' EXIT

${CXX:-c++} -std=c++14 -Wall -Wextra -Werror \
	-I. tests/degauss_shortcut_logic_test.cpp -o "$test_binary"
"$test_binary"

# The shortcut must use the physical Linux key. Moving its hook below either
# transformation makes a saved assignment depend on the active keyboard map.
shortcut_hook_line="$(grep -n 'degauss_shortcut_handle_keyboard_event' input.cpp | cut -d: -f1)"
keyboard_map_guard_line="$(grep -n 'if (ev->type == EV_KEY && ev->code < 256' input.cpp | head -1 | cut -d: -f1)"
keyboard_map_line="$(grep -n 'kbdmap\[ev->code\]' input.cpp | cut -d: -f1)"
keyrah_line="$(grep -n 'ev->code = keyrah_trans' input.cpp | cut -d: -f1)"

test -n "$shortcut_hook_line"
test "$shortcut_hook_line" -lt "$keyboard_map_guard_line"
test "$shortcut_hook_line" -lt "$keyboard_map_line"
test "$shortcut_hook_line" -lt "$keyrah_line"
grep -B8 'degauss_shortcut_handle_keyboard_event' input.cpp | grep -q 'valid_keyboard_key(ev->code)'
grep -B8 'degauss_shortcut_handle_keyboard_event' input.cpp | grep -q '!input\[dev\]\.force_joy'
grep -q 'uint8_t  kbdmap\[256\]' input.cpp

# The two Degauss rows must follow their visible order when Up or Down changes
# menusub. They stay above every stock System-menu index, with no controller
# direction required to open the shortcut settings.
frontend_menusub="$(awk '$2 == "DEGAUSS_MENUSUB" { print $3 }' support/degauss/degauss_launcher.h)"
shortcut_menusub="$(awk '$2 == "DEGAUSS_SHORTCUT_MENUSUB" { print $3 }' support/degauss/degauss_launcher.h)"
test "$frontend_menusub" -eq 30
test "$shortcut_menusub" -eq 31

frontend_row_line="$(grep -n 'MenuWrite(n++, " Frontend ' menu.cpp | head -1 | cut -d: -f1)"
shortcut_row_line="$(grep -n 'MenuWrite(n++, " Frontend shortcut' menu.cpp | cut -d: -f1)"
core_row_line="$(grep -n 'MenuWrite(n++, " Core ' menu.cpp | head -1 | cut -d: -f1)"
test "$frontend_row_line" -lt "$shortcut_row_line"
test "$shortcut_row_line" -lt "$core_row_line"

if grep -q 'right && menusub == DEGAUSS_MENUSUB' menu.cpp; then
	echo "Frontend shortcut still depends on Right from the Frontend row" >&2
	exit 1
fi
grep -A4 'case DEGAUSS_SHORTCUT_MENUSUB:' menu.cpp \
	| grep -q 'menustate = MENU_DEGAUSS_SHORTCUT1'

# The release UI and input path are keyboard-only. Version 1 keeps a legacy
# byte solely so files written by local pre-release builds remain readable.
if grep -q ' Controller:' menu.cpp; then
	echo "Frontend shortcut UI still exposes a controller assignment" >&2
	exit 1
fi
if grep -q 'degauss_shortcut_handle_controller_event' input.cpp; then
	echo "Frontend shortcut input still handles controller events" >&2
	exit 1
fi
grep -q 'legacy_controller_button' support/degauss/degauss_shortcut_logic.h
grep -q ' A: Capture   X: Disable' menu.cpp
if grep -q 'set/capture' menu.cpp; then
	echo "Frontend shortcut UI still uses the ambiguous set/capture label" >&2
	exit 1
fi
