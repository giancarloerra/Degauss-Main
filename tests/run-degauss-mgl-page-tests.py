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
binding_at = source.index('mgl->item[mgl->current].submenu = selentry;')
binding_end = source.index('\n\n', binding_at)
binding = source[source.rindex('int idx = 1;', hook_end, binding_end):binding_end]
select_at = source.index('menusub = mgl->item[mgl->current].submenu;', binding_end)
lookup_start = source.index('\t\t\t\twhile (1)', select_at)
actions = source[source.index('\n\n', select_at):source.index('\t\t\t\tstatic char ext[256];', select_at)]
action_guards = [line.strip().removeprefix('else ') for line in actions.splitlines()
                 if line.strip().startswith(('if (', 'else if (')) and '_submenu == menusub' in line]
menu_actions = '\n'.join(f'    {guard} ordinary_menu_command = true;' for guard in action_guards)
guard_at = source.index('if (p && !d)', lookup_start)
file_at = source.index("if (p[0] == 'F' && (select || recent))", guard_at)
image_at = source.index("else if (p[0] == 'S' && (select || recent))", file_at)
lookup = source[lookup_start:source.index('\n', guard_at)]
file_index = source[source.index('store_name = 0;', file_at):source.index('substrcpy(ext, p, 1);', file_at)]
image_index = source[source.index('store_name = 0;', image_at):source.index('substrcpy(ext, p, 1);', image_at)]
reject_start = source.index('\t\t// F/S option not found -> deactivate mgl.')
reject_end = source.index('\n\t\t}\n', reject_start) + len('\n\t\t}\n')
rejection = source[reject_start:reject_end]
test = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
static std::vector<const char *> rows;
static char *user_io_get_confstr(int i) { return i < int(rows.size()) ? const_cast<char *>(rows[i]) : nullptr; }
static int user_io_hd_mask(const char *s) { return s[0] >= 'A' ? s[0] - 'A' + 10 : s[0] - '0'; }
PRODUCTION
static int page, flat, firstmenu;
static uint32_t menusub;
static uint32_t hdmask, test_mask;
static const int UIO_GET_OSDMASK = 0;
static char title[32];
struct File { char type; int index; int submenu; };
struct Mgl { bool done; int current; File item[2]; int state = 0; } description;
static Mgl *mgl = &description;
static uint32_t spi_uio_cmd16(int, int) { return test_mask; }
static void user_io_read_confstr() {}
static bool mgl_enabled;
static void substrcpy(char *out, const char *in, int) {
    const char *label = std::strchr(in, ',');
    assert(label);
    std::strncpy(out, label + 1, 31);
    out[31] = 0;
}
static void render_mgl_page() {
    char *p;
    mgl_enabled = false;
HOOK
}
static void bind_mgl_slot(const char *p, int d, int selentry) {
    (void)d;
BINDING
}
static bool is_x86() { return false; }
static bool is_pcxt() { return std::strcmp(rows[0], "PCXT") == 0; }
static bool game_docs_manual_available() { return false; }
static uint32_t manual_submenu = -1, dip_submenu = -1, ra_submenu = -1;
static bool select, ordinary_menu_command;
static struct { int dip_num; } switches;
static auto arcade_sw() { return &switches; }
struct Transfer { char type; int index; };
static Transfer selected_transfer() {
    char addon[32], *p;
    int h, d, inpage, i = 2;
    int menustate = 0;
    const int MENU_NONE1 = 1;
    (void)MENU_NONE1;
    uint32_t entry = 0;
    menusub = mgl->item[mgl->current].submenu;
    select = true;
MENU_ACTIONS
    switch (0) {
    case 0:
LOOKUP
    {
        int store_name, opensave, ioctl_index;
        if (p[0] == 'F') {
FILE_INDEX
            (void)store_name;
            (void)opensave;
            return {'F', ioctl_index};
        }
        if (p[0] == 'S') {
IMAGE_INDEX
            (void)store_name;
            return {'S', ioctl_index};
        }
    }
        break;
    }
    (void)menustate;
    return {'?', -1};
}
static void transfer_is(char type, int index) {
    const auto selected = selected_transfer();
    if (selected.type != type || selected.index != index) {
        std::fprintf(stderr, "%s MGL %c%d selected %c%d, expected %c%d\n",
                     rows[0], mgl->item[mgl->current].type, mgl->item[mgl->current].index,
                     selected.type, selected.index, type, index);
    }
    assert(selected.type == type && selected.index == index);
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
    assert(MglFilePage('F', 7, 1, ~0U) == 1); // No matching page: keep the current page.
    // Execute the actual render-state integration, not just the helper.
    test_mask = 1U << 14;
    page = flat = 0;
    menusub = firstmenu = 7;
    description = {false, 0, {{'F', 5, 0}, {'S', 0, 0}}};
    render_mgl_page();
    assert(page == 1 && menusub == 0 && firstmenu == 0);
    assert(std::strcmp(title, "System & BIOS;") == 0);
    bind_mgl_slot("FC5,JRC,Cartridge 1;", 0, 0);
    transfer_is('F', 5);
    description.item[0] = {'F', 6, 0};
    render_mgl_page();
    bind_mgl_slot("FC5,JRC,Cartridge 1;", 0, 0);
    bind_mgl_slot("FC6,JRC,Cartridge 2;", 0, 1);
    transfer_is('F', 6);
    description.current = 1;
    render_mgl_page();
    assert(page == 0);
    bind_mgl_slot("S0,IMG,Floppy;", 0, 0);
    transfer_is('S', 0);
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
    // Existing MGLs request the historical slots. On the released SNES/NES
    // cores the correct loader is row zero even when the slot doesn't match.
    rows = {"SNES", "", "FS1,SFCSMCBINBS ;", "FS4,SPC;"};
    description = {false, 0, {{'F', 0, 0}, {'F', 1, 0}}};
    test_mask = 0;
    page = flat = 0;
    render_mgl_page();
    bind_mgl_slot(rows[2], 0, 0);
    transfer_is('F', 1);
    assert(consume_mgl_slot() == 1 && description.state == 0);
    description.current = 1;
    render_mgl_page();
    bind_mgl_slot(rows[2], 0, 0);
    transfer_is('F', 1); // An explicit SNES slot still works.
    rows = {"NES", "", "FS,NESFDSNSF;", "H1F2,BIN,Load FDS BIOS;"};
    render_mgl_page();
    bind_mgl_slot(rows[2], 0, 0);
    transfer_is('F', 1); // Unnumbered binding parses as 0; transfer uses row+1.
    // Bind the exact visible disk row even when it is disabled. Dispatch
    // must skip that row, never send its file to the first (BIN) loader.
    rows = {"BK0011M", "", "F,BIN;", "D2S1,DSKIMGBKD,Mount FDD A;"};
    description = {false, 0, {{'S', 1, 0}, {'F', 0, 0}}};
    test_mask = 1U << 2;
    render_mgl_page();
    bind_mgl_slot(rows[2], 0, 0);
    bind_mgl_slot(rows[3] + 2, 1, 1);
    assert(description.item[0].submenu == 1);
    description.state = 2;
    transfer_is('?', -1);
    assert(description.state == 3); // The disabled request must not stall the MGL.
    test_mask = 0;
    render_mgl_page();
    bind_mgl_slot(rows[3] + 2, 0, 1);
    transfer_is('S', 1);
    // The added disabled-row match must not hide another enabled exact match.
    rows = {"Core", "", "F2,ROM,Other;", "F1,ROM,Enabled;", "D2F1,ROM,Disabled;"};
    description.item[0] = {'F', 1, 0};
    test_mask = 1U << 2;
    render_mgl_page();
    bind_mgl_slot(rows[3], 0, 1);
    bind_mgl_slot(rows[4] + 2, 1, 2);
    assert(description.item[0].submenu == 1);
    transfer_is('F', 1);
    render_mgl_page();
    bind_mgl_slot(rows[4] + 2, 1, 2);
    assert(description.item[0].submenu == 2); // No stale enabled match.
    // PCXT profiles in a different machine mode must not open the JRC as
    // Floppy A when the PCjr cartridge selectors aren't exposed.
    rows = {"PCXT", "", "S0,IMG,Floppy;", "hEP1FC5,JRC,PCjr Cartridge;"};
    description = {false, 0, {{'F', 5, 0}, {'S', 1, 0}}};
    render_mgl_page();
    description.state = 2;
    transfer_is('?', -1);
    assert(description.state == 3);
    description.current = 1;
    description.state = 2;
    transfer_is('S', 0); // Preserve legacy image-to-image row zero.
    // An unmatched request is not an interactive choice of DIP/manual/RA.
    dip_submenu = manual_submenu = ra_submenu = 0;
    rows = {"Core", "", "O1,Setting,Off,On;", "P1,Submenu;"};
    description.state = 2;
    transfer_is('?', -1);
    assert(!ordinary_menu_command && description.state == 3);
    dip_submenu = manual_submenu = ra_submenu = -1;
    // Keep the existing rejection handling for an explicitly rejected slot.
    description.current = 0;
    description.state = 0;
    description.item[0].submenu = -1;
    assert(consume_mgl_slot() == 0 && description.state == 3);
    description.item[0].submenu = 2;
    description.state = 0;
    assert(consume_mgl_slot() == 1 && description.state == 0);
    description.done = true;
    description.item[0].submenu = -1;
    assert(consume_mgl_slot() == 1 && description.state == 0);
}
'''
for marker, snippet in (
    ('PRODUCTION', production), ('HOOK', hook), ('BINDING', binding),
    ('MENU_ACTIONS', menu_actions), ('LOOKUP', lookup),
    ('FILE_INDEX', file_index), ('IMAGE_INDEX', image_index),
    ('REJECTION', rejection),
):
    test = test.replace(marker, snippet)
with tempfile.TemporaryDirectory(prefix='degauss-mgl-pages-') as tmp:
    cpp = Path(tmp) / 'test.cpp'
    binary = Path(tmp) / 'test'
    cpp.write_text(test)
    subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print('MGL page resolver: passed')
