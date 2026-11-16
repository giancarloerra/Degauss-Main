#!/usr/bin/env python3
"""Exercise the production HDMI ownership and hotplug functions."""
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

video = Path("video.cpp").read_text()
start = re.search(r"(?m)^(?:void tmds_power|static void hdmi_apply_power)\(", video).start()
functions = video[start:video.index("\nstatic int api1_5", start)]
state = "\n".join(
    re.findall(
        r"(?m)^static (?:bool|int) (?:hdmi_power|hdmi_need_init|degauss_crt_only_active|"
        r"degauss_hdmi_resume_power|degauss_hdmi_reconnect_pending) = .*;$",
        video,
    )
)
assert "DEGAUSS_CRT_ONLY" in Path("cfg.cpp").read_text()
assert re.search(r"0x41, \(uint8_t\)\(.*0x10.*0x50|0x41, \(uint8_t\)\(.*0x50.*0x10", video)

harness = r"""
#include <cassert>
#include <cstdint>
#include <cstdio>

static int hdmi_main_fd = 7;
static int write_count = 0, last_power = 0x10, irq = 0, sense = 0, warnings = 0, reinits = 0;
static bool owned = false, native = false, irq_supported = true;
static struct {
    bool degauss_crt_only = false;
    bool direct_video = false;
    bool vga_scaler = false;
} cfg;
static bool video_degauss_native_fb_active() { return native; }
static bool menu_degauss_controls_active() { return owned; }
static void cfg_error(const char *) { ++warnings; }
static bool hdmi_has_int() { return irq_supported; }
static void cec_poll() {}
static bool fpga_get_hdmi_int() { return irq != 0; }
static int i2c_smbus_read_byte_data(int fd, int address) {
    assert(fd == hdmi_main_fd);
    assert(address == 0x96 || address == 0x42);
    return address == 0x96 ? irq : sense;
}
static int i2c_smbus_write_byte_data(int fd, int address, int data) {
    assert(fd == hdmi_main_fd);
    assert(address == 0x96 || address == 0x41);
    if (address == 0x96) irq &= ~data;
    else { ++write_count; last_power = data; }
    return 0;
}
static void video_reinit();
"""
standard = "static int hdmi_power" in state
if standard:
    harness += """
static void hdmi_config_audio() {}
static void video_reinit() { ++reinits; hdmi_need_init = 0; }
"""
else:
    harness += """
static void usleep(unsigned) {}
static void video_reinit() { ++reinits; }
"""
tests = r"""
int main() {
    owned = native = true;
    video_poll();
    assert(write_count == 0); // default off: do not touch HDMI
    native = false;
    cfg.degauss_crt_only = true;
    video_poll();
    video_poll();
    assert(warnings == 1 && write_count == 0); // HDMI-only misconfiguration

    native = true;
    cfg.direct_video = true;
    video_poll();
    assert(!degauss_crt_only_active && last_power == 0x10);
    cfg.direct_video = false;
    video_poll();
    assert(degauss_crt_only_active && last_power == 0x50);

    const int writes = write_count;
    video_hdmi_power(1); // input resets the existing idle timer
    assert(write_count == writes && last_power == 0x50);
    irq = 0xc0;
    sense = 0;
    video_poll(); // unplug
    irq = 0xc0;
    sense = 0x60;
    video_poll(); // reconnect with stable HPD and monitor sense
    assert(!irq && last_power == 0x50 && reinits == 0);
    owned = false; // ordinary exit and native handovers use the same ownership bit
    video_poll();
    assert(!degauss_crt_only_active && last_power == 0x10 && reinits == 1);

    irq_supported = false; // boards without hotplug IRQ still need the setting
    native = false;
    cfg.vga_scaler = owned = true;
    video_poll();
    assert(degauss_crt_only_active && last_power == 0x50);
    video_hdmi_power(0); // honour the pre-existing idle timer on return
    owned = false;
    video_poll();
    assert(!degauss_crt_only_active && last_power == 0x50);
    video_hdmi_power(1);
    assert(last_power == 0x10);
}
"""
with TemporaryDirectory(prefix="degauss-crt-only-") as directory:
    target = Path(directory) / "test"
    source = target.with_suffix(".cpp")
    includes, declarations = harness.split("static int hdmi_main_fd", 1)
    source.write_text(includes + state + "\nstatic int hdmi_main_fd" + declarations + functions + tests)
    subprocess.run(["c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(target)], check=True)
    subprocess.run([str(target)], check=True)
print("CRT-only HDMI ownership and reconnect checks passed.")
