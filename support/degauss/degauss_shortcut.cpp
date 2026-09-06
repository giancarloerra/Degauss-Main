// Degauss frontend shortcut integration for MiSTer Main.
//
// Copyright (C) 2026 Giancarlo Erra
// SPDX-License-Identifier: GPL-3.0-or-later

#include <stdio.h>
#include <string.h>

#include "degauss_shortcut.h"
#include "degauss_launcher.h"
#include "../../file_io.h"
#include "../../menu.h"
#include "../../user_io.h"
#include "../../video.h"

namespace
{

constexpr const char *CONFIG_NAME = "degauss/frontend_shortcut.bin";
constexpr const char *CONFIG_PATH = CONFIG_DIR "/degauss/frontend_shortcut.bin";

using degauss_shortcut_logic::ConfigV1;
using degauss_shortcut_logic::KeyboardRuntimeState;
using degauss_shortcut_logic::RequestState;

ConfigV1 config = degauss_shortcut_logic::make_config(0);
DegaussShortcutLoadState load_state = DEGAUSS_SHORTCUT_MISSING;
bool loaded = false;
RequestState request_state;

bool capture_active = false;
bool capture_ready = false;
uint16_t capture_key = 0;
uint16_t capture_release_key = 0;

KeyboardRuntimeState keyboard_state;

void ensure_loaded()
{
	if (loaded) return;
	loaded = true;

	const bool exists = FileExists(CONFIG_PATH);
	const int size = FileLoadConfig(CONFIG_NAME, nullptr, 0);
	ConfigV1 candidate = {};
	const bool read = size == static_cast<int>(sizeof(candidate))
		&& FileLoadConfig(CONFIG_NAME, &candidate, sizeof(candidate))
			== static_cast<int>(sizeof(candidate));
	const degauss_shortcut_logic::ConfigLoadResult result =
		degauss_shortcut_logic::classify_config(exists, size,
			read ? &candidate : nullptr);

	if (result == degauss_shortcut_logic::CONFIG_MISSING) return;
	if (result == degauss_shortcut_logic::CONFIG_INVALID)
	{
		load_state = DEGAUSS_SHORTCUT_INVALID;
		printf("Degauss shortcut config is invalid or unsupported (size %d): %s\n",
			size, CONFIG_PATH);
		return;
	}

	config = candidate;
	load_state = DEGAUSS_SHORTCUT_VALID;
}

bool save_config(const ConfigV1 &candidate)
{
	if (!degauss_shortcut_logic::config_valid(candidate)) return false;

	ConfigV1 stored = candidate;
	if (FileSaveConfig(CONFIG_NAME, &stored, sizeof(stored))
		!= static_cast<int>(sizeof(stored)))
	{
		printf("Degauss shortcut config save failed: %s\n", CONFIG_PATH);
		return false;
	}

	config = candidate;
	load_state = DEGAUSS_SHORTCUT_VALID;
	loaded = true;
	return true;
}

bool runtime_eligible(bool require_hidden_osd)
{
	const degauss_shortcut_logic::RuntimeConditions conditions = {
		degauss_installed(),
		is_menu() != 0,
		menu_osd_is_unlocked(),
		video_fb_state() && video_chvt(0) == 2,
		user_io_osd_is_visible() != 0
	};
	return degauss_shortcut_logic::runtime_eligible(conditions, require_hidden_osd);
}

} // namespace

DegaussShortcutLoadState degauss_shortcut_load_state(void)
{
	ensure_loaded();
	return load_state;
}

uint16_t degauss_shortcut_keyboard_key(void)
{
	ensure_loaded();
	return load_state == DEGAUSS_SHORTCUT_INVALID ? 0 : config.keyboard_key;
}

bool degauss_shortcut_set_keyboard(uint16_t key)
{
	ensure_loaded();
	if (load_state == DEGAUSS_SHORTCUT_INVALID
		|| !degauss_shortcut_logic::valid_keyboard_key(key))
	{
		return false;
	}

	return save_config(degauss_shortcut_logic::make_config(key));
}

bool degauss_shortcut_reset(void)
{
	return save_config(degauss_shortcut_logic::make_config(0));
}

void degauss_shortcut_begin_keyboard_capture(void)
{
	capture_active = true;
	capture_ready = false;
	capture_key = 0;
}

void degauss_shortcut_cancel_keyboard_capture(void)
{
	capture_active = false;
	capture_ready = false;
	capture_key = 0;
}

bool degauss_shortcut_take_keyboard_capture(uint16_t *key)
{
	if (!capture_ready) return false;
	if (key) *key = capture_key;
	capture_ready = false;
	return true;
}

bool degauss_shortcut_handle_keyboard_event(uint16_t key, int value, bool menu_event)
{
	ensure_loaded();

	if (!menu_event && capture_active)
	{
		if (value == 1 && key)
		{
			capture_active = false;
			capture_ready = true;
			capture_key = key;
			capture_release_key = key;
		}
		return true;
	}

	if (!menu_event && capture_release_key && key == capture_release_key)
	{
		if (!value) capture_release_key = 0;
		return true;
	}

	if (menu_event || load_state == DEGAUSS_SHORTCUT_INVALID) return false;

	const bool needs_eligibility = !keyboard_state.consumed_key
		&& config.keyboard_key
		&& key == config.keyboard_key
		&& value == 1;
	bool triggered = false;
	const bool consumed = keyboard_state.event(config.keyboard_key, key, value,
		needs_eligibility && runtime_eligible(true), triggered);
	if (triggered) request_state.request();
	return consumed;
}

bool degauss_shortcut_take_request(void)
{
	if (!request_state.pending) return false;
	return request_state.take(runtime_eligible(false));
}
