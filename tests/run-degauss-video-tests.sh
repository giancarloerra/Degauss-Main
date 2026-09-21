#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

framebuffer_enable="$(awk '
  /^void video_fb_enable\(/ { capture = 1 }
  capture { print }
  /^int video_fb_state\(/ { exit }
' video.cpp)"

# A scaler-backed framebuffer needs the same Y/C refresh as Direct Video.
# Without it, cold startup can retain parameters calculated before the
# framebuffer timing was ready and remain monochrome until a video re-init.
printf '%s\n' "$framebuffer_enable" \
	| grep -Fq 'if (cfg.direct_video || cfg.vga_scaler) set_yc_mode();'

# Direct Video still owns only its existing framebuffer-selection command.
printf '%s\n' "$framebuffer_enable" \
	| grep -Fq 'if (cfg.direct_video) set_vga_fb(enable);'
