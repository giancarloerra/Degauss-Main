#!/usr/bin/env python3
"""Check the production Apple III WOZ codec with bounded track decoding."""

from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
checks = r'''
#include "support/a3/a3_woz.h"
#include "support/a2/iigs_fmt.h"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
static void set32(uint8_t *p, uint32_t v) {
    p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24;
}
int main(int argc, char **argv) {
    assert(argc == 2);
    std::vector<uint8_t> disk(A2_525_IMAGE_SIZE), woz(512 * 1024);
    for (size_t i = 0; i < disk.size(); ++i) disk[i] = (i * 19 + i / 256) & 255;
    size_t size = a3_dsk_to_woz(woz.data(), woz.size(), disk.data(), 0, 42);
    assert(size);
    uint8_t decoded[A2_TRACK_SIZE] = {}, volumes[16];
    if (!strcmp(argv[1], "healthy")) {
        A2SectorOrder order = a2_detect_525_order(disk.data(), disk.size());
        assert(order == A2_ORDER_UNKNOWN || order == A2_ORDER_DOS || order == A2_ORDER_PRODOS);
        std::vector<uint8_t> nib(A2_NIB_IMAGE_SIZE);
        for (int t = 0; t < A2_TRACKS_525; ++t) {
            assert(a3_decode_track(woz.data(), size, t, decoded, volumes) == 16);
            assert(!memcmp(decoded, disk.data() + t * A2_TRACK_SIZE, A2_TRACK_SIZE));
            for (uint8_t v : volumes) assert(v == 42);
            a3_nib_track(nib.data() + t * A2_NIB_TRACK_SIZE, decoded, t, volumes);
        }
        size = a3_nib_to_woz(woz.data(), woz.size(), nib.data()); assert(size);
        for (int t = 0; t < A2_TRACKS_525; ++t) {
            assert(a3_decode_track(woz.data(), size, t, decoded, volumes) == 16);
            assert(!memcmp(decoded, disk.data() + t * A2_TRACK_SIZE, A2_TRACK_SIZE));
        }
        // The imported per-track conversion APIs must link and preserve sector order.
        uint8_t prodos[A2_TRACK_SIZE], restored[A2_525_IMAGE_SIZE];
        a2_dos_track_to_prodos(prodos, disk.data());
        std::vector<uint8_t> prodos_disk(A2_525_IMAGE_SIZE);
        a2_dos_to_prodos(prodos_disk.data(), disk.data());
        assert(!memcmp(prodos, prodos_disk.data(), A2_TRACK_SIZE));
        a2_prodos_to_dos(restored, prodos_disk.data());
        assert(!memcmp(restored, disk.data(), disk.size()));
    } else if (!strcmp(argv[1], "malformed")) {
        const auto valid = woz;
        memcpy(woz.data() + 248, "MISS", 4);
        assert(a3_decode_track(woz.data(), size, 0, decoded, volumes) == 0);
        woz = valid;
        set32(woz.data() + 16, UINT32_MAX);
        assert(a3_decode_track(woz.data(), size, 0, decoded, volumes) == 0);
        woz = valid;
        assert(a3_decode_track(woz.data(), size, -1, decoded, volumes) == 0);
        assert(a3_decode_track(woz.data(), size, INT32_MAX, decoded, volumes) == 0);
        set32(woz.data() + 252, 7);
        assert(a3_decode_track(woz.data(), 263, 0, decoded, volumes) == 0);
        woz = valid; woz[256] = woz[257] = 0xff;
        assert(a3_decode_track(woz.data(), size, 0, decoded, volumes) == 0);
        woz = valid; set32(woz.data() + 260, UINT32_MAX);
        assert(a3_decode_track(woz.data(), size, 0, decoded, volumes) == 0);
        assert(a3_decode_track(woz.data(), 11, 0, decoded, volumes) == 0);
    } else {
        // A rewritten track without an address field must not run beyond decoded bytes.
        bool long_track = !strcmp(argv[1], "long-empty");
        unsigned blocks = long_track ? 32 : 13, bytes = blocks * 512;
        woz[258] = blocks; woz[259] = 0;
        set32(woz.data() + 260, bytes * 8);
        memset(woz.data() + 1536, 0xff, bytes);
        set32(woz.data() + 8, woz_crc32(woz.data() + 12, size - 12));
        assert(a3_decode_track(woz.data(), size, 0, decoded, volumes) == 0);
        for (uint8_t v : volumes) assert(v == 254);
    }
}
'''
with tempfile.TemporaryDirectory(prefix="degauss-a3-woz-") as temporary:
    unit, binary = Path(temporary) / "codec.cpp", Path(temporary) / "codec"
    unit.write_text(checks)
    subprocess.run([
        "c++", "-std=c++14", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
        "-fsanitize=address,undefined", "-I", str(ROOT), str(unit),
        str(ROOT / "support/a3/a3_woz.cpp"), str(ROOT / "support/a2/iigs_fmt.cpp"),
        "-o", str(binary),
    ], check=True)
    for case in ("healthy", "empty", "long-empty", "malformed"):
        subprocess.run([str(binary), case], check=True, timeout=15)
print("Apple III DSK/NIB round-trip, linked sector-order APIs and empty-track bounds passed")
