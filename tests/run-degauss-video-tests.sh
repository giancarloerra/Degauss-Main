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
	| grep -Fq 'if(stock_menu&&fpga_has_degauss_menu()){fpga_load_rbf(DEGAUSS_COLD_BOOT_MARKER);}'
printf '%s\n' "$compact_startup" \
	| grep -Fq 'user_io_init(degauss_cold_boot?"":((argc>1)?argv[1]:""),'
grep -Fq '#define DEGAUSS_COLD_BOOT_MARKER "@degauss-cold-boot"' fpga_io.h
grep -Fq 'degauss_cold_boot && degauss_menu ? DEGAUSS_COLD_BOOT_MARKER' fpga_io.cpp

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

# fb_hscale changes only the Linux framebuffer's horizontal divisor. Its
# default preserves the released geometry; vertical scaling and output timing
# remain controlled by their existing paths.
grep -Fq 'uint8_t fb_hscale;' cfg.h
grep -Fq '{ "FB_HSCALE", (void*)(&(cfg.fb_hscale)), UINT8, 1, 4 },' cfg.cpp
grep -Fq 'cfg.fb_hscale = 1;' cfg.cpp
grep -Fq 'const int fb_scale_x = fb_scale * cfg.fb_hscale;' video.cpp
grep -Fq 'const int fb_scale_y = v_cur.param.pr == 0 ? fb_scale : fb_scale * 2;' video.cpp
grep -Fq 'fb_width = v_cur.item[1] / fb_scale_x;' video.cpp
grep -Fq 'fb_height = v_cur.item[5] / fb_scale_y;' video.cpp

# Native CRT plus independently timed HDMI is opt-in. The default keeps the
# released framebuffer path, while the enabled Degauss path uses a native-size
# source and explicitly asks the paired Menu core for native analog output.
grep -Fq 'uint8_t degauss_native_analog;' cfg.h
grep -Fq '{ "DEGAUSS_NATIVE_ANALOG", (void*)(&(cfg.degauss_native_analog)), UINT8, 0, 1 },' cfg.cpp
grep -Fq '#define FB_NATIVE   0x2000' video.cpp
grep -Fq 'return degauss_native_fb && is_menu() && !cfg.vga_scaler;' video.cpp
grep -Fq 'enable = enable && cfg.degauss_native_analog;' video.cpp
grep -Fq '(video_degauss_native_fb_active() ? FB_NATIVE : 0)' video.cpp
grep -Fq 'int width = 352, height = cfg.menu_pal ? 288 : 240;' video.cpp

# Very narrow test modes still need a non-zero checker size before the
# framebuffer diagnostic divides coordinates by it.
grep -A8 'static void draw_checkers()' video.cpp | grep -Fq 'if (!sz) sz = 1;'

# Degauss uses native mask files only while its Menu framebuffer is active.
# A malformed file switches the effect off, never restores the old effect.
grep -Fq 'else if (!strcmp(cmd, "fb_mask off")) video_set_degauss_display_mask(nullptr);' input.cpp
grep -Fq 'else if (!strncmp(cmd, "fb_mask ", 8)) video_set_degauss_display_mask(cmd + 8);' input.cpp
mask_handler="$(sed -n '/^bool video_set_degauss_display_mask(/,/^}/p' video.cpp)"
printf '%s\n' "$mask_handler" | grep -Fq 'if (!is_menu() || !video_fb_state())'
printf '%s\n' "$mask_handler" | grep -Fq 'degauss_display_mask[0] = 0;'
printf '%s\n' "$mask_handler" | grep -Fq 'setShadowMask();'
invalid_name_handler="$(printf '%s\n' "$mask_handler" | sed -n '/if (!len || len >= sizeof(degauss_display_mask)/,/return false;/p')"
printf '%s\n' "$invalid_name_handler" | grep -Fq 'degauss_display_mask[0] = 0;'
printf '%s\n' "$invalid_name_handler" | grep -Fq 'setShadowMask();'
if printf '%s\n' "$mask_handler" | grep -Fq 'video_save_shadow_mask_cfg'; then
	exit 1
fi
grep -Fq 'Scripts/.config/degauss/masks/%s.txt' video.cpp
grep -Fq 'const int fb_mask = (degauss_display_mask[0] || degauss_preset_active) ? SM_FLAG_FB : 0;' video.cpp
grep -Fq 'case SM_MODE_1X: spi_w(SM_FLAG(SM_FLAG_ENABLED | fb_mask)); break;' video.cpp
grep -Fq 'if (!video_fb_state() && degauss_display_mask[0])' video.cpp
fb_enable="$(sed -n '/void video_fb_enable/,/^}/p' video.cpp)"
printf '%s\n' "$fb_enable" | grep -Fq 'if (!video_fb_state() && degauss_preset_active)'
printf '%s\n' "$fb_enable" | grep -Fq 'degauss_restore_preset_baseline(false);'

# A temporary Degauss preset restores the exact live Menu state rather than
# reloading saved/default configuration and losing unsaved OSD choices.
preset_restore="$(sed -n '/static void degauss_restore_preset_baseline/,/^}/p' video.cpp)"
if printf '%s\n' "$preset_restore" | grep -Fq 'video_cfg_init();'; then
	exit 1
fi
printf '%s\n' "$preset_restore" | grep -Fq 'memcpy(gamma_cfg, degauss_gamma_before_preset'
printf '%s\n' "$preset_restore" | grep -Fq 'if (has_gamma) spi_uio_cmd8(UIO_SET_GAMMA, gamma_cfg[0]);'
printf '%s\n' "$preset_restore" | grep -Fq 'memcpy(scaler_flt, degauss_scaler_before_preset'
printf '%s\n' "$preset_restore" | grep -Fq 'memcpy(scaler_flt_data, degauss_scaler_data_before_preset'
printf '%s\n' "$preset_restore" | grep -Fq 'memcpy(shadow_mask_cfg, degauss_shadow_mask_before_preset'
preset_apply="$(sed -n '/bool video_set_degauss_preset/,/^}/p' video.cpp)"
printf '%s\n' "$preset_apply" | grep -Fq 'memcpy(degauss_gamma_before_preset, gamma_cfg'
printf '%s\n' "$preset_apply" | grep -Fq 'memcpy(degauss_scaler_before_preset, scaler_flt'
printf '%s\n' "$preset_apply" | grep -Fq 'memcpy(degauss_scaler_data_before_preset, scaler_flt_data'
printf '%s\n' "$preset_apply" | grep -Fq 'memcpy(degauss_shadow_mask_before_preset, shadow_mask_cfg'
printf '%s\n' "$preset_apply" | grep -Fq 'if (!video_loadPreset(path, false))'
printf '%s\n' "$preset_apply" | grep -Fq 'degauss_restore_preset_baseline(true);'
printf '%s\n' "$preset_apply" | grep -Fq 'return false;'

# A mask selected while a full preset is active is parsed before it is
# accepted as the state to restore later. A missing or malformed file resets it.
deferred_mask="$(sed -n '/if (degauss_preset_active)/,/return true;/p' video.cpp | head -n 20)"
printf '%s\n' "$deferred_mask" | grep -Fq 'Scripts/.config/degauss/masks/%s.txt'
printf '%s\n' "$deferred_mask" | grep -Fq 'if (!degauss_validate_mask_path(path))'
printf '%s\n' "$deferred_mask" | grep -Fq 'degauss_mask_before_preset[0] = 0;'
