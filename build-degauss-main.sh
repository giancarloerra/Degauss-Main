#!/usr/bin/env bash
# Build the Degauss fork of MiSTer Main for the device.
#
# Debian names the toolchain arm-linux-gnueabihf while upstream's Makefile
# defaults to arm-none-linux-gnueabihf; same target, different packaging, so
# BASE is overridden rather than the Makefile edited.
set -euo pipefail
cd "$(dirname "$0")"
# The Cortex-A9 in the DE10-Nano has NEON, and upstream builds with it: the
# scalar fallback in scaler.cpp is guarded by __ARM_NEON and does not even
# compile, carrying a duplicated default argument and an undeclared variable.
# Debian's compiler defaults to vfpv3-d16 and would take that dead branch, so
# the architecture is stated here rather than left to the toolchain default.
ARCH_FLAGS="-mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard"

IMAGE=degauss-main-build:bullseye
docker image inspect "$IMAGE" >/dev/null 2>&1 || docker build -t "$IMAGE" .docker
docker run --rm -v "$(pwd):/src" -w /src -u "$(id -u):$(id -g)" -e HOME=/tmp \
    "$IMAGE" make BASE=arm-linux-gnueabihf \
        CC="arm-linux-gnueabihf-gcc ${ARCH_FLAGS}" "$@"
