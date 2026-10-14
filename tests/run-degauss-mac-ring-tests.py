#!/usr/bin/env python3
"""Check production Mac PPC ring polling using real mapped host memory."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "support/mac/mac_eth.cpp").read_text()
start = source.index("#define RING_BASE")
production = source[start:source.index("void mac_eth_poll(", start)]
dependencies = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <sys/mman.h>
static unsigned opt = 1, opens, closes, addresses, sends, barriers;
static const char *good_iface;
static bool zero_tap;
static int open_ok;
static volatile uint64_t *ring;
static char ifname[64];
static const char *const q8_iface_names[] = {"eth0", "eth1", "wlan0", "tap0"};
#define MAC_OUI_0 8
#define MAC_OUI_1 0
#define MAC_OUI_2 7
static unsigned user_io_status_get(const char *) { return opt; }
static bool CheckTimer(unsigned long) { return true; }
static unsigned long GetTimer(unsigned long) { return 0; }
static void *shmem_map(unsigned long, unsigned long size) {
    void *mapped = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    assert(mapped != MAP_FAILED); return (void *)(ring = (volatile uint64_t *)mapped);
}
// The production interface helper returns 0 on failure and 1 on success.
static int mac_eth_iface_open(const char *) { ++opens; return open_ok; }
static void mac_eth_iface_close() { ++closes; }
static int mac_eth_iface_hwaddr(const char *name, uint8_t *hw) {
    ++addresses;
    if (zero_tap && !strcmp(name, "tap0")) return 1;
    if (!good_iface || strcmp(name, good_iface)) return 0;
    const uint8_t value[] = {2, 3, 4, 5, 6, 7}; memcpy(hw, value, sizeof(value)); return 1;
}
static const char *user_io_get_core_name() { return "MacPPC7300"; }
static int mac_eth_iface_send(const uint8_t *, int) {
    assert(barriers & 1); // Slot reads/sends occur after acquire and before release.
    ++sends; assert(sends <= 8); return 1;
}
static int mac_eth_iface_recv(uint8_t *, int) { return -1; }
static void record_barrier() { ++barriers; }
#define __sync_synchronize() record_barrier()
'''
checks = r'''
int main(int argc, char **argv) {
    assert(argc == 2);
    if (!strncmp(argv[1], "tap-", 4)) {
        opt = 4; open_ok = 1;
        if (!strcmp(argv[1], "tap-valid")) good_iface = "tap0";
        if (!strcmp(argv[1], "tap-eth")) good_iface = "eth0";
        if (!strcmp(argv[1], "tap-zero-wifi")) { zero_tap = true; good_iface = "wlan0"; }
        ring_poll();
        uint8_t published[8]; uint64_t address = ring[5]; memcpy(published, &address, sizeof(address));
        assert(published[0] == 8 && published[1] == 0 && published[2] == 7);
        assert(published[3] == (good_iface ? 5 : 0) && published[4] == (good_iface ? 6 : 0) && published[5] == (good_iface ? 7 : 0));
        assert(addresses == (!strcmp(argv[1], "tap-valid") ? 1u : !strcmp(argv[1], "tap-eth") ? 2u : 3u));
        assert(!munmap((void *)ring, RING_SIZE)); return 0;
    }
    open_ok = strcmp(argv[1], "open-failure") != 0;
    ring_poll();
    if (!open_ok) {
        assert(opens == 1 && addresses == 0 && ring[5] == 0);
        ring_poll(); assert(opens == 2); // Failed opens remain retryable, never falsely up.
    } else {
        assert(opens == 1 && addresses == 1 && ring[5] != 0);
        ring[0] = (uint64_t)RING_MAGIC << 32;
        for (unsigned slot = 0; slot < 8; ++slot) ring[0x200 + slot * 0x100] = 64;
        ring[1] = 3; ring_poll(); assert(sends == 3 && ring[2] == 3);
        assert(barriers == 2);
        // Only the eight still-stored slots are processed after a producer overrun.
        sends = 0; ring[1] = 20; ring_poll(); assert(sends == 8 && ring[2] == 20);
        sends = 0; ring[1] = UINT32_MAX - 2; ring_poll(); assert(sends == 8 && ring[2] == UINT32_MAX - 2);
        // Counter wrap must still process the ordinary five pending frames.
        sends = 0; ring[1] = 2; ring_poll(); assert(sends == 5 && ring[2] == 2);
        opt = 3; ring_poll();
        assert(opens == 2 && closes == 1 && !strcmp(ifname, "wlan0"));
        ring_poll(); assert(opens == 2 && closes == 1); // An unchanged selection is not reopened.
        opt = 2; open_ok = 0; ring_poll(); assert(opens == 3 && closes == 2);
        ring_poll(); assert(opens == 4 && closes == 2); // A failed changed interface stays retryable.
        open_ok = 1; ring_poll(); assert(opens == 5 && addresses == 3);
        assert(!strcmp(ifname, "eth1"));
        opt = 0; ring_poll(); assert(closes == 3);
        opt = 7; ring_poll(); assert(opens == 5 && closes == 3);
    }
    assert(!munmap((void *)ring, RING_SIZE));
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-mac-ring-") as temporary:
    unit, binary = Path(temporary) / "ring.cpp", Path(temporary) / "ring"
    unit.write_text(dependencies + production + checks)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined", str(unit), "-o", str(binary)], check=True)
    for name in ("open-failure", "tx-bound", "tap-valid", "tap-eth", "tap-zero-wifi", "tap-fixed"):
        subprocess.run([str(binary), name], check=True)
print("Mac PPC failed-open, interface-switch, TAP address, TX ordering and eight-slot checks passed")
