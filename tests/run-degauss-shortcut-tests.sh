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
keyboard_map_line="$(grep -n 'kbdmap\[ev->code\]' input.cpp | cut -d: -f1)"
keyrah_line="$(grep -n 'ev->code = keyrah_trans' input.cpp | cut -d: -f1)"

test -n "$shortcut_hook_line"
test "$shortcut_hook_line" -lt "$keyboard_map_line"
test "$shortcut_hook_line" -lt "$keyrah_line"

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

! grep -q 'right && menusub == DEGAUSS_MENUSUB' menu.cpp
grep -A4 'case DEGAUSS_SHORTCUT_MENUSUB:' menu.cpp \
	| grep -q 'menustate = MENU_DEGAUSS_SHORTCUT1'

# The release UI and input path are keyboard-only. Version 1 keeps a legacy
# byte solely so files written by local pre-release builds remain readable.
! grep -q ' Controller:' menu.cpp
! grep -q 'degauss_shortcut_handle_controller_event' input.cpp
grep -q 'legacy_controller_button' support/degauss/degauss_shortcut_logic.h
grep -q ' A: Capture   X: Disable' menu.cpp
! grep -q 'set/capture' menu.cpp
