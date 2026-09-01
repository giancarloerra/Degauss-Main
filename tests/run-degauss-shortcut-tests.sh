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
