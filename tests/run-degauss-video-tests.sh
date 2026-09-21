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

# Direct Video still owns the sole framebuffer-selection command. Ignore
# formatting so this checks the invariant rather than one source spelling.
compact_enable="$(printf '%s\n' "$framebuffer_enable" | tr -d '[:space:]')"
test "$(printf '%s\n' "$compact_enable" | grep -oF 'set_vga_fb(enable);' | wc -l | tr -d '[:space:]')" -eq 1
case "$compact_enable" in
	*'if(cfg.direct_video)set_vga_fb(enable);'* | *'if(cfg.direct_video){set_vga_fb(enable);'*) ;;
	*) exit 1 ;;
esac
