#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

main_startup="$(sed -n '/FindStorage();/,/user_io_init/p' main.cpp)"
compact_startup="$(printf '%s\n' "$main_startup" | tr -d '[:space:]')"

# Stock Main supplies an empty core path when it starts the configured custom
# Main binary after a cold boot. That path must still select Degauss's private
# Menu core; otherwise the stock core leaves scaler/framebuffer Y/C monochrome.
printf '%s\n' "$compact_startup" \
	| grep -Fq 'argc<=1||!argv[1][0]||!strcasecmp(argv[1],"menu.rbf")'
printf '%s\n' "$compact_startup" \
	| grep -Fq 'if(stock_menu&&fpga_has_degauss_menu()){fpga_load_rbf("menu.rbf");}'

framebuffer_enable="$(awk '
  /^void video_fb_enable\(/ { capture = 1 }
  capture { print }
  /^int video_fb_state\(/ { exit }
' video.cpp)"
compact_enable="$(printf '%s\n' "$framebuffer_enable" | tr -d '[:space:]')"

# Framebuffer activation is not the Menu-core selection boundary. Preserve the
# existing Direct Video update without reprogramming scaler Y/C here.
test "$(printf '%s\n' "$compact_enable" | grep -oF 'set_vga_fb(enable);' | wc -l | tr -d '[:space:]')" -eq 1
printf '%s\n' "$compact_enable" \
	| grep -Fq 'if(cfg.direct_video){set_vga_fb(enable);set_yc_mode();}'
if printf '%s\n' "$compact_enable" | grep -Fq 'cfg.vga_scaler)set_yc_mode();'; then
	exit 1
fi
