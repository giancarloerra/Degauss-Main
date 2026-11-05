#!/usr/bin/env python3
"""Run the production MGL page resolver against core configuration rows."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'menu.cpp').read_text()
start = source.index('static int MglFilePage(')
end = source.index('\n}\n', start) + 3
production = source[start:end]
hook_start = source.index('\t\thdmask = spi_uio_cmd16(UIO_GET_OSDMASK, 0);')
hook_end = source.index('\t\tuint32_t s_entry = 0;', hook_start)
hook = source[hook_start:hook_end]
binding = next(line.strip() for line in source.splitlines()
               if 'mgl->item[mgl->current].submenu = selentry;' in line)
reject_start = source.index('\t\t// F/S option not found -> deactivate mgl.')
reject_end = source.index('\n\t\t}\n', reject_start) + len('\n\t\t}\n')
rejection = source[reject_start:reject_end]
test = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
static std::vector<const char *> rows;
static char *user_io_get_confstr(int i) { return i < int(rows.size()) ? const_cast<char *>(rows[i]) : nullptr; }
static int user_io_hd_mask(const char *s) { return s[0] >= 'A' ? s[0] - 'A' + 10 : s[0] - '0'; }
PRODUCTION
static int page, flat, menusub, firstmenu;
static uint32_t hdmask, test_mask;
static const int UIO_GET_OSDMASK = 0;
static char title[32];
struct File { char type; int index; int submenu; };
struct Mgl { bool done; int current; File item[2]; int state = 0; } description;
static Mgl *mgl = &description;
static uint32_t spi_uio_cmd16(int, int) { return test_mask; }
static void user_io_read_confstr() {}
static void substrcpy(char *out, const char *in, int) {
    const char *label = std::strchr(in, ',');
    assert(label);
    std::strncpy(out, label + 1, 31);
    out[31] = 0;
}
static void render_mgl_page() {
    char *p;
HOOK
}
static void bind_mgl_slot(char type, int num, int d, int selentry) {
    const char p[] = {type, 0};
BINDING
}
static int consume_mgl_slot() {
    int menustate = -1;
    const int MENU_NONE1 = 1;
    int continued = 0;
    switch (0) {
        case 0:
REJECTION
        ++continued;
    }
    assert(menustate == -1 || menustate == MENU_NONE1);
    return continued;
}
int main() {
    // Real PCXT layout: cartridge slots are on page 1 and only visible for PCjr.
    rows = {"PCXT", "", "S0,IMG,Floppy;", "hEP1FC5,JRC,Cartridge 1;",
        "hEP1FC6,JRC,Cartridge 2;", "hEP1,System & BIOS;", "S2,VHD,Hard disk;"};
    assert(MglFilePage('F', 5, 0, 1U << 14) == 1);
    assert(MglFilePage('F', 6, 0, 1U << 14) == 1);
    assert(MglFilePage('F', 5, 0, 0) == 0); // Hidden in another machine mode.
    assert(MglFilePage('S', 0, 1, 0) == 0); // Next MGL item returns to the top.
    assert(MglFilePage('S', 2, 0, 0) == 0);
    assert(MglFilePage('F', 7, 1, ~0U) == 1); // Missing slot keeps the existing failure path.
    // Execute the actual render-state integration, not just the helper.
    test_mask = 1U << 14;
    page = flat = 0;
    menusub = firstmenu = 7;
    description = {false, 0, {{'F', 5, -1}, {'S', 0, -1}}};
    render_mgl_page();
    assert(page == 1 && menusub == 0 && firstmenu == 0);
    assert(std::strcmp(title, "System & BIOS;") == 0);
    description.current = 1;
    render_mgl_page();
    assert(page == 0);
    flat = 1;
    description.current = 0;
    render_mgl_page();
    assert(page == 0); // Flat layout still uses its existing top-level parser.
    flat = 0;
    description.done = true;
    render_mgl_page();
    assert(page == 0); // Normal interactive menus are untouched.
    rows = {"Core", "", "F5,JRC,Top;", "P1FC5,JRC,Nested;", "P2FS3,ROM,Nested;"};
    assert(MglFilePage('F', 5, 0, 0) == 0);
    assert(MglFilePage('F', 5, 1, 0) == 1); // Preserve the already selected matching page.
    assert(MglFilePage('F', 3, 0, 0) == 2);
    assert(MglFilePage('S', 3, 0, 0) == 0); // File and image slots are distinct.
    rows = {"Core", "", "DEFMRA,default.mra;", "P1F0,ROM,Nested;"};
    assert(MglFilePage('F', 0, 0, 0) == 1);
    rows = {"Core", "", "P0F5,JRC,Root page;"};
    assert(MglFilePage('F', 5, 1, 0) == 0);
    rows = {"Core", "", "H1h2P3F1,ROM,Conditional;", "P4D1F2,ROM,Literal;", "P1,Header;"};
    assert(MglFilePage('F', 1, 0, 1U << 2) == 3);
    assert(MglFilePage('F', 1, 0, (1U << 1) | (1U << 2)) == 0);
    assert(MglFilePage('R', 0, 0, 0) == 0);
    rows = {"Core", "", "S0,IMG,Enabled first row;", "D1P2F5,JRC,Disabled;", "d2P3F6,JRC,Inverse disabled;"};
    assert(MglFilePage('F', 5, 0, 1U << 1) == 0);
    assert(MglFilePage('F', 5, 0, 0) == 2);
    assert(MglFilePage('F', 6, 0, 0) == 0);
    assert(MglFilePage('F', 6, 0, 1U << 2) == 3);
    // mgl_parse zero-initializes every item. A disabled or missing slot
    // must not retain that zero and activate the first enabled media row.
    description = {false, 0, {{'F', 5, 0}, {'S', 0, 0}}};
    test_mask = 1U << 1;
    page = flat = 0;
    render_mgl_page();
    bind_mgl_slot('F', 5, 1, 4);
    assert(description.item[0].submenu == -1);
    bind_mgl_slot('F', 5, 0, 4);
    assert(description.item[0].submenu == 4);
    description.item[0] = {'F', 9, 0};
    render_mgl_page();
    assert(description.item[0].submenu == -1);
    assert(consume_mgl_slot() == 0 && description.state == 3);
    description.item[0].submenu = 2;
    description.state = 0;
    assert(consume_mgl_slot() == 1 && description.state == 0);
    description.done = true;
    description.item[0].submenu = -1;
    assert(consume_mgl_slot() == 1 && description.state == 0);
}
'''.replace('PRODUCTION', production).replace('HOOK', hook).replace('BINDING', binding).replace('REJECTION', rejection)
with tempfile.TemporaryDirectory(prefix='degauss-mgl-pages-') as tmp:
    cpp = Path(tmp) / 'test.cpp'
    binary = Path(tmp) / 'test'
    cpp.write_text(test)
    subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('MGL page resolver: passed')
