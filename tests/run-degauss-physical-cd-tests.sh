#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

test_binary="$(mktemp -t degauss-physical-cd-test.XXXXXX)"
trap 'rm -f "$test_binary"' EXIT

${CXX:-c++} -std=c++14 -Wall -Wextra -Werror -I. \
	tests/degauss_physical_cd_logic_test.cpp \
	support/degauss/physical_cd_logic.cpp -o "$test_binary"
"$test_binary"

grep -q 'for (int i = 0; i < 8; i++)' support/degauss/physical_cd_autorun.cpp
grep -q 'O_RDONLY | O_NONBLOCK | O_CLOEXEC' support/degauss/physical_cd_autorun.cpp
grep -q 'pthread_create' support/degauss/physical_cd_autorun.cpp
grep -q 'detection_current(generation)' support/degauss/physical_cd_autorun.cpp
grep -q 'DEGAUSS_PHYSICAL_DISC_CONTROL_FILE' support/degauss/physical_cd_autorun.cpp
grep -q 'DEGAUSS_PHYSICAL_DISC_EVENT_FILE' support/degauss/physical_cd_autorun.cpp
grep -q 'access(DEGAUSS_PHYSICAL_DISC_EVENT_FILE, F_OK) != 0' support/degauss/physical_cd_autorun.cpp
grep -q 'GetTimer(CD_POLL_MS \* 4)' support/degauss/physical_cd_autorun.cpp
if grep -q 'xml_load' support/degauss/physical_cd_autorun.cpp; then
	echo "Physical-disc detection bypasses the Degauss launch handoff" >&2
	exit 1
fi
grep -q 'physical_cd_autorun_poll();' scheduler.cpp
