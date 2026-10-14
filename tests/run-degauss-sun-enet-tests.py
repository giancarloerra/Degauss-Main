#!/usr/bin/env python3
"""Check production Sun bridge retries and unchanged mailbox handling."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "support/sun/sun_enet.cpp").read_text()
production = source[source.index("#define SB_BASE"):]
dependencies = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <sys/mman.h>
static unsigned long now = 1;
static unsigned selection, opens, closes;
static int open_ok;
static void *mapped;
static const char *sun_net_status() { return "network"; }
static unsigned user_io_status_get(const char *) { return selection; }
unsigned long GetTimer(unsigned long delay) { return now + delay; }
unsigned long CheckTimer(unsigned long deadline) { return now >= deadline; }
static void sun_idprom_send() {}
static void *shmem_map(unsigned long, unsigned long size) {
    mapped = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, -1, 0);
    assert(mapped != MAP_FAILED); return mapped;
}
static int ethernet_open(const char *, int) { ++opens; return open_ok; }
static void ethernet_close() { ++closes; }
static void ethernet_send(const uint8_t *, int) {}
static int ethernet_recv_nb(uint8_t *, int) { return 0; }
static int ethernet_set_mac_filter(const uint8_t *) { return 1; }
static int ethernet_macvlan_create(const char *, const char *, const uint8_t *) { return 1; }
static void ethernet_macvlan_delete(const char *) {}
static int a2065_mode_available(int) { return 1; }
static void ethernet_offload_off(const char *) {}
static void ethernet_offload_on(const char *) {}
'''
checks = r'''
int main() {
    sun_enet_start(); wr64(SB_MAGIC_OFF, SB_MAGIC_S2);
    sun_enet_poll(); assert(opens == 1 && !link_open);
    for (int i = 0; i < 100; ++i) sun_enet_poll();
    assert(opens == 1); // A failing external interface is not reopened on every poll.
    now = 1000; sun_enet_poll(); assert(opens == 1);
    now = 1001; sun_enet_poll(); assert(opens == 2);
    now = 2001; open_ok = 1; sun_enet_poll(); assert(opens == 3 && link_open);
    sun_enet_poll(); assert(opens == 3); // Healthy links are not reopened.
    selection = 2; sun_enet_poll(); assert(opens == 4 && closes == 1);
    selection = 4; open_ok = 0; sun_enet_poll(); assert(opens == 5 && closes == 2);
    sun_enet_poll(); assert(opens == 5);
    selection = 0; open_ok = 1; sun_enet_poll(); assert(opens == 6 && link_open);
    // A changed selection opens immediately even while a former retry is pending.
    selection = 1; sun_enet_poll(); assert(closes == 3 && !link_open);
    sun_enet_poll(); assert(opens == 6);
    sun_enet_stop();
    sun_enet_start(); wr64(SB_MAGIC_OFF, SB_MAGIC_S3);
    selection = 0; sun_enet_poll(); assert(opens == 7 && link_open);
    sun_enet_stop(); assert(closes == 4 && !munmap(mapped, SB_SIZE));
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-sun-enet-") as temporary:
    unit, binary = Path(temporary) / "bridge.cpp", Path(temporary) / "bridge"
    unit.write_text(dependencies + production + checks)
    subprocess.run([
        "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
        str(unit), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
print("Sun bridge failed-open retry, immediate mode switch, stop/restart and healthy-link checks passed")
